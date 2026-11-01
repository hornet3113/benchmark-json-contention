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
