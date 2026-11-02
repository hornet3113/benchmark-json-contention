# F8 — Matriz completa (en curso, NO completada)

**Estado: plan aprobado por Alix el 2026-11-02**, con los dos añadidos (F8-b y
F8-c) y el orden por concurrencia. F8-b hecho; la matriz la corre Alix.

Qué cubre F8 (PLAN F8): recorrer la matriz con `scripts/run_benchmarks.sh`,
reanudable, hasta tener el CSV final del experimento. Es la fase que produce los
datos del reporte.

---

## Decisiones aprobadas (2026-11-02)

| # | Decisión |
|---|---|
| F8-a | Tras un fallo, el worker espera 1 s antes de reintentar. Motivo principal: **455 504 reintentos en 110 s son CPU del runner compitiendo con el motor dentro de la misma VM**, no el crudo de 19 MB. Hecho en F7 |
| F8-b | **Poder descartar y repetir una repetición**, con el motivo **obligatorio** y una **tabla de descartes en el reporte** (cero si no hubo): descartar tiene que ser visible y auditable, no silencioso. Queda como requisito **R-27.1** |
| F8-c | `results/logs/` con los casos `error` y `oom` correlacionados (R-32). **Al final**, cuando ya haya filas |
| F8-d | **Orden por concurrencia, no por perfil** (Alix): primero todo con c=1, luego c=10, luego c=50. Razón: si hay que parar a la mitad, quedan los dos motores y los tres perfiles con datos utilizables, en vez de dos perfiles completos y el tercero sin nada. Y c=50 es justo donde las filas salen `error`, `oom` o con el p95 contaminado |
| A2 | **Tanda 1 = Q1 + Q2_MEM_LOW** (36 celdas, 108 corridas), que es trabajo correcto conteste el docente 36 o 54. `run_benchmarks.sh` la corre por defecto |

## Costo medido en el piloto (F7.2), no estimado

| | Corridas | Tiempo | Espacio |
|---|---|---|---|
| **Tanda 1** (Q1 + Q2_MEM_LOW) | 108 | **13.4 h** | ~31 MB |
| Tanda 2 (Q2_MEM_HIGH), si el docente dice 54 | 54 | 6.7 h | ~16 MB |

448.5 s por repetición. El espacio no es un problema (951 GB libres) y 31 MB sí
caben en el repositorio.

## Bloques (F8-d): por concurrencia

```bash
scripts/up_monitoring.sh                                  # si no está arriba
scripts/run_benchmarks.sh --listar                        # qué falta, sin correr nada
scripts/run_benchmarks.sh --concurrencia 1 --max-celdas 6 # bloque 1: Mongo, c=1, los 3 perfiles
```

| Bloque | Comando | Celdas | Tiempo |
|---|---|---|---|
| 1 | `--concurrencia 1 --max-celdas 6` | Mongo, c=1, A/B/C × 2 queries | 2.2 h |
| 2 | `--concurrencia 1` | lo que falte de c=1 (Postgres) | 2.2 h |
| 3–4 | `--concurrencia 10` | los dos motores | 4.5 h |
| 5–6 | `--concurrencia 50` | los dos motores | 4.5 h |

Cada comando se puede relanzar: corre solo lo que falta. `--max-celdas N` corta
la sesión donde quieras.

**Paramos después del bloque 1 para revisar el CV y las tendencias** con datos
reales, antes de gastar las otras 11 h.

Ya no hace falta `sudo -v`: la regla de V7 cubre el flush. Antes de cada bloque:
cargador conectado, Windows sin suspender y no usar el equipo para nada más.

## Lo que hay que esperar y no confundir con fallos

- **Q1 con c=50 dará filas `error` y `oom`** (F7.3/F7.4): 92 % de timeouts en
  PROFILE_A, OOM en C, y en B puede no completarse ninguna consulta. Son
  resultados; el script no se detiene por ellas.
- **El p95 de c=50 en B y C viene contaminado** por la primera consulta en frío
  (hasta el 91 % de la ventana). Se declara y se muestran las dos vistas (F7-e, R-30.1).
- **El script sí se detiene** si 3 celdas seguidas fallan al ejecutarse, si la
  caché de sudo caduca, o si tras un OOM el dataset no tiene 500 000 filas (R-08).

