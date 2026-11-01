# F7 — Celda piloto y validación del CSV (en curso, NO completada)

**Estado: plan aprobado por Alix el 2026-11-02.** F7.1 hecha; F7.2–F7.4 las
corre Alix (necesitan sudo). Es la última puerta antes de F8.

Qué cubre F7 (PLAN F7, exigido por la diapo 13/13): correr una celda real
completa —**MongoDB × PROFILE_C_SEVERE × Q2_MEM_LOW × c=1**, ventanas reales
60/300/60 y 3 repeticiones— y después la misma en Postgres, para decidir si el
entorno es lo bastante estable como para gastar ~20 h en la matriz.

---

## Decisiones aprobadas (2026-11-02)

| # | Decisión |
|---|---|
| F7-a | Las filas del piloto van a **`results/f7/`**, no a `results/measurements.csv`. La CLI gana `--salida DIR` (solo en corridas reales). Motivo: si después hay que ajustar algo, el CSV de la matriz no mezcla condiciones. En F8 la matriz se corre completa, piloto incluido |
| F7-b | **Tendencia = monotonía Y tamaño**: las 3 repeticiones en orden monótono **y** un cambio de r1 a r3 de más del **10 %**, en throughput o en p50. Con 3 valores, el orden monótono sale por azar 1 de cada 3 veces (2 de los 6 órdenes posibles), así que la monotonía sola no distingue ruido de deriva. El caso de Alix (100-110-120: CV 9 %, deriva 20 %) sí se detecta |
| F7-c | **Primera consulta en frío en A y B:** con el propio runner en humo, calentamiento de 60 s (`--ventanas 60 30 5`) y **c=50** (el peor caso), para 3 perfiles × 2 motores × 3 queries = **18 corridas, ~45–60 min**. PROFILE_C con c=1 lo da el piloto. Mismo procedimiento que la matriz (flush, arranque, calentamiento); el crudo ya guarda las consultas del calentamiento |
| F7-d | **Memoria con la ventana real en PROFILE_A** (casilla que F6 pasó a F7): una repetición de humo 60/300/60 de Q1 con c=50 por motor (~16 min), para ver `MemAvailable` de la VM y cuánto ocupa Prometheus con la ventana larga en el perfil de menos margen |

**Antes de cada corrida, en el host:** cargador conectado y "Suspender: nunca"
(reversible). Con batería, Windows baja la frecuencia del procesador y eso
puede crear justo la tendencia que F7-b busca descartar. En el humo de F6.4 el
registro decía "batería estado=1" (descargando, 77 %) y plan "Equilibrado". Los
scripts dejan anotados la batería y el plan de energía.

---

## Pasos y criterios

| Paso | Qué | Evidencia |
|---|---|---|
| **F7.1** | `--salida` en la CLI; `scripts/run_pilot_f7.sh`; `scripts/checks/check_pilot_f7.py`; pruebas | Hecho, abajo |
| **F7.2** | **Alix corre el piloto** (~50 min) | `results/f7/` |
| **F7.3** | **Alix corre** el barrido de primera consulta en frío (F7-c) | `results/f7/frio/` |
| **F7.4** | **Alix corre** la ventana larga en PROFILE_A (F7-d) | `results/f7/memoria_a/` |
| **F7.5** | Estimación del costo de F8 y cierre en este documento | Lo revisa Alix antes de tocar PLAN |

---

## Registro de ejecución

### F7.1 — Herramientas del piloto (2026-11-02)

**`--salida DIR` en la CLI (F7-a).** Solo en corridas reales; con `--smoke` da
error. Acepta un nombre simple de subcarpeta de `results/`: rechaza rutas
(`a/b`, `../x`, `/tmp`), `.` y lo vacío, para que una medición real no pueda
escribir fuera de `results/`. El CSV, los crudos, los planes y la telemetría van
todos a esa carpeta.

**`scripts/run_pilot_f7.sh`.** Mongo primero y luego Postgres, como pide PLAN
F7; `--runs 1 2 3`; monitor del host por motor; al final `validate_csv.py` y el
analizador. Necesita `sudo -v` (V7: nada permanente).

**`scripts/checks/check_pilot_f7.py`.** Por motor:

