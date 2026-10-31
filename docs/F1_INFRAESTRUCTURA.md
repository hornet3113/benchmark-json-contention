# F1 — Infraestructura Docker (CERRADA el 2026-11-01)

**Estado: cerrada con evidencia en `results/env/f1/`.** Todas las casillas de
abajo tienen salida de comandos detrás; el detalle está en el registro de
ejecución, al final. El procedimiento sigue siendo válido para repetir la
verificación (por ejemplo, después de un `docker pull` que cambie el digest).

Qué cubre F1: levantar MongoDB y PostgreSQL bajo los tres perfiles de recursos
del manual y comprobar que los límites se aplican de verdad. No incluye
esquema, índices, dataset ni queries — eso es F2 y F3.

---

## Archivos de esta fase

| Archivo | Qué hace |
|---|---|
| `docker/docker-compose.yml` | Los dos servicios, parametrizados por variables. R-25 |
| `docker/images.env` | Etiquetas de imagen y credenciales locales |
| `docker/profiles/a_baseline.env` | 4.0 CPU · 4096 m — R-05 |
| `docker/profiles/b_medium.env` | 2.0 CPU · 2048 m — R-06 |
| `docker/profiles/c_severe.env` | 1.0 CPU · 1024 m — R-07 |
| `scripts/up_profile.sh` | Levanta un motor con un perfil y espera a que esté sano |
| `scripts/down_profile.sh` | Baja todo; con `--volumes` borra datos (pide confirmación) |
| `scripts/verify_limits.sh` | Compara límites reales contra los esperados y archiva evidencia |

---

## Cómo ejecutarlo desde Ubuntu WSL2

Desde PowerShell, `wsl -d Ubuntu` te deja en `/mnt/c/Users/...`. Hay que moverse
al repo, que vive en el sistema de archivos de Linux (F0-V3).

```bash
cd ~/benchmark-json-contention
chmod +x scripts/*.sh          # solo la primera vez
```

Comprobación previa de que las imágenes existen:

```bash
docker pull mongo:8.2
docker pull postgres:18
```

Si alguna etiqueta no existe, cámbiala en `docker/images.env` y dímelo: la
etiqueta es una propuesta mía, lo que vale como evidencia es el digest que
registra el verificador.

### Prueba de PROFILE_A

```bash
scripts/up_profile.sh a_baseline mongo
scripts/verify_limits.sh a_baseline mongo

scripts/up_profile.sh a_baseline postgres
scripts/verify_limits.sh a_baseline postgres

scripts/down_profile.sh
```

`up_profile.sh` baja cualquier motor que estuviera arriba antes de levantar el
suyo: nunca corren los dos a la vez (SPEC §2, decisión 1).

### Los otros dos perfiles

```bash
for P in b_medium c_severe; do
  for E in mongo postgres; do
    scripts/up_profile.sh $P $E && scripts/verify_limits.sh $P $E
  done
done
scripts/down_profile.sh
```

---

## Qué debe salir

`verify_limits.sh` imprime y archiva. Para PROFILE_A:

```
  OK    cpu.max          esperado=400000 100000        obtenido=400000 100000
  OK    memory.max       esperado=4294967296           obtenido=4294967296
  OK    memory.swap.max  esperado=0                    obtenido=0
```

Y termina con `RESULTADO: TODOS LOS LIMITES COINCIDEN`, código de salida 0.

La evidencia queda en `results/env/f1/PROFILE_A_BASELINE_<motor>_<fecha>.txt`
y `.json`, con el digest de la imagen y la versión del motor (R-28, diapo 5/13).

### Si `cpu.max` sale `max 100000`

Significa que Compose no aplicó la clave `cpus:`. El experimento correría sin
contención y los números no medirían nada. Solución: sustituir en los dos
servicios

```yaml
    cpus: ${CPUS_LIMIT}
```

por

```yaml
    deploy:
      resources:
        limits:
          cpus: ${CPUS_LIMIT}
```