## Criterios de aceptación (PLAN F8)

- [ ] Filas = celdas × 3 con el conteo de A2, sin combinaciones que falten ni repetidas.
- [ ] Todas las filas pasan `validate_csv.py`.
- [ ] Las celdas `error` tienen su log correlacionado en `results/logs/` (F8-c).
- [ ] Evidencia del flush en cada repetición (ya va en el crudo, con la vía usada).
- [ ] Los 12 planes de las celdas de c=1 (R-31).
- [ ] **R-27.1:** tabla de descartes con su motivo, o cero descartes.

---

## Registro de ejecución

### F8-b — Descartar una repetición para repetirla (2026-11-02)

**El agujero que tapa.** Si el equipo se suspende dentro de una ventana, el
runner lo detecta (F5-d) y escribe una fila `status=error`. Esa fila **ya
existe**, así que la reanudación da la repetición por hecha y **no la repite
nunca**: la matriz se queda con un agujero permanente. Editarla a mano está
prohibido (CLAUDE.md).

`scripts/descartar_repeticion.py`:

```bash
.venv/bin/python scripts/descartar_repeticion.py \
    --engine mongodb --profile PROFILE_C_SEVERE --query-id Q2_MEM_LOW \
    --concurrency 50 --run-number 2 \
    --motivo "el equipo se suspendió 4 min dentro de la ventana"
.venv/bin/python scripts/descartar_repeticion.py --listar
```

Con la condición de Alix —**visible y auditable, no silencioso**—:

1. **El motivo es obligatorio** y no puede estar vacío.
2. Copia el CSV a `measurements.csv.bak-<sello>` antes de tocarlo.
3. Anota la fila en `descartadas.csv` con el motivo, la fecha y quién lo pidió.
   Ese archivo **no se borra nunca**: es la tabla que va al reporte (R-27.1).
4. **Mueve** el crudo y la telemetría a `raw/descartadas/` y
   `telemetry/descartadas/`. La evidencia de lo que pasó no se borra.
5. Reescribe el CSV sin esa fila, copiando el encabezado y las demás líneas
   **tal cual**: ningún número se reformatea.

Después, `run_benchmarks.sh` la vuelve a ver como pendiente.

**Pruebas:** `tests/test_descartar.py`, 7 pruebas: el motivo obligatorio y el
motivo vacío no tocan nada; el descarte deja registro, mueve (no borra) crudo y
telemetría, y conserva el encabezado y las demás filas byte a byte; la
repetición vuelve a estar pendiente mientras la 1 sigue hecha; descartar dos
veces falla la segunda sin duplicar el registro; una clave inexistente no toca
nada; y `--listar` con cero descartes **dice cero**.

**Requisito nuevo:** R-27.1 en SPEC §2, con su casilla en CHECKLIST §2.

**Arreglo en `run_benchmarks.sh`:** `--max-celdas` solo cortaba al ejecutar, así
que `--listar` anunciaba las 12 celdas y 4.5 h aunque fueras a correr 6. Ahora
recorta la sesión antes de contar, y el listado dice lo que de verdad va a
correr, con una línea que avisa de cuántas quedan para la próxima.

**Pruebas tras F8-b: 292/292.**

### Arreglo: los scripts no conocían la regla de V7 (2026-11-02)

Alix lanzó el bloque 1 y el script se detuvo pidiendo `sudo -v`, aunque la regla
de V7 estaba instalada y el flush no necesita contraseña.

**Causa, y es un fallo mío:** al aplicar V7 arreglé la comprobación del runner
(`lifecycle.sudo_ready()`) pero no la de los scripts de Bash, que seguían con un
`sudo -n true` suelto. Con la regla instalada ese comando **sigue fallando**, y
debe fallar: el NOPASSWD cubre solo el ayudante, no todo `sudo`. Así que los
scripts pedían credenciales que ya no hacían falta.

Peor aún: `run_benchmarks.sh` repite esa comprobación **antes de cada celda**, de
modo que una matriz lanzada con la regla puesta se habría detenido en la primera.