- 3 filas con `run_number` 1, 2 y 3;
- **CV del throughput < 15 %**;
- **sin tendencia** en throughput ni en p50 (F7-b);
- plan capturado (R-31);
- flush con efecto medido (A5), sin suspensión de la VM (F5-d) y telemetría sin fallo (F6);
- **tiempo real por repetición** → estimación de F8, medido como la diferencia
  entre los `inicio_utc` de dos repeticiones consecutivas **del mismo motor**
  (el salto de un motor al otro incluye el monitor del host y falsearía el dato);
- **primera consulta en frío** de cada worker frente al calentamiento;
- el throttling de la fila junto a la **línea base en reposo** de F6.3, normalizada a 300 s.

Avisos que se declaran y **no** bloquean: baja densidad muestral (A4), una
primera consulta en frío que no cabe en el calentamiento (limitación del
protocolo) y workers cortados al final (consulta huérfana, pendiente F7/F8).

**Pruebas:** `tests/test_pilot_f7.py`, 14 nuevas; suite completa **264/264**
(`results/f7/tests_f71_20261102T111349Z.txt`). Cubren el caso de Alix
(100-110-120: CV 9 % y tendencia detectada), la degradación de la sonda de Mongo
(31 → 62 → 161 s), que la monotonía pequeña no cuenta, que un cambio grande no
monótono tampoco, y la primera consulta en frío por worker (incluido un worker
que nunca terminó ninguna).

**Ensayo en seco del analizador** (fuera de `results/`, en el directorio
temporal de la sesión): con los crudos del humo de F6.4 duplicados a 3
repeticiones y un throughput creciente a propósito (+21 % de r1 a r3), el
analizador marcó `sin_tendencia_throughput: false` y dio **480 s por
repetición → 21.6 h** para 162 corridas. Dos fallos encontrados así y
corregidos: el tiempo por repetición se calculaba mezclando los dos motores (daba
0 s) y el mensaje final nombraba una ruta fija.

**Dato para F7.5:** el PLAN estima ~19 h para F8 contando solo las ventanas.
Con el sobrecosto real por repetición (~60 s de flush, arranque, healthcheck y
plan) sale **~21–22 h**. El número definitivo saldrá del piloto, no del ensayo.

### Lo que ya se puede anticipar del piloto

- **Mongo saldrá con "baja densidad muestral".** En el humo, Q2 en PROFILE_C con
  c=1 tardaba ~20 s por consulta: en 300 s son ~15 completadas, por debajo del
  umbral de 20 (A4). No es un error; se marca, y el p99 de 15 muestras se
  declara poco fiable. Postgres, con ~1.6 s, tendrá ~180.
- **Parte del throttling de Mongo no es del benchmark:** ~27 s por cada 300 s en
  reposo (línea base de F6.3). El analizador los pone uno al lado del otro.
- **Si el CV o la tendencia fallan, no se pasa a F8:** primero se busca la causa
  (caché, memoria de la VM, térmico, energía).

### F7.2 — Celda piloto corrida por Alix (2026-11-02, 11:18–11:59 UTC)

`results/f7/pilot_20261102T111824Z.txt`, `results/f7/check_pilot.json`.
Cargador conectado (batería estado=2, 99 %), plan "Equilibrado". Ventanas
60/300/60, 3 repeticiones por motor, 6 filas en `results/f7/measurements.csv`.
`validate_csv.py`: **VÁLIDO**.

| Motor | qps (r1/r2/r3) | CV qps | Tendencia | p50 (ms) | CV p50 | Completadas | Throttling (s) | `max_rss_mb` (MiB) |
|---|---|---|---|---|---|---|---|---|
| MongoDB | 0.0433 / 0.0467 / 0.0467 | **4.2 %** | no | 22 587 / 21 075 / 21 831 | 3.5 % | 13 / 14 / 14 | 204 / 193 / 193 | 616 / 624 / 613 |
| PostgreSQL | 0.5033 / 0.5233 / 0.5433 | **3.8 %** | no (creciente, +7.9 % < 10 %) | 1 900 / 1 807 / 1 804 | 3.0 % | 151 / 157 / 163 | 858 / 861 / 853 | 16.4 / 16.8 / 17.9 |

**Los 8 criterios se cumplen en los dos motores:** 3 filas r1–r3, CV < 15 %, sin
tendencia en throughput ni en p50, plan capturado (R-31), flush con efecto
medido (de 695 MB a 1 843 MB liberados por repetición), sin suspensión de la VM,
y telemetría sin fallo.

