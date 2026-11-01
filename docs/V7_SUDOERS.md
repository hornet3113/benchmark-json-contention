# V7 — Diseño de la regla de sudoers para el flush de caché

**Estado: DISEÑO, no aplicado.** Nada de este documento se ha instalado en el
sistema. Es lo que pediste ver antes de tocar nada (CLAUDE.md, pendiente V7).

## El problema

Cada repetición limpia la caché de páginas de la VM (A5, R-21), y eso necesita
root: `sync` y `echo 3 > /proc/sys/vm/drop_caches`. Hoy `scripts/flush_caches.sh`
usa `sudo -n` y el runner renueva las credenciales con `sudo -n -v` mientras
corre. Funciona para una celda, pero **no para la matriz**: `sudo` guarda la
contraseña unos 15 minutos y F8 son 13–20 h. En cuanto caduque, el flush falla,
y una repetición sin flush no mide lo que dice medir.

`scripts/run_benchmarks.sh` ya no deja que eso pase en silencio: comprueba
`sudo -n true` **antes de cada celda** y, si caducó, se detiene y lo dice. Sin
regla de sudoers, la matriz se corre en bloques, escribiendo la contraseña al
empezar cada uno.

## Las tres opciones (SPEC A5)

| | Qué | Veredicto |
|---|---|---|
| 1 | Seguir con `sudo -v` y bloques cortos | No toca el sistema, pero te ata al equipo cada ~15 min |
| 2 | Correr toda la matriz bajo `sudo` | **Mala idea:** Python, el runner y los drivers correrían como root |
| 3 | Regla en `/etc/sudoers.d/` para **un solo** script | La dirección razonable; es la que se diseña aquí |

## Diseño de la opción 3

### El script

| | |
|---|---|
| **Dónde vive** | `/usr/local/sbin/bench-drop-caches` — **fuera del repositorio** |
| **De quién es** | `root:root` |
| **Permisos** | `0755` (lo lee y ejecuta cualquiera; **solo root lo escribe**) |
| **Parámetros** | **Ninguno.** Si recibe alguno, sale con error sin hacer nada |
| **Qué hace** | `sync` y `echo 3 > /proc/sys/vm/drop_caches`. Nada más |

**Por qué fuera del repo, y es lo importante de todo esto.** Si el script viviera
en `~/benchmark-json-contention/scripts/` —escribible por tu usuario— la regla
equivaldría a darte **root completo sin contraseña**: bastaría con editar el
archivo y poner cualquier otra cosa dentro. Esa es la trampa clásica de las
reglas de sudoers, y es la razón de que el archivo tenga que ser de root y vivir
en `/usr/local/sbin/`.

Contenido propuesto, íntegro:

```sh
#!/bin/sh
# bench-drop-caches — sync + drop_caches. Instalado para el proyecto
# benchmark-json-contention (V7, SPEC A5). No acepta parámetros.
# Revertir:  sudo rm /etc/sudoers.d/bench-drop-caches /usr/local/sbin/bench-drop-caches
[ $# -eq 0 ] || { echo "bench-drop-caches no acepta parámetros" >&2; exit 2; }
sync
echo 3 > /proc/sys/vm/drop_caches
```

### La regla

Archivo `/etc/sudoers.d/bench-drop-caches`, de `root:root` y con permisos
**`0440`** (sudo rechaza el archivo si es más permisivo):

```
alix_anahi ALL=(root) NOPASSWD: /usr/local/sbin/bench-drop-caches
```

- Nombra **un único ejecutable por ruta absoluta**: sin comodines, sin `*`, sin
  argumentos libres, sin `ALL`.
- Solo `NOPASSWD` para ese programa. Todo lo demás sigue pidiendo contraseña.
- Se instala con `sudo visudo -f /etc/sudoers.d/bench-drop-caches`, que **valida
  la sintaxis antes de guardar**. Nunca con un redirigido, porque un archivo de
  sudoers mal escrito puede dejarte sin `sudo`.

### Qué permite exactamente

Que tu usuario vacíe la caché de páginas del kernel de la VM sin contraseña. Eso
es todo. No da acceso a archivos, ni a otros comandos, ni a una shell de root.
Es una operación que ralentiza un momento a la máquina y no altera datos.

### Qué habría que cambiar en el repo

En `scripts/flush_caches.sh`, una sola línea:

```diff
-if sudo -n sh -c 'echo 3 > /proc/sys/vm/drop_caches' 2>/dev/null; then
+if sudo -n /usr/local/sbin/bench-drop-caches 2>/dev/null; then
```

Conviene que funcione de las dos formas: si el script no está instalado, usar la
ruta de hoy. Así el repo sigue corriendo en una máquina sin la regla —y el
docente puede reproducirlo sin instalar nada.

### Cómo se revierte, en 10 segundos

```sh
sudo rm /etc/sudoers.d/bench-drop-caches
sudo rm /usr/local/sbin/bench-drop-caches
sudo -k                                  # olvida las credenciales en caché
sudo -l | grep -i bench || echo "revertido: ya no hay regla"
```

No queda ningún rastro: son dos archivos y ninguno modifica nada existente.
**No se toca `/etc/sudoers`**, solo se añade y se borra un archivo propio en
`/etc/sudoers.d/`.

### Comprobación después de instalar

```sh
sudo -l | grep bench-drop-caches        # la regla aparece
sudo -n /usr/local/sbin/bench-drop-caches && echo "funciona sin contraseña"
sudo -n /usr/local/sbin/bench-drop-caches x ; echo "con parámetro debe dar 2: $?"
sudo -n true ; echo "lo demás SÍ pide contraseña, debe fallar: $?"
stat -c '%U %G %a %n' /usr/local/sbin/bench-drop-caches /etc/sudoers.d/bench-drop-caches
```

La tercera y la cuarta son las que importan: confirman que el permiso no se
desborda a otros comandos.

## Lo que queda a tu criterio

1. **¿Se instala o no?** Sin regla, F8 va en bloques de ~2 h con la contraseña
   al empezar cada uno (6 bloques con 36 celdas). Con regla, puede correr
   desatendida.
2. **¿Solo mientras dure el proyecto?** Se puede instalar para F8 y revertirla
   al terminar. Eso deja el sistema como estaba y la evidencia ya recogida.
3. Si se instala, queda declarado en la sección 1 del reporte, con este
   documento como referencia, igual que las demás desviaciones del entorno.

**No aplico nada hasta que lo apruebes explícitamente**, y cuando lo hagas, los
comandos los ejecutas tú: no tengo (ni quiero tener) sudo sin tu presencia.