**Arreglo:** `scripts/sudo_listo.sh`, cargado con `source`, con dos funciones:
`sudo_via` (devuelve `ayudante_v7`, `sudo_v` o `ninguna`) y `sudo_listo` (corta
con un mensaje que explica las dos opciones). Misma lógica que
`lifecycle.sudo_ready()`, en un solo sitio. Actualizados los 7 scripts que
tenían la comprobación: `run_benchmarks.sh` (la de arriba **y** la del bucle),
`run_pilot_f7.sh`, `run_cold_f73.sh`, `run_memory_f74.sh`, `smoke_f64.sh`,
`smoke_f55.sh` y `smoke_f55b.sh`.

Ahora cada corrida empieza diciendo por qué vía va: `== sudo para el flush: vía
ayudante_v7`. Si algún día se revierte la regla, la misma función detecta
`sudo_v` y vuelve a pedir `sudo -v`, sin tocar nada.

### Bloque 1 — Mongo, c=1, los tres perfiles (2026-11-02, 16:13–18:12 UTC)

`results/run_benchmarks_20261102T161337Z.txt`. 6 celdas, 18 repeticiones,
**0 fallos**, CSV `VÁLIDO`, 6 planes capturados (R-31). 2 h de reloj.

**Estabilidad: el entorno se porta mejor que en el piloto.**

| Celda (Mongo, c=1) | CV qps | CV p50 | Tendencia | qps | p50 (ms) | Throttling (reposo) | `max_rss_mb` |
|---|---|---|---|---|---|---|---|
| A · Q1 | 1.8 % | 1.5 % | no | 0.291 | 3 414 | 0 s (0.2) | 824 MiB |
| A · Q2_MEM_LOW | 2.0 % | 1.7 % | no | 0.730 | 1 352 | 0 s (0.2) | 832 MiB |
| B · Q1 | 0.7 % | 0.6 % | no | 0.261 | 3 818 | 13 s (3.6) | 812 MiB |
| B · Q2_MEM_LOW | 0.0 % | 1.0 % | no | 0.180 | 5 536 | 17 s (3.6) | 830 MiB |
| C · Q1 | 3.0 % | 1.5 % | no | 0.193 | 5 505 | 158 s (26.7) | 588 MiB |
| C · Q2_MEM_LOW | 0.0 % | 1.4 % | no | 0.053 | 19 329 | 183 s (26.7) | 612 MiB |

**Los 6 criterios se cumplen:** 3 repeticiones por celda, CV muy por debajo del
15 % (máximo 3.0 %) y **ninguna tendencia**. Todas las filas salieron `ok`.

**Primer resultado del experimento (M1), y es fuerte.** De PROFILE_A a PROFILE_C
con c=1, las dos queries del manual no se degradan igual en MongoDB:

- **Q1** (unwind + group): de 0.291 a 0.193 qps → **1.5 veces más lento**.
- **Q2** (sort top-K): de 0.730 a 0.053 qps → **13.7 veces más lento**.

En PROFILE_A, Q2 es 2.5 veces más rápida que Q1; en PROFILE_C es 3.6 veces más
lenta. La contención no castiga a las dos por igual, y eso es justo lo que M1
pregunta. Falta ver si Postgres hace lo mismo (bloque 2) y qué pasa con la
concurrencia (bloques 3–6) antes de interpretarlo en el reporte.

**Otras observaciones:**

- **`max_rss_mb` baja con el perfil** (830 → 600 MiB): WiredTiger dimensiona su
  caché según el límite del contenedor, así que en C usa menos memoria porque
  tiene menos, no porque necesite menos.
- **El throttling de C es casi todo del benchmark:** 158–183 s por ventana,
  frente a los ~27 s de reposo (F6.3). En B, 13–17 s frente a 3.6 s.
- **Sin spill en ninguna celda**, como se esperaba con c=1 (A12 y F4).
- **Baja densidad muestral en C · Q2** (16 muestras < 20; A4): declarada, no es
  un fallo.
- **Telemetría:** 0 fallos; 4 de 18 repeticiones perdieron **una** muestra de
  ~300 en las series del contenedor (el salto de 2 s de cAdvisor ya visto en
  F6.3 y F7.2). Quedan en `results/telemetria_eventos.jsonl`.
- **Espacio:** 796 KB de crudos y 4.6 MB de telemetría para 18 repeticiones; la
  tanda 1 completa cabe en ~30 MB, como se estimó.