**Sobre la tendencia (F7-b).** Postgres sí salió monótono creciente en
throughput y decreciente en p50, pero el cambio de r1 a r3 es del 7.9 % y del
−5.1 %, por debajo del umbral del 10 %. Es el caso que el umbral existe para no
confundir con deriva: con 3 valores, el orden monótono sale por azar 1 de cada 3
veces. Aun así hay que mirarlo en F8, porque los dos indicadores apuntan al
mismo lado (va mejorando, probablemente caché del sistema de archivos que el
flush no alcanza, o calentamiento de la VM).

**Tiempo real: 448.5 s por repetición** (mediana entre repeticiones del mismo
motor), 28.5 s más que las ventanas. **Estimación de F8: 20.2 h** con 162
corridas y 13.5 h con 108. El PLAN decía ~19 h contando solo las ventanas. Es de
PROFILE_C con c=1; con c=50 el arranque y el corte de workers pueden subirlo.

**Primera consulta en frío (PROFILE_C, c=1):** Mongo 32.9 / 27.5 / 28.2 s y
Postgres 4.4 / 3.3 / 3.3 s, **todas dentro del calentamiento de 60 s**. En esta
celda los P95/P99 no están contaminados, y los tres percentiles son válidos
según la censura (A4). Para A y B queda F7.3.

**Throttling frente a la línea base en reposo (F6.3):** Mongo 193–204 s por
ventana, de los que ~27 s son de reposo (13 %). Postgres 853–861 s, con 0.4 s de
reposo. **Postgres acumula 4 veces más throttling que Mongo con 1 CPU de cuota**
porque Q2 le lanza 2 workers paralelos: 3 procesos en 3 CPUs contra la cuota de
una, y el tiempo de throttling se suma por CPU (SPEC §4). No es que Postgres sufra
más: es que pide más paralelismo. Va al reporte junto a la figura de throttling.

**Baja densidad muestral en Mongo, como estaba previsto:** 13–14 consultas
completadas en la ventana, por debajo de 20 (A4). Se marca en el log y en el
crudo. Postgres tuvo 151–163.

**Gracia y enfriamiento frente a la latencia (pendiente de F5, resuelto para
esta celda).** En Mongo r1 y r3, un worker quedó cortado al final. Secuencia
real: la ventana cierra, los workers **siguen** en bucle durante el enfriamiento
(60 s), y al terminarlo hay 15 s de gracia; una consulta de ~21 s no cabe en esos
15 s, así que el worker se corta y su consulta queda en el servidor. La última
muestra registrada terminó 59.6 s después del cierre de la ventana, ya en el
enfriamiento. **No contamina nada:** no entra en la ventana (A4) y cada
repetición empieza con `stop_engines` + flush + contenedor nuevo
(`lifecycle.prepare`), así que la consulta huérfana muere con el contenedor
anterior. Hay que volver a comprobarlo con c=50 en F8.

**Huecos de telemetría en r3 de los dos motores (marcados, no fallo).** Las 7
series del contenedor perdieron **una** muestra (hueco de 2.0 s en 300); las del
host, ninguna. Causa: cAdvisor se saltó una lectura de ese cgroup. No fue falta
de recursos: en esas ventanas cAdvisor no tuvo throttling (0.0 s) y su scrape
máximo fue de 0.02–0.04 s. Es el 0.3 % de las muestras, y las columnas del CSV
salen del cgroup, no de aquí. Quedó en `results/f7/telemetria_eventos.jsonl` con
la memoria de la VM (4.6–5.1 GiB disponibles, sin presión), que es justo lo que
F6-f pedía para distinguir un hueco inocuo de uno por presión de memoria.

**Dos fallos de mi analizador, encontrados con los datos reales y corregidos:**

1. `plan_capturado` exigía plan en las 3 repeticiones. Por diseño de F5 (R-31)
   se captura **uno por celda**, en la repetición 1 de c=1. Ahora comprueba que
   exista el archivo de alguna repetición y que ninguna tenga `plan_error`.
2. `cabe_en_el_calentamiento` daba falso negativo si algún worker quedaba
   cortado **al final** de la ventana, algo que no dice nada de la primera
   consulta. Ahora solo cuenta un worker que no terminó **ninguna** consulta.
   Por eso el primer análisis avisaba de que 32.91 s "no cabía" en 60 s.

