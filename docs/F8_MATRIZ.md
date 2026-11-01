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