### Herramienta nueva: `scripts/checks/check_matrix.py`

Se corre **después de cada bloque**, no solo al final: si el entorno se degrada a
mitad de las 13 h, se ve en el bloque siguiente y no cuando ya no hay remedio.
Por celda da el CV del throughput y del p50, la tendencia con el criterio F7-b,
el throttling con su línea base en reposo al lado, y los avisos (baja densidad,
percentiles invalidados por censura, suspensión de la VM, fallos de telemetría,
dataset no intacto). Del conjunto: cuántas corridas faltan, las filas
descartadas (R-27.1) y los planes capturados.

Las celdas con filas `error` u `oom` se marcan como **no medibles** y su CV se
informa sin exigirlo: con 4 muestras censuradas, un CV no significa nada (A4).

### Bloque 2 — Postgres, c=1, los tres perfiles (2026-11-02, 18:47–19:40 UTC)

`results/run_benchmarks_20261102T184722Z.txt`. 6 celdas, 18 repeticiones,
**0 fallos**, CSV `VÁLIDO`, 12 planes en total. Con esto, **c=1 está completo en
los dos motores y los tres perfiles**: 36 de 162 corridas.

| Celda (Postgres, c=1) | status | CV qps | CV p50 | Tendencia | qps | Throttling (reposo) |
|---|---|---|---|---|---|---|
| A · Q1 | spill ×3 | 1.5 % | 0.8 % | no | 0.132 | 0 s (0.0) |
| A · Q2_MEM_LOW | ok ×3 | **12.3 %** | 11.7 % | **decreciente −19.2 %** | 1.880 | 18 s |
| B · Q1 | spill ×3 | 0.0 % | 1.8 % | no | 0.110 | 146 s |
| B · Q2_MEM_LOW | ok ×3 | 0.9 % | 0.3 % | no | 1.089 | 550 s |
| C · Q1 | spill ×3 | 0.0 % | 1.5 % | no | 0.057 | 489 s (0.4) |
| C · Q2_MEM_LOW | ok ×3 | 4.7 % | 5.9 % | creciente +9.0 % | 0.572 | 871 s |

**Hallazgo grande: Q1 vuelca a disco en Postgres en los TRES perfiles**, también
en PROFILE_A. No es un caso extremo de c=50: ocurre con **una sola consulta a la
vez**. `status=spill` en las 9 repeticiones, y por ventana de 300 s:

| Perfil | `temp_bytes` | Archivos temporales | Consultas completadas |
|---|---|---|---|
| A | **+32.3 GB** | 600 | 40 |
| B | +27.5 GB | 510 | 33 |
| C | +13.7 GB | 255 | 17 |

Son ~0.8 GB de temporales **por consulta** (32.3 GB ÷ 40). Coincide con F3, donde
una sola ejecución de Q1 volcó 1.4 GiB. **M2 ya tiene respuesta con datos:** el
volcado existe, es masivo y sistemático en Postgres con Q1, y no aparece en
ninguna celda de Mongo.

**Comparación entre motores con c=1** (throughput medio de las 3 repeticiones):

| Perfil / query | Mongo | Postgres | Quién gana |
|---|---|---|---|
| A · Q1 | 0.291 | 0.132 | **Mongo ×2.2** |
| B · Q1 | 0.261 | 0.110 | **Mongo ×2.4** |
| C · Q1 | 0.193 | 0.057 | **Mongo ×3.4** |
| A · Q2 | 0.730 | 1.880 | **Postgres ×2.6** |
| B · Q2 | 0.180 | 1.089 | **Postgres ×6.0** |
| C · Q2 | 0.053 | 0.572 | **Postgres ×10.7** |

El resultado se parte por query, no por motor: **Mongo gana Q1 y Postgres gana
Q2**, y la diferencia **crece** al apretar los recursos en los dos casos. Falta
la concurrencia (bloques 3–6) antes de escribirlo en el reporte.

### La tendencia de Postgres · A · Q2_MEM_LOW: diagnóstico

Es la primera celda que incumple un criterio, y es exactamente lo que el criterio
F7-b existe para cazar: el CV (12.3 %) **pasa** el límite del 15 %, pero las tres
repeticiones bajan en orden y el cambio de r1 a r3 es del −19.2 %.