Con las correcciones, el analizador da **CUMPLE** en los dos motores.
Pruebas: 19 en `tests/test_pilot_f7.py` (4 nuevas para el criterio del plan y 1
para el worker cortado al final); suite completa **269/269**
(`results/f7/tests_f72_20261102T120658Z.txt`).

### Herramientas de F7.3 y F7.4 (2026-11-02)

**Cambio en `--salida`:** ahora también vale con `--smoke`, y en ese caso el CSV
sigue llamándose `measurements_smoke.csv`, así que un CSV de humo nunca se
confunde con uno real. Hacía falta porque F7.3 y F7.4 son corridas de humo con
ventanas propias que no deben pisar `results/smoke/`. Sigue rechazando rutas,
`.` y lo vacío. Carpetas: **`results/f7_frio/`** y **`results/f7_memoria/`** (la
CLI solo acepta un nombre simple, sin barras, así que no son subcarpetas de `f7/`).

**F7.3 — `scripts/run_cold_f73.sh` y `scripts/checks/check_cold_f73.py`.**
3 perfiles × 2 motores × 3 queries con **c=50** (el peor caso: 50 primeras
consultas en frío a la vez), ventanas **60/30/5**: el dato está en el
calentamiento, no en la ventana. Cada corrida lleva el procedimiento real
(flush, contenedor nuevo, calentamiento de 60 s). El analizador da, por celda:
duración de la primera consulta de cada worker (mediana y máximo), cuántas pasan
del calentamiento, cuántas **terminan dentro de la ventana** —las que contaminan
los percentiles—, qué fracción de la ventana son, y el p95/p99 de la fila frente
al recalculado **sin** las primeras consultas, que es lo que mide cuánto se
desplazan.

**F7.4 — `scripts/run_memory_f74.sh`.** Una repetición por motor de **Q1 con
c=50 en PROFILE_A** y ventanas **reales 60/300/60**: la query que más memoria
mueve, en el perfil con menos margen. Reutiliza `check_smoke_f64.py`, que ahora
acepta la carpeta como argumento, y añade el mínimo de memoria disponible, el
máximo de swap y el RSS del árbol del runner, del monitor del host.

**Ensayo en seco del analizador de F7.3** (en el directorio temporal de la
sesión, con los crudos del humo de F6.4 y del piloto): destapó **un fallo real
mío**. Calculaba las duraciones en milisegundos y las comparaba con los 60
**segundos** del manual, así que todas las celdas salían "NO CABE", incluidas
las de 3.3 s. Corregido y fijado con una prueba de unidades
(`ColdSweepUnitsTest`). Con la corrección, el ensayo deja ver el fenómeno que
F7.3 va a medir: en el humo de F6.4 (PROFILE_A, c=50, calentamiento de **30 s**),
la primera consulta tardó 35.9 s en Mongo y 43.5 s en Postgres; **el 17 % de las
consultas de la ventana eran primeras consultas**, y el p95 de Mongo pasó de
25 243 ms sin ellas a 34 048 ms con ellas, un 35 % más. Con el calentamiento
real de 60 s puede que quepan; eso es justo lo que hay que medir.

**Pruebas:** 270/270 (`results/f7/tests_f73_herramientas_20261102T122357Z.txt`).

### Lo que falta correr

```bash
cd ~/benchmark-json-contention
scripts/up_monitoring.sh      # si no está arriba
sudo -v
scripts/run_cold_f73.sh       # F7.3, ~45 min (puede pasar de 1.5 h si hay timeouts)
scripts/run_memory_f74.sh     # F7.4, ~16 min
```

En F7.3, un timeout de 300 s en la primera consulta (posible con Q1 y c=50 en
PROFILE_C) **no es un fallo**: es el hallazgo, y la celda sale con
`status=error`, que en humo no cuenta.

### F7.3 — Primera consulta en frío por perfil y motor (2026-11-02, 12:28–13:11 UTC)

`results/f7_frio/frio_20261102T122820Z.txt`, `results/f7_frio/check_cold.json`.
18 celdas, c=50, ventanas 60/30/5. **La respuesta es sí: la primera consulta en
frío supera los 60 s de calentamiento en casi todas las celdas con c=50.**

Solo cabe en **4 de 18**, todas en PROFILE_A y con Q2:

| Celda (c=50) | 1ª consulta máx. | Mediana | ¿Cabe en 60 s? |
|---|---|---|---|
| Mongo · A · Q2_MEM_HIGH | 39.4 s | 36.9 s | sí |
| Postgres · A · Q2_MEM_HIGH | 41.2 s | 34.8 s | sí |
| Mongo · A · Q2_MEM_LOW | 41.3 s | 38.3 s | sí |
| Postgres · A · Q2_MEM_LOW | 52.3 s | 43.8 s | sí, al filo |
| Postgres · B · Q2_MEM_HIGH | 69.1 s | 58.5 s | **no** |
| Postgres · B · Q2_MEM_LOW | 75.3 s | 63.9 s | **no** |
| Postgres · C · Q2_MEM_LOW | 109.4 s | 101.1 s | **no** |
| Postgres · C · Q2_MEM_HIGH | 110.3 s | 98.9 s | **no** |
| Mongo · A · Q1 | 102.2 s | 100.6 s | **no** |
| Postgres · C · Q1 | 90.5 s | 89.5 s | **no** (además OOM, abajo) |
| Mongo · B y C × las 3 queries (6 celdas) | **> 110 s** | — | **no** |
| Postgres · A · Q1 y B · Q1 | **> 110 s** | — | **no** |

En las 8 celdas de "> 110 s" no terminó **ninguna** consulta: los 50 workers
quedaron con su primera consulta en vuelo cuando se agotaron calentamiento +
ventana + enfriamiento + gracia (110 s). No hubo errores ni timeouts y el motor
siguió sano: solo es que tardan más que toda la corrida. Es una cota inferior,
no una medida. Para PROFILE_A de Postgres con Q1, F7.4 la midió de verdad: **~260 s**.

**Cuánto contamina los percentiles.** Lo que importa no es solo que no quepa,
sino qué fracción de la ventana son primeras consultas:

| Celda | % de la ventana que son 1ª consulta | p95 de la fila | p95 sin las 1ª |
|---|---|---|---|
| Postgres · B · Q2_MEM_LOW | **81.6 %** | 73 743 ms | 44 348 ms |
| Postgres · B · Q2_MEM_HIGH | **77.8 %** | 68 719 ms | 26 733 ms (−61 %) |
| Postgres · C · Q2_MEM_HIGH | **90.9 %** | 88 840 ms | sin muestras suficientes |
| Postgres · C · Q2_MEM_LOW | 63.6 % | 85 047 ms | 42 349 ms |
| Mongo y Postgres · A · Q2 | 0 % | — | igual |

Con c=50 en B y C, **la ventana de medición mide sobre todo consultas en frío**,
no el régimen estacionario que el manual quiere medir. En PROFILE_A con Q2 no hay
contaminación ninguna.

**Hallazgo nuevo: OOM real en Postgres · C · Q1 · c=50.** `status=oom`,
`oom_kill +3`, `OOMKilled=true`. El kernel mató backends de Postgres al pasar de
1 GiB. **Es la primera evidencia de OOM en una query del manual** (hasta ahora
solo había sondas), y responde M2 con datos. Detalle en
`results/f7_frio/raw/postgresql_PROFILE_C_SEVERE_Q1_c50_r1.json`.

### F7.4 — Memoria con la ventana real en PROFILE_A (2026-11-02, 13:11–13:27 UTC)

`results/f7_memoria/memoria_20261102T131116Z.txt`. Q1 con c=50, ventanas reales
60/300/60. `check_smoke_f64.py`: **TODO CUADRA** (serie de 1 s igual a
`max_rss_mb`, telemetría completa sin huecos, throttling columna/Prometheus al
0.2 %).

| | Mongo | Postgres |
|---|---|---|
| `status` | ok | **error** (92 % de timeouts) |
| `max_rss_mb` (anon) | 1 046 MiB | 1 977 MiB |
| `working_set` | 1 270 MiB | **2 936 MiB** (`shmem` 211) |
| Throttling en 300 s | 1 188 s | 1 032 s |
| `MemAvailable` mínima de la VM | 4 391 MiB | **3 217 MiB** |
| Presión de memoria (PSI, espera) | 0 s | **120 s de 300** |
| Páginas enviadas a swap | 0 | 0 |
| RSS del árbol del runner | 442 MiB | 472 MiB |
| Monitoreo | 0.075 núcleos, ≤ 105 MiB | 0.083 núcleos, ≤ 103 MiB |