y volver a verificar. No sigas a F2 hasta que `cpu.max` dé el valor correcto.

---

## Hallazgo abierto: `mem_swappiness` (V8)

Al resolver el compose con `docker compose config`, la clave `mem_swappiness`
**desaparece** del resultado, mientras `cpus`, `mem_limit` y `memswap_limit`
sí aparecen. Observado sobre el archivo de este repo.

Explicación más probable, sin confirmar: `memory.swappiness` era un control de
**cgroups v1**; cgroups v2 no lo expone por cgroup. El manual pide las dos
cosas a la vez (cgroups v2 **y** `mem_swappiness=0`), así que la tensión es del
manual, no de la implementación.

Esto no rompe nada, porque la garantía de "sin swap" la da `memory.swap.max=0`,
que sí se verifica y sí se cumple. Lo que hay que hacer es **confirmarlo en tu
máquina** y declararlo:

```bash
docker inspect bench_mongo --format '{{.HostConfig.MemorySwappiness}}'
docker exec bench_mongo ls /sys/fs/cgroup/ | grep -i swappi || echo "no existe memory.swappiness (esperado en cgroups v2)"
```

Guarda también cualquier aviso que Docker imprima al levantar el contenedor.
`verify_limits.sh` ya reporta ambas cosas y **no** las cuenta como fallo.

---

## Criterios para dar F1 por completada

- [x] `docker pull` exitoso de ambas imágenes; digests registrados
- [x] PROFILE_A verificado en Mongo **y** en Postgres, con código de salida 0
- [x] PROFILE_B verificado en ambos motores
- [x] PROFILE_C verificado en ambos motores
- [x] `memory.swap.max = 0` en los tres perfiles y los dos motores
- [x] Archivos de métricas del cgroup presentes en todos los casos
- [x] V8 resuelta: comportamiento de `mem_swappiness` documentado con evidencia (SPEC A7)
- [x] Seis archivos de evidencia en `results/env/f1/`
- [x] Prueba negativa de OOM: un contenedor que pide más memoria de la del
      perfil muere y `memory.events` lo registra (PLAN F1)

Hasta que estas casillas tengan salida de comandos detrás, F1 sigue abierta.

---

## Registro de ejecución

### 2026-11-01 — imágenes y PROFILE_A

Entorno al empezar: Docker 29.4.1, `CgroupVersion=2`, `NCPU=12`,
`MemTotal=7687327744` (= 7.159 GiB, igual que en F0). Contenedores de otros
proyectos presentes pero todos detenidos.

| Paso | Resultado | Evidencia en `results/env/f1/` |
|---|---|---|
| `docker pull mongo:8.2` | exit 0 · `sha256:e0ce8c35124d4a9f9785532d1f268f39e9728ffa1cb38f46fa482436424c4bd3` | `docker_pull_20261101T164211Z.txt` |
| `docker pull postgres:18` | exit 0 · `sha256:3a4264520e121176619f54ff867d12774bc81e95e7b84db58d63bccdb6144b81` | ídem |
| `up_profile.sh a_baseline mongo` | healthy · sin avisos de Docker | `up_PROFILE_A_BASELINE_mongodb_20261101T164551Z.txt` |
| `verify_limits.sh a_baseline mongo` | exit 0 · MongoDB 8.2.12 · wiredTiger · `cpu.max=400000 100000` · `memory.max=4294967296` · `memory.swap.max=0` · 5/5 archivos de métricas | `PROFILE_A_BASELINE_mongodb_20261101T164611Z.{txt,json}` |
| `up_profile.sh a_baseline postgres` | healthy · sin avisos de Docker | `up_PROFILE_A_BASELINE_postgresql_20261101T164629Z.txt` |
| `verify_limits.sh a_baseline postgres` | exit 0 · PostgreSQL 18.6 · mismos tres valores · 5/5 archivos de métricas · `data_directory=/var/lib/postgresql/data/pgdata` | `PROFILE_A_BASELINE_postgresql_20261101T164643Z.{txt,json}` |
| `down_profile.sh` | exit 0 · volúmenes conservados | — |