| | r1 | r2 | r3 |
|---|---|---|---|
| qps | 2.147 | 1.760 | 1.733 |
| p50 (ms) | 444 | 545 | 551 |
| Completadas en la ventana | 644 | 528 | 520 |
| **Tiempo de CPU en la ventana** | **1 142.7 s** | **1 141.1 s** | **1 142.0 s** |
| Flush (liberado) | 1 132 MB | 1 036 MB | 1 174 MB |

**El mismo tiempo de CPU produjo un 19 % menos de trabajo.** Eso descarta varias
causas: no es el flush (los tres liberaron lo mismo), no es throttling de cgroups
(17–20 s en los tres), no es memoria (sin swap ni presión) y no es que el motor
se quedara esperando disco (entonces habría gastado *menos* CPU, no la misma).

**No es una deriva dentro de la ventana, es un escalón entre r1 y r2.** Medianas
por tercio de ventana: r1 `435 → 448 → 453 ms`, r2 `526 → 555 → 558`, r3
`529 → 538 → 578`. r1 empieza rápido y acaba casi donde empieza r2.

**Y solo le pasa a la celda que satura las 4 CPUs.** Núcleos medios por celda:

| Celda | Núcleos usados | ¿Tendencia? |
|---|---|---|
| **Postgres A · Q2** | **3.81 de 4** | **sí, −19 %** |
| Postgres A · Q1 | 1.71 | no (0.133/0.130/0.133) |
| Postgres B · Q2 | 1.99 de 2 | no (1.080/1.100/1.087) |
| Postgres C · Q2 | 1.00 de 1 | no |
| Mongo A · Q2 | 1.24 | no |

**Hipótesis: el reloj del procesador baja.** Un Ryzen 5 PRO 5675U de portátil
(15–25 W) con cuatro núcleos saturados durante 20 minutos reduce la frecuencia
por potencia o temperatura. Encaja con todo: mismo tiempo de CPU, menos trabajo,
escalón al pasar de la repetición en frío a las siguientes, y solo donde hay
carga de 4 núcleos (las celdas de B y C no pasan de 2 y 1).

**No se puede comprobar desde WSL2:** no hay `cpufreq` en `/sys` y
`/proc/cpuinfo` informa siempre la frecuencia nominal (2295.613 MHz). **Windows
sí lo sabe**: `Win32_Processor` da `CurrentClockSpeed` (2010 MHz en reposo, con
un máximo de 2301). Por eso ahora hay `scripts/checks/monitor_cpu_clock.sh`, que
`run_benchmarks.sh` **arranca solo en cada sesión** (un único proceso de
PowerShell cada 15 s, con limpieza garantizada al salir) y deja
`monitor_clock_<sello>.csv` junto a los resultados, con el resumen al final de la
corrida. Desde el bloque 3, cada celda tendrá su contexto de frecuencia sin
costar un minuto extra. `--sin-reloj` lo desactiva.

### Bloque 3 — c=10, los dos motores (2026-11-02, 21:11–02:25 UTC)

`results/run_benchmarks_20261102T211151Z.txt`. 12 celdas, 36 repeticiones,
**0 fallos**, CSV `VÁLIDO`. **72 de 162 corridas** (c=1 y c=10 completos).

Todas las filas salieron `ok` o `spill`. Q1 de Postgres sigue volcando en los
tres perfiles, también con c=10. La estabilidad aguanta: de las 24 celdas, el
CV del throughput solo pasa del 10 % en dos (11.6 % y 12.3 %) y ninguna del 15 %.

**Dos avisos nuevos de tendencia, y ninguno es degradación.** Al mirarlos uno a
uno aparece un patrón que conviene entender antes de seguir:

| Celda | qps (r1→r3) | p50 (r1→r3) | Qué pasa |
|---|---|---|---|
| Postgres · A · Q2 · **c=1** | 2.147 → **1.733** (−19 %) | 444 → **551** (+24 %) | **Degradación real:** las dos métricas empeoran a la vez |
| Postgres · B · Q2 · c=10 | 1.043 → 1.197 (**+15 %**) | 8 299 → 6 801 (**−18 %**) | **Mejora**, no degradación: r1 es la lenta |
| Postgres · C · Q2 · c=10 | 0.607 → 0.607 (**0 %**) | 10 496 → 13 859 (+32 %) | El throughput **no cambia** y el p95 tampoco (28 901 → 28 890 ms): se movió la mediana dentro de una distribución con la misma cola |