**La memoria aguanta, pero con menos margen del que parecía:** nunca se usó
swap, y quedaron 3.2 GiB libres en el peor caso. Eso sí, **la VM pasó 120 de los
300 s en espera por memoria** (reclamando caché de páginas) en la celda de
Postgres. El monitoreo no es el problema: cuesta menos de 0.09 núcleos y ~105 MiB.

**Dos hallazgos reales de esa celda (Postgres · A · Q1 · c=50):**

1. **Spill masivo:** `disk_spill=true`, `temp_bytes` **+37.2 GB** en 380 archivos
   temporales durante la ventana. En F3, Q1 con una sola consulta volcaba 1.4 GiB;
   con 50 concurrentes son 37 GB. Responde M2 con datos.
2. **92 % de timeouts:** 46 de 50 consultas agotaron el límite de 300 s y solo 4
   terminaron. Por A4 la fila sale `status=error` y **ningún percentil es válido**;
   el p95 que aparece (261 s) está censurado y no se usa. Es el comportamiento
   correcto del runner, no un fallo.

### Qué significa todo esto para F8

**Q1 con c=50 es, en buena medida, inmedible en este hardware.** En PROFILE_A da
92 % de timeouts; en C, OOM; en B, ninguna consulta termina en 110 s. Esas filas
saldrán `error` u `oom`, con las columnas que se puedan medir y las latencias
vacías. **No es un fallo del experimento: es el resultado**, y es justo lo que el
manual quiere observar bajo contención. Hay que anticiparlo en el reporte en vez
de descubrirlo al final de 13 h de corrida.

---

## Decisiones que salen de F7 (pendientes de Alix)

### F7-e — Qué hacer con los P95/P99 contaminados por la consulta en frío

El calentamiento de 60 s del manual no alcanza con c=50 en B y C: hasta el 91 %
de la ventana son primeras consultas. Tres caminos:

| | Qué | Coste |
|---|---|---|
| **(a)** | Correr tal como dice el manual y **declarar la limitación**, mostrando en el reporte las dos vistas: el p95 del CSV y el p95 recalculado sin las primeras consultas (los crudos ya guardan cada muestra con su worker, así que se recalcula sin volver a medir) | Ninguno. Es lo que ya acordamos al cerrar F5 |
| (b) | Alargar el calentamiento a 120–180 s | Desviarse de §6 del manual, repetir F7 y +3–6 h de F8 |
| (c) | Descartar las celdas de c=50 en B y C | Perder la mitad de la respuesta a M1 |

**Recomiendo (a)**, que además es lo que ya decidiste. Lo nuevo es la **segunda
vista** en el reporte: sin ella, un p95 de 88 s en PROFILE_C se lee como latencia
del motor cuando es sobre todo arranque en frío.

### F8-a — El bucle de reintentos cuando el motor muere

En la celda del OOM, al morir los backends, cada worker reintentó la conexión
**sin pausa**: 455 504 "consultas" de 0.005 ms en 110 s, y un crudo de **19 MB**.
En F8, con ventanas de 300 s, serían ~2 M muestras y ~80 MB por repetición
afectada, y Q1 · C · c=50 se corre 3 veces.

Propongo que, al fallar la conexión, el worker **espere 1 s antes de reintentar**.
Así el bucle sigue vivo (si el motor se recupera, se ve), pero las muestras
quedan acotadas a ~300 por worker y el crudo a un tamaño normal. No cambia
ninguna columna: los errores no cuentan para el throughput ni para los
percentiles (A4), y la fila seguiría siendo `oom`. Cambia solo el **número** de
errores registrados, que hoy mide la velocidad del bucle y no el experimento.

Son dos líneas en `benchmark_runner/workload.py` y una prueba. **No lo toco sin
tu aprobación**, porque cambia lo que se registra.

### A2 — Tu decisión, confirmada

La estrategia de tandas es correcta y así está implementada: la **tanda 1** son
`Q1` + `Q2_MEM_LOW` (36 celdas, 108 corridas) y `run_benchmarks.sh` la corre por
defecto, dejando `Q2_MEM_HIGH` al final de la matriz. Si el docente dice 54, se
añade con `--todo`.

Un detalle del caso "responde 36": el cambio de etiqueta `Q2_MEM_LOW` → `Q2`
afecta al CSV **y** a los 108 crudos. Para que no sea una edición a mano (que el
proyecto prohíbe), hay que hacerlo con un script que reescriba el CSV a partir de
los crudos. Es media hora de trabajo y solo si hace falta; lo anoto como
pendiente en vez de escribirlo ahora.