Lo que se observó para V8, sin cerrarla todavía:

- `docker compose up` **no imprimió ningún aviso** sobre `mem_swappiness`.
- `docker inspect` → `HostConfig.MemorySwappiness=<no value>` en los dos motores:
  el valor no llegó a Docker.
- `/sys/fs/cgroup/memory.swappiness` no existe dentro de ninguno de los dos
  contenedores.

Con esto todavía no se sabe *quién* descarta el valor: si Compose (ya se vio
en `docker compose config`) o también Docker Engine al recibirlo bajo
cgroups v2. Para separar las dos cosas falta una prueba con `docker run
--memory-swappiness=0` directo, sin Compose.

### 2026-11-01 — PROFILE_B y PROFILE_C

Bucle de "Los otros dos perfiles", tal cual. La salida de cada `up` está en
`up_<perfil>_<motor>_<fecha>.txt`. Los cuatro `up` salieron healthy y sin
avisos de Docker, y los cuatro `verify_limits.sh` terminaron con exit 0.

| Perfil | Motor | `cpu.max` | `memory.max` | `memory.swap.max` | Evidencia |
|---|---|---|---|---|---|
| PROFILE_B_MEDIUM | mongodb 8.2.12 | `200000 100000` | `2147483648` | `0` | `PROFILE_B_MEDIUM_mongodb_20261101T171042Z.{txt,json}` |
| PROFILE_B_MEDIUM | postgresql 18.6 | `200000 100000` | `2147483648` | `0` | `PROFILE_B_MEDIUM_postgresql_20261101T171059Z.{txt,json}` |
| PROFILE_C_SEVERE | mongodb 8.2.12 | `100000 100000` | `1073741824` | `0` | `PROFILE_C_SEVERE_mongodb_20261101T171114Z.{txt,json}` |
| PROFILE_C_SEVERE | postgresql 18.6 | `100000 100000` | `1073741824` | `0` | `PROFILE_C_SEVERE_postgresql_20261101T171133Z.{txt,json}` |

En los cuatro casos estaban los 5 archivos de métricas, y `MemorySwappiness` salió
`<no value>` igual que en PROFILE_A. `down_profile.sh` terminó con exit 0.

### 2026-11-01 — V8 resuelta

Evidencia en `V8_mem_swappiness_20261101T171426Z.txt`; el detalle está en SPEC A7.

- Ninguno de los seis `docker compose up` emitió avisos.
- `MemorySwappiness=<nil>`, y no hay ningún `memory.swappiness` en el cgroup.
- `docker compose config` no incluye la clave: Compose no se la pasa a Docker.
- Con `docker create --memory-swappiness=0` directo, Docker la descarta con
  el aviso `Memory swappiness discarded.` y `memory.swap.max` queda en `0`.

No es un fallo: la garantía de "sin swap" es `memory.swap.max=0`.

### 2026-11-01 — Prueba negativa de OOM

Script: `scripts/probes/oom_profile_c.sh`. Es una sonda: no usa los motores ni
produce filas del CSV. Evidencia: `OOM_PROFILE_C_SEVERE_20261101T171903Z.txt`.

Contenedor desechable (`mongo:8.2`, solo `sh`/`head`/`tail`) con los límites de
`c_severe.env`, que pide 2 GiB con `head -c 2G /dev/zero | tail`.

| Fuente | Valor observado |
|---|---|
| Código del proceso asignador / del contenedor | `137` / `137` (128 + SIGKILL) |
| `memory.events` leído dentro del cgroup | `max 251` · `oom 10` · `oom_kill 1` · `oom_group_kill 0` |
| `memory.peak` | `1073741824` (exactamente `memory.max`) |
| `memory.swap.max` | `0` |
| `docker inspect State.OOMKilled` | `true` |
| Swap usado en la VM, antes / después | `0 MB` / `0 MB` |