En bucle cerrado con 10 workers, el throughput depende de la latencia **media**,
no de la mediana: el p50 puede moverse un 32 % con el throughput y el p95
clavados, porque la distribución se reparte distinto. Eso no es que la celda
mida peor, y mezclarlo con la degradación real tapa la señal que importa.

Y la celda que **mejora** (B · Q2 · c=10, r1 la más lenta) apunta a la otra cara
de lo ya documentado en A5/L4: `drop_caches` limpia la caché de la VM, pero **no
la de Windows sobre el `.vhdx`**. La primera repetición de una celda lee del
disco virtual en frío; las siguientes se aprovechan de la caché de Windows. El
estado de partida es repetible, no frío, y está declarado.

**Propuesta (F8-e), pendiente de tu aprobación.** Que el criterio de aceptación
sea la **tendencia del throughput**, y que la del p50 se informe como
observación que hay que explicar cuando aparezca. Motivo: lo que pediste cazar
es la degradación progresiva, y una celda cuyo throughput y cuyo p95 no se
mueven no se está degradando. Con este criterio, de las 24 celdas **solo se
marca la de siempre** (Postgres · A · Q2 · c=1), que es justo la que tiene las
dos métricas empeorando a la vez. No cambia nada de lo medido: solo qué se
considera incumplimiento. Mientras no lo apruebes, el analizador sigue marcando
las tres.

### El muestreador de frecuencia estaba midiendo un valor clavado

El de la sesión del bloque 3 dio **2010 MHz en las 1008 muestras**, con 4 h de
carga incluidas. No es que el reloj no se moviera: **`Win32_Processor.
CurrentClockSpeed` está clavado en esta máquina** y no sirve para esto. Fallo del
instrumento, no de la hipótesis.

El indicador que sí varía es el contador de rendimiento **"% de rendimiento del
procesador"** (`% Processor Performance`): el porcentaje de la frecuencia nominal
al que va de verdad. En reposo da 80.7–84.7 %, es decir **1 853–1 944 MHz** de
los 2 295 nominales, mientras WMI insiste en 2010.

`scripts/checks/monitor_cpu_clock.sh` reescrito: muestrea ese contador, estima
los MHz y guarda también el valor de WMI y la carga, para que se vea que uno se
mueve y el otro no. Tres detalles del entorno que hubo que resolver:

- el contador está **traducido** ("Información del procesador"), así que se busca
  por expresión regular y funciona igual en inglés;
- la **política de ejecución de scripts de PowerShell está deshabilitada** en
  esta máquina, así que el código va con `-EncodedCommand` en vez de un `.ps1`
  (no se toca la política);
- el bucle vive dentro de PowerShell y sobrevivía al `kill`; ahora hay una
  trampa de limpieza, comprobada.

Las columnas `mhz_wmi` de los bloques ya corridos quedan como están, con su
valor inútil declarado aquí. Desde el bloque 4 hay dato real.

### Bloque 4 — c=50, los dos motores (2026-11-03, 02:46–08:00 UTC)

`results/run_benchmarks_20261103T024628Z.txt`. **8 celdas completas y 1
detenida**: 26 filas nuevas, 98 de 162 corridas. CSV `VÁLIDO`. A la tanda 1 le
faltan **10 repeticiones (~1.2 h)**, todas de Postgres con c=50.

**La matriz se detuvo sola, y fue una FALSA ALARMA mía.** En
`postgresql · B · Q1 · c=50 · r2` el OOM mató backends y Postgres entró en
**recuperación** (rehace su WAL). El recuento del dataset, que corre justo
después, recibió `FATAL: the database system is in recovery mode`, y mi
implementación trataba "no se puede contar" como "dañado": detuvo la matriz
pidiendo recargar el dataset.

**El dataset estaba intacto.** Comprobado después en los dos motores:

```
postgresql: 500000 de 500000 filas (1.73 s)
mongodb:    500000 de 500000 filas (4.33 s)
```