---

## Cierre de F7 — PROPUESTA para revisión de Alix (2026-11-02)

**No se ha tocado PLAN, CLAUDE ni CHECKLIST.** Esto es lo que propongo marcar.

### PLAN F7

| Casilla | Propuesta | Evidencia |
|---|---|---|
| 3 filas con `run_number` 1, 2, 3 | [x] | `results/f7/measurements.csv` (6 filas, 3 por motor) |
| `validate_csv.py` pasa | [x] | VÁLIDO, en el registro del piloto |
| CV del throughput < 15 % | [x] | 4.2 % (Mongo) y 3.8 % (Postgres), `results/f7/check_pilot.json` |
| Sin tendencia monótona | [x] | Mongo no es monótono; Postgres sí, pero +7.9 % < 10 % (F7-b). Anotado para vigilar en F8 |
| Planes capturados (R-31) | [x] | `results/f7/explains/` (uno por celda, en r1) |
| Tiempo real → costo de F8 | [x] | 448.5 s por repetición → **20.2 h** con 162 corridas y **13.5 h** con 108 |
| Primera consulta en frío frente al calentamiento, en los 3 perfiles | [x] | `results/f7_frio/check_cold.json`: **no cabe en 14 de 18 celdas con c=50**. Se declara como limitación del protocolo (F7-e) |

### CHECKLIST

Propongo marcar, con su archivo: el piloto corrido con 3 repeticiones, el CV,
los planes por celda y la estimación del costo de F8. **No** marco nada del
reporte (F9) ni de la matriz (F8).

### Lo que F7 deja dicho para el reporte

1. **El calentamiento de 60 s del manual no alcanza con c=50** en B y C: hasta
   el 91 % de la ventana son primeras consultas en frío, y el p95 llega a bajar
   un 61 % si se quitan. Se declara, y se muestran las dos vistas (F7-e).
2. **Q1 con c=50 es inmedible en este hardware:** 92 % de timeouts en A, OOM en
   C, ninguna consulta terminada en B. Son resultados, no fallos.
3. **Primera evidencia de OOM y de spill en queries del manual** (no en sondas):
   Postgres · C · Q1 · c=50 → OOM; Postgres · A · Q1 · c=50 → 37.2 GB de
   archivos temporales. Las dos responden M2 con datos.
4. **Postgres acumula 4 veces más throttling que Mongo** con la misma cuota de
   1 CPU, porque Q2 le lanza 2 workers paralelos y el throttling se suma por CPU.
5. **La memoria de la VM aguanta** (3.2 GiB libres en el peor caso, sin swap),
   pero con 120 de 300 s en espera por memoria en la celda más pesada.
6. **Costo de F8 medido:** 13.5 h la tanda 1 (108 corridas) y 20.2 h la matriz
   completa, a 448 s por repetición.

### Pendientes que F7 pasa a F8

- **F7-e** y **F8-a**, arriba, que necesitan tu decisión.
- **V7**: el diseño de la regla de sudoers está en `docs/V7_SUDOERS.md`, sin aplicar.
- Vigilar la tendencia de Postgres (monótona pero pequeña) con más repeticiones.
- Recomprobar con c=50 lo de la consulta huérfana (en el piloto, con c=1, es inocua).
- Si el docente responde 36, hace falta un script que reescriba el CSV desde los
  crudos para cambiar la etiqueta, en vez de editarlo a mano.

### Herramienta de F8 lista: `scripts/run_benchmarks.sh`

Nombre exigido por R-25. Recorre la matriz y es **reanudable**: antes de cada
celda consulta el CSV y corre solo las repeticiones que faltan
(`benchmark_runner/schedule.py`, clave `engine/profile/query_id/concurrency/run_number`).

- `--listar` dice qué falta **sin correr nada y sin sudo**.
- Por defecto, **tanda 1** (Q1 + Q2_MEM_LOW); `--todo` añade Q2_MEM_HIGH;
  `--matriz 36 --q2-variante MEM_LOW` para el otro conteo de A2.
- `--motor` / `--perfil` / `--query` / `--concurrencia` para correr por bloques,
  y `--max-celdas N` para cortar la sesión a propósito.