El kernel mata **al proceso** que se pasa del límite, no al contenedor entero.
En la sonda, el contenedor termina con 137 porque `sh` devuelve el código del
proceso muerto. `memory.events` y `State.OOMKilled` registran el OOM los dos,
así que las dos fuentes que propone SPEC A6 funcionan en este entorno.
Por qué `oom` (10) es mayor que `oom_kill` (1) no se investigó.

### Pendiente detectado al cerrar (resuelto abajo): criterio de PLAN.md que este documento no listaba

PLAN.md F1 pide además que **`capture_env.py` emita un JSON** con versión del
motor, digest, límites reales y datos del host (R-28). Ese script **no existe**.
Los JSON de `verify_limits.sh` cubren versión, digest y límites, pero los
datos del host (loadavg, memoria y swap de la VM) solo quedan en los `.txt`.
Hasta que esto se resuelva o se acuerde que `verify_limits.sh` lo cubre, F1 no
se declara cerrada.

### 2026-11-01 — `capture_env.py` y corrección de `verify_limits.sh`

Decisión de Alix: opción (a), escribir `capture_env.py`.

- **`scripts/capture_env.py`** es ahora el único lugar que lee el cgroup,
  `docker inspect`, la versión del motor, el digest y el host (loadavg,
  `/proc/meminfo`, kernel, nproc). Si una lectura falla, el campo queda en
  `null` y se anota en `errores`. Usa solo la biblioteca estándar.
- **`scripts/verify_limits.sh`** ya no lee nada por su cuenta: llama a
  `capture_env.py` y compara. Su `.json` es la captura completa más
  `esperado` y `coinciden`.
- **Pruebas:** `tests/test_capture_env.py`, 10 de 10 aprobadas con
  `python3 -m unittest discover -s tests -v`. Simulan Docker, así que no
  necesitan contenedores.

**Defecto encontrado en la versión anterior de `verify_limits.sh`.** El
informe se generaba dentro de `{ … } | tee`. En Bash ese bloque corre en un
subproceso, así que el `FAIL=1` de `check()` se perdía: el **código de salida
siempre era 0** y el JSON siempre decía `"coinciden": true`, aunque hubiera
discrepancias. Las líneas `OK`/`FALLA` y `RESULTADO:` sí eran correctas. Las
seis verificaciones anteriores siguen siendo válidas porque todas sus líneas
dicen `OK`, pero su exit 0 y su `coinciden: true` no prueban nada por sí
mismos. Corregido: el informe se escribe al archivo y se muestra después.

**Prueba negativa** (con salida fuera de `results/`, mediante `VERIFY_OUTDIR`):
contenedor en PROFILE_A verificado como `c_severe` → `FALLA` en `cpu.max` y
`memory.max`, exit 1 y `coinciden: false`. Con el contenedor parado,
`capture_env.py` sale con 2.

**Las seis verificaciones se repitieron con el código corregido**
(`PROFILE_*_20261101T1728*Z` y `…T1729*Z`, esquema `capture_env/1`). Todas
dieron exit 0, `errores=[]` y los mismos valores que las anteriores.

### 2026-11-01 — Imágenes fijadas por digest (después del cierre)

`docker/images.env` pasa de las etiquetas `mongo:8.2` y `postgres:18` a
`mongo@sha256:e0ce8c35…4bd3` y `postgres@sha256:3a426452…4b81`. La etiqueta
de origen queda en un comentario al final de la misma línea.

- `capture_env.load_env_file` ahora ignora ese comentario igual que Bash.
  Prueba nueva: `test_comentario_al_final_de_la_linea`; 11 de 11 aprobadas.
- Bash, Python y `docker compose config` resuelven la misma referencia.
- PROFILE_A se re-verificó en ambos motores: exit 0 y `.Config.Image` igual
  al digest. Evidencia: `PROFILE_A_BASELINE_mongodb_20261101T174228Z`,
  `PROFILE_A_BASELINE_postgresql_20261101T174244Z` y
  `up_a_baseline_*_digest.txt`.