No se recargó nada. La fila `oom` de r2 **se conserva**: es una medición válida
(un OOM es un resultado). Lo único equivocado era el motivo añadido al crudo, y
queda explicado aquí.

**Arreglo:** `count_dataset` ahora **reintenta** mientras el motor no conteste
(hasta 90 s, cada 5 s) y solo decide cuando responde. Un motor en recuperación no
es un dataset dañado. Si al final no contesta, se para igual: no se puede
afirmar que esté bien. Pruebas: `tests/test_pilot_f7.py::CountRetryTest` (motor
que falla dos veces y luego cuenta 500 000 → intacto; recuento distinto → daño
sin reintentar; motor que nunca contesta → se detiene).

**La frecuencia del procesador sí baja, y mucho.** Primer bloque con el
muestreador bueno, 632 muestras: **media 81.7 %, mínimo 60.8 %**, es decir
**1 877 MHz de media y 1 396 MHz en el peor momento**, de 2 296 nominales. El
resumen que imprimió la corrida decía "media 82 MHz" porque el `awk` leía la
columna del porcentaje y la llamaba MHz; corregido.

**Dos celdas incumplen el CV, y no tienen la misma causa.** Cruzando cada
ventana de medición con el reloj:

| | r1 | r2 | r3 | CPU en la ventana | Rendimiento del procesador |
|---|---|---|---|---|---|
| **Postgres · A · Q2 · c=50** | 1.833 | 1.697 | **1.207** (−34 %) | 1 197 s en las tres | 75.9 % → 75.7 % → **65.2 %** |
| **Mongo · B · Q2 · c=50** | 0.477 | **0.323** | 0.320 (−33 %) | 598.6 s en las tres | 83.4 % → 81.7 % → 84.6 % |

- En la de **Postgres** el reloj cae con el throughput: de 75.9 % a 65.2 % justo
  en la repetición que pierde el 34 %. La frecuencia explica **parte** (−14 %),
  no todo, pero va en la misma dirección y es la única variable que se mueve.
- En la de **Mongo**, el reloj está plano (83.4 / 81.7 / 84.6) y el tiempo de CPU
  es idéntico: **el mismo CPU, a la misma frecuencia, produjo un 33 % menos de
  trabajo entre r1 y r2.** Esa causa **no está identificada**. Lo que queda fuera
  del alcance de `drop_caches` —la caché de Windows sobre el `.vhdx` (A5, L4)— es
  el sospechoso natural, pero no hay medición que lo demuestre.

**Y no hay sesgo sistemático de "la primera repetición es más rápida":** r1 es la
más rápida en **6 de 30** celdas medibles, cuando por azar serían ~10. Así que
las dos celdas de arriba son sucesos puntuales, no un defecto del protocolo.

**Otras lecturas del bloque:**

- `postgresql · A · Q1 · c=50`: `error` ×3 con **CV del 173 %**. Es lo previsto en
  F7.4 (92 % de timeouts): con 2–4 consultas completadas, el throughput es ruido
  y el analizador marca la celda como **no medible**, sin exigirle criterios.
- `mongodb · C · Q1 · c=50`: `error` ×3, también previsto (F7.3: ninguna consulta
  termina en PROFILE_C con c=50).
- `postgresql · B · Q1 · c=50`: **`oom` ×2** con `spill=true` y 1 791 MiB de RSS.
  Segunda evidencia de OOM en una query del manual, ahora en PROFILE_B, no solo en C.
- Mongo con c=50 en PROFILE_C **no dio OOM** (pendiente abierto desde F5): la
  celda de Q2 salió `ok` ×3 con CV 0 %.

### Bloque 5 — las 10 corridas que faltaban (2026-11-03, 08:24–09:40 UTC)

`results/run_benchmarks_20261103T082456Z.txt`. 4 celdas, 10 repeticiones,
**0 fallos**. El recuento del dataset tras cada OOM funcionó con el arreglo del
reintento: ninguna parada en falso.

| Celda (Postgres, c=50) | status | qps | CV |
|---|---|---|---|
| B · Q1 | `oom`, `oom`, `error` | 0.013 ×3 | 0 % |
| B · Q2_MEM_LOW | `ok` ×3 | 0.953 / 1.127 / 1.087 | 8.6 % |
| C · Q1 | **`oom` ×3** | **0.000** ×3 | — |
| C · Q2_MEM_LOW | `ok` ×3 | 0.563 / 0.567 / 0.553 | 1.2 % |

