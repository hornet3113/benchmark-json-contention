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