- **Comprueba `sudo -n` antes de cada celda** y se detiene si la caché caducó, en
  vez de dejar repeticiones sin flush (V7).
- Se detiene tras 3 celdas seguidas con fallo.
- `--humo` corre 2 celdas (una por motor, PROFILE_C, Q2_MEM_LOW, c=1) con
  ventanas 5/20/5 en `results/f8_humo/`, solo la primera repetición que falte,
  para no duplicar filas al relanzarlo.

**Probado sin sudo:** `--listar` con el CSV real del piloto da 156 corridas
pendientes y excluye las 6 ya hechas; `--matriz 36` da 108; los filtros de
bloque dan 6 celdas; el humo da 2 celdas y 2 repeticiones; sin `sudo -v` se
detiene antes de tocar nada. Pruebas: `tests/test_schedule.py`, 9 nuevas
(reanudar sin repetir ni saltar, los dos conteos de A2, Q2_MEM_HIGH al final,
filas ajenas a la matriz, filtros). Suite completa **279/279**
(`results/f7/tests_f8_runner_20261102T141608Z.txt`).

**Falta el humo con motores de verdad, que necesita sudo:**
`scripts/run_benchmarks.sh --humo` (~2 min).

---

## Decisiones aplicadas el 2026-11-02 (aprobadas por Alix)

### F7-e — Las dos vistas, también en la figura

Aprobado. Además del texto, **la figura de P99 contra concurrencia muestra las
dos vistas o marca los puntos contaminados**: la curva sube en parte por el
arranque en frío y eso no puede quedar en una nota. Queda como requisito
**R-30.1** en SPEC §2, para que no se pierda al llegar a F9.

### F8-a — Pausa tras un fallo (hecho)

`benchmark_runner/workload.py`: tras un fallo, el worker espera
`ERROR_BACKOFF_S = 1 s` antes de reintentar. Un **timeout no pausa**: ya tardó
lo suyo y pausarlo falsearía el bucle cerrado.

**El motivo principal no es el disco** (el crudo de 19 MB), sino que **455 504
reintentos en 110 s son CPU del runner compitiendo con el motor dentro de la
misma VM**, justo cuando el motor está en apuros por el OOM. El crudo grande es
la consecuencia visible, no el problema.

No cambia ninguna columna: los errores no cuentan para el throughput ni para los
percentiles (A4), y la fila sigue siendo `oom`. Cambia solo el **número** de
errores registrados, que hoy medía la velocidad del bucle de reintentos.
Pruebas: `tests/test_workload.py::ErrorBackoffTest` (un motor que falla siempre
produce menos de 100 errores en 4 s, no decenas de miles).

### R-08 ampliado — Recuento del dataset después de cada OOM (hecho)

Pedido de Alix: *"después de cada OOM, contar las filas antes de continuar. Si no
son 500 000, parar"*, para no medir horas sobre un dataset dañado.

- `benchmark_runner/runner.py`: cuando la fila sale `oom`, se cuentan las filas
  (`count(*)` en Postgres, `count_documents({})` en Mongo) **fuera de la ventana**,
  y el resultado va al crudo (`"dataset"`). No poder contar también cuenta como
  "no intacto": si el motor no responde después de un OOM, seguir sería peor.
- `benchmark_runner/cli.py`: si no son 500 000, lo dice y **sale con código 3**
  sin correr las repeticiones siguientes.
- `scripts/run_benchmarks.sh`: el código 3 **detiene la matriz en seco** (no
  cuenta como "una celda con fallo, sigo con la siguiente"), e indica recargar con
  `scripts/load_dataset.sh` y verificar con `scripts/run_gate.sh`.
- Pruebas: `tests/test_pilot_f7.py::DatasetAfterOomTest`.

La fila del OOM **sí se escribe**: es un resultado legítimo. Lo que se detiene es
lo que venga después.

### V7 — Regla de sudoers (diseño aprobado; la instalación la ejecuta Alix)

Scripts hechos: `scripts/v7_install_sudoers.sh` y
`scripts/v7_revert_sudoers.sh`. El runner ya funciona con las dos vías
(`flush_caches.sh` elige, `sudo_ready()` acepta ambas, y el keepalive no arranca
si la regla está puesta). Detalle y reversión en `docs/V7_SUDOERS.md`.

**Pruebas tras estos cambios: 285/285** (`results/f7/tests_f8a_v7_20261102T144532Z.txt`).