**`postgresql · C · Q1 · c=50` no completó ni una consulta en las 3
repeticiones**: throughput 0.000 y `oom` en todas. Es el extremo del
experimento: 50 clientes haciendo `$unwind` sobre 500 000 documentos con 1 CPU y
1 GiB. Con `throughput_qps = 0` y las latencias vacías, la fila dice exactamente
lo que pasó (A4), sin inventar nada.

Frecuencia de la sesión: media 83.7 %, mínimo 60.9 % (1 922 y 1 398 MHz).

## TANDA 1 COMPLETA — 108 de 108 corridas (2026-11-03)

`results/measurements.csv`: **108 filas, 36 celdas, `VÁLIDO`** con
`--expect-rows 108`. Ninguna combinación falta ni está repetida. **Cero
descartes** (R-27.1).

| `status` | Filas |
|---|---|
| `ok` | 78 |
| `spill` | 18 |
| `error` | 7 |
| `oom` | **5** |

24 filas con `disk_spill=true` (las 18 de `status=spill` más 6 donde `oom` o
`error` tienen precedencia). **Las 24 son de Postgres con Q1**; ninguna de Mongo.

**Estado de los criterios de aceptación de PLAN F8:**

- 108 filas con el conteo de A2 (tanda 1), sin faltar ni duplicar: **cumplido**.
- Todas pasan `validate_csv.py`: **cumplido**.
- Evidencia del flush en cada repetición, con su vía: **cumplido**.
- Planes de las celdas de c=1 (R-31): 12 archivos en `results/explains/`: **cumplido**.
- Logs correlacionados de las filas `error`/`oom` en `results/logs/`: **pendiente (F8-c)**.

**Seis celdas medibles incumplen algún criterio de estabilidad**, todas de
`Q2_MEM_LOW`: dos por CV (24.0 % y 20.9 %, las dos analizadas en el bloque 4) y
cuatro solo por la tendencia del p50, que es lo que F8-e propone dejar como
observación. Las demás 24 celdas medibles cumplen.

### F8-c — Logs de spill y OOM correlacionados (2026-11-04)

`scripts/build_logs_f8c.py` escribe una ficha por repetición afectada en
`results/logs/`, más un `README.md` con la tabla índice. Cubre R-32 ("capturas o
logs de spill/OOM como evidencia") y la casilla de PLAN F8 ("las celdas con
`status=error` tienen su log correlacionado").

Entran las repeticiones con `status` `error` u `oom` **y** las que tienen
`disk_spill=true` aunque el status sea otro, porque la precedencia
`oom` > `error` > `spill` puede tapar un volcado: **30 de las 108 filas**.

Cada ficha lleva la fila del CSV entera, los motivos, la censura de A4, los
contadores de OOM y de volcado, el estado del contenedor, el flush con su vía,
la telemetría, `working_set` y `shmem` de la serie de 1 s, ejemplos de error del
motor y punteros a la evidencia original. **No mide ni inventa nada**: se
regenera del CSV y de `results/raw/`, así que no es una fuente de datos.

**Dos lecturas que las fichas ahora advierten, porque es fácil citarlas mal:**

1. **El OOM puede haber ocurrido antes de la ventana.** En 3 de las 5 filas `oom`
   el contador `oom_kill` del cgroup **no se movió durante la ventana**: el motor
   se quedó sin memoria durante el calentamiento. Como el contenedor se recrea en
   cada repetición, la marca `OOMKilled` sí es de esa repetición.
2. **Con 0 consultas completadas, las columnas de recursos describen un motor ya
   colapsado.** En `postgresql · C · Q1 · c=50`, la fila dice
   `cpu_throttled_seconds=0.035` y `max_rss_mb=8.2`. Eso **no** es "Postgres
   consumió 8 MiB atendiendo 50 clientes": es que durante la ventana el motor no
   estaba trabajando, y los ~15 000 "errores" son conexiones rechazadas, no
   consultas ejecutadas. Citarlo sin esta nota sería engañoso.
