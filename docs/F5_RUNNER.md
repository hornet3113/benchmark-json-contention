# F5 — Runner de benchmark (en curso, NO completada)

**Estado: plan aprobado por Alix el 2026-11-01, con tres ajustes.** La fase se
detiene después de F5.2 para revisar la lógica antes de tocar los motores.

Qué cubre F5: el programa que ejecuta la matriz. N procesos en bucle cerrado,
ventanas de calentamiento, medición y enfriamiento, limpieza de caché y
reinicio por repetición, y una fila del CSV de 14 columnas por repetición. No
cubre Prometheus ni las sondas de volcado: eso es F6.

---

## Decisiones aprobadas (2026-11-01)

| # | Decisión |
|---|---|
| F5-a | **F5 mide directamente las 14 columnas**, sin valores vacíos ni inventados. Throttling: diferencia de `cpu.stat` antes y después de la ventana. Memoria: anónima de `memory.stat`, muestreada cada 1 s durante la ventana. Volcado: `temp_bytes` (Postgres) y contadores de spill (Mongo). OOM: `memory.events` y `OOMKilled`. A F6 le quedan Prometheus/cAdvisor, las sondas y el cruce de fuentes |
| F5-b | Percentiles con la biblioteca estándar (`statistics.quantiles(method="inclusive")`, la interpolación lineal que `numpy` usa por defecto). **Ajuste 2:** con menos de 2 muestras completadas, `statistics.quantiles` lanza un error; el runner **no se cae**: los percentiles quedan vacíos, la fila sale con `status=error` y el motivo va al log (A4) |
| F5-c | Motor fijado en un conjunto de CPUs y runner y telemetría en otro, sin compartir núcleo físico (`cpuset_cpus` en el compose, más `taskset` para el runner). **Ajuste 1:** el reparto se decide con la topología medida, no supuesta (ver abajo). Exige repetir las verificaciones de F1 |
| F5-d | Detección de suspensión: reloj de pared frente a reloj monotónico y frente a `CLOCK_BOOTTIME` durante la ventana. Si divergen más de 2 s, `status=error` y la repetición se repite. Antes de F7 y F8, plan de energía de Windows en "nunca suspender" |
| F5-e | Orden por repetición: bajar el motor → `sync` + `drop_caches` (con `sudo -v` renovado; V7 sin configuración permanente) → medir cuánto bajó el caché (abortar si no bajó) → levantar con el perfil de la celda → healthcheck → `capture_env` → ventanas |
| F5-f | Límite de 300 s por query: `maxTimeMS` (Mongo) y `statement_timeout` (Postgres) |
| F5-g | Las corridas de prueba van a `results/smoke/`, nunca a `measurements.csv` |
| F5-h | Encabezado del CSV **sin espacios por defecto**. **Ajuste 3:** es un parámetro, para poder regenerarlo con `", "` si el docente lo pide. La prueba compara contra el texto de §8.2 extraído del PDF |
| F5-i | `.venv` con `requirements.txt` fijado (`pymongo`, `psycopg[binary]`). Alix instaló `python3-venv` y `python3-pip` |

## Topología de CPU medida (ajuste 1)

`results/env/f5/cpu_topology_20261101T204105Z.txt`, con `lscpu -e` y
`thread_siblings_list`:

| CPUs lógicas | Núcleo físico (`CORE`) |
|---|---|
| 0, 1 | 0 |
| 2, 3 | 1 |
| 4, 5 | 2 |
| 6, 7 | 3 |
| 8, 9 | 4 |
| 10, 11 | 5 |

**Reparto:** motor en las CPUs **0–7** (núcleos 0–3) y runner y telemetría en
las **8–11** (núcleos 4–5). La propuesta inicial coincide con la topología
medida, así que no hubo que ajustarla. PROFILE_A (4.0 CPUs) cabe en 4 núcleos
físicos sin usar hilos hermanos por obligación.

**Límite que se declara (junto a L1 y L2):** es la topología que informa la VM
de WSL2. Que esos pares sean los mismos núcleos físicos del Ryzen depende de
cómo Hyper-V asigna las vCPUs, y no se puede verificar desde dentro de la VM.

---

## Pasos

| Paso | Qué se hace | Cómo se verifica |
|---|---|---|
| **F5-c** | `cpuset_cpus` en el compose; `capture_env.py` y `verify_limits.sh` leen y comparan `cpuset.cpus.effective` | Las 6 verificaciones de F1 repetidas, ahora con el cpuset |
| **F5.1** | `.venv`, `requirements.txt` fijado y versiones registradas | Los drivers importan y se conectan a cada motor |
| **F5.2** | Lógica pura: CSV, validador, percentiles, dominios, matriz 36/54, ventana (A4), detector de suspensión | `test_csv_schema`, `test_percentiles`, `test_status_domain`, `test_matrix`, `test_window` |
| F5.3 | Adaptadores por motor (queries leídas de `queries/`) | Mismo resultado que `check_equivalence.py` |
| F5.4 | El runner completo | Pruebas con un motor falso |
| F5.5 | Prueba de humo (una celda por motor en PROFILE_C) y prueba de carga máxima (Q1 en Postgres con concurrencia 50) | Menos de 1 min por celda; CSV válido; disco temporal y memoria del runner medidos |

---

## Registro de ejecución

### 2026-11-01 — F5-c: motor y runner en CPUs separadas

- Topología medida antes de tocar el compose (ajuste 1):
  `results/env/f5/cpu_topology_20261101T204105Z.txt`. El reparto 0–7 / 8–11
  coincide con los núcleos físicos 0–3 / 4–5.
- `docker/images.env`: `ENGINE_CPUSET=0-7`, `RUNNER_CPUSET=8-11` y
  `EXPECT_CPUSET=0-7`. `docker/docker-compose.yml`:
  `cpuset: ${ENGINE_CPUSET}` en los dos servicios. La cuota `cpus` del perfil
  no cambia.
- `scripts/capture_env.py` lee `cpuset.cpus.effective` y `CpusetCpus`, y
  `scripts/verify_limits.sh` los compara. Pruebas de `capture_env` actualizadas.
- **Las 6 verificaciones de F1 se repitieron con el cpuset**
  (`results/env/f5/cpuset/`, vía `VERIFY_OUTDIR`). Las 6 dieron exit 0:
  `cpu.max`, `memory.max` y `memory.swap.max` iguales al manual, y
  `cpuset.cpus.effective = 0-7` (`docker inspect CpusetCpus = 0-7`).
- Los datos de F3 siguen intactos tras los reinicios: 500 000 documentos en
  cada motor.

### 2026-11-01 — F5.1: entorno Python

- `.venv/` (ya en `.gitignore`) y `requirements.txt` con versiones exactas:
  `pymongo==4.19.0`, `dnspython==2.9.1`, `psycopg==3.3.6`,
  `psycopg-binary==3.3.6`.
- Las dos tienen paquete compilado para Python 3.14 (`cp314-manylinux_2_17`):
  no hizo falta `libpq5`. Evidencia: `results/env/f5/pip_install_20261101T204524Z.txt`.
- Conexión comprobada: `results/env/f5/drivers_conexion_20261101T204553Z.txt`.
  pymongo ve 500 000 documentos en MongoDB 8.2.12; psycopg (libpq 18.0.6) ve
  500 000 filas en PostgreSQL 18.6, y `SET work_mem = '64MB'` por sesión
  devuelve `64MB` en `SHOW work_mem`.

### 2026-11-01 — F5.2: lógica pura

Archivos: `benchmark_runner/{__init__,config,csv_writer,matrix}.py`,
`benchmark_runner/metrics/{__init__,percentiles,window}.py` y
`scripts/validate_csv.py`. Pruebas: `tests/test_csv_schema.py`,
`test_percentiles.py`, `test_status_domain.py` y `test_matrix.py` (incluye la
ventana y la suspensión). Suite: **168 de 168**, también con
`-W error::ResourceWarning`.

- **Esquema:** `csv_writer.py` es la única definición. `config.py` toma de ahí
  los dominios, y el validador aplica las mismas reglas (`check_row`).
- **Encabezado:** probado contra §8.2 **extraído del PDF**, tanto sin espacios
  (por defecto) como con `", "` (`header_spaces=True`, ajuste 3).
- **Sonda 5 de PLAN:** una columna de más, una renombrada, columnas
  reordenadas, una fila corta o una duplicada hacen fallar al validador. Se
  comprobó también por la línea de comandos.
- **Percentiles:** `statistics.quantiles(method="inclusive")`; P50/P95/P99 de
  1..10 = 5.5 / 9.55 / 9.91. Coinciden con la fórmula lineal escrita a mano
  (9 decimales) para n de 2 a 5 000. **Con 0 o 1 muestras no se lanza
  ningún error** (ajuste 2): percentiles vacíos, `status=error` y el motivo
  textual. Por debajo de 20 se marca baja densidad.
- **Matriz:** 54 celdas y 162 corridas, o 36 y 108 con la variante de Q2
  elegida explícitamente (A2 pendiente). En orden por bloques de motor y perfil.
- **Ventana (A4):** cuenta lo que termina dentro; lo que sigue en vuelo se
  descarta; los fallos se cuentan aparte.
- **Suspensión (F5-d):** el caso de F3-G3 (3 180 s de reloj de pared frente
  a 210 s monotónicos) se detecta; umbral de 2 s.

Defectos encontrados al escribir y probar:

1. `CsvWriter` abría el archivo para leer el encabezado y no lo cerraba
   (aviso `ResourceWarning`). Corregido con `with`.
2. **Precisión del throughput:** con 3 decimales, 1/300 = 0.00333 qps se
   escribía `0.003`. En celdas con pocas muestras eso perdía el conteo de
   completadas (errores de hasta ~15 %). SPEC §4 fija 3 decimales solo para
   latencias. **El throughput lleva 6**: `completadas = qps × 300` se
   recupera exacto. Hay prueba nueva.

### 2026-11-01 — F5.3: adaptadores por motor

Archivos: `benchmark_runner/env.py` (reutiliza `capture_env.py` para leer
`images.env`), `benchmark_runner/engines/{__init__,base,mongo,postgres}.py`,
`scripts/checks/check_adapters.py` y `tests/test_engines.py`, con 7 pruebas que
se omiten si no hay drivers. Suite: **175 de 175** con `.venv/bin/python`; con
`python3` del sistema, 175 con 7 omitidas.

- Una conexión por worker. La query se lee de `queries/` tal cual: el
  pipeline de Mongo se carga del JSON y el SQL va sin parámetros.
- Variante de Q2: `allowDiskUse` en `aggregate()` o `SET work_mem` en la
  sesión, confirmado con `SHOW work_mem`. Q1 sin variante.
- Límite: `maxTimeMS` o `statement_timeout`, nunca 0 (0 significaría "sin
  límite").
- Errores traducidos a `QueryTimeout` o `QueryFailed`.

**Verificación con los motores** (`results/f5/f5_3/run_20261101T205749Z.txt`,
`adapters_{mongodb,postgresql}.json`; PROFILE_A, datos de G3):

| | Q1 | Q2_MEM_LOW | Q2_MEM_HIGH | Timeout de 1 ms en Q1 |
|---|---|---|---|---|
| MongoDB | 240/240, igual a G3 | mismo conjunto y vector que G3 | ídem | `QueryTimeout` (código 50); conexión viva |
| PostgreSQL | 240/240, igual a G3 (`SHOW work_mem` = 4MB) | ídem (`work_mem` = 4MB) | ídem (`work_mem` = 64MB) | `QueryTimeout` (statement timeout); conexión viva |

"Igual a G3" significa igual a lo que obtuvo `check_equivalence.py` en G3, que
ya se había validado contra la referencia exacta.

**Observación abierta: el servidor está más lento que durante G3.** Por el
adaptador, Q1 en Postgres tardó 47 s y luego 33 s, frente a los 8.6 s del
`EXPLAIN ANALYZE` de G3; Q2, 1.9–2.6 s frente a 0.4–0.6 s. Se investigó sin
cambiar nada:

1. **El adaptador no es la causa** (`diagnostico_latencia_20261101T210047Z.txt`):
   en el mismo momento, el propio `EXPLAIN ANALYZE` de Q2 tarda 1.1–1.7 s, y
   el adaptador da 1.0–2.0 s.
2. **El cpuset no es la causa** (`ab_cpuset_20261101T210135Z.txt`): alternando
   0–7, 0–11, 0–7, 0–11, la mediana de Q2 fue 1 487 / 1 617 / 1 501 / 1 635
   ms. No hay ventaja para 0–11; si algo, 0–7 es algo mejor.
3. Estado del host, leído de Windows: conectado a corriente (100 %), plan
   **"Equilibrado"**, CPU a 2 010 de 2 301 MHz según WMI. No hay dato del
   estado durante G3, así que **la causa no está establecida**. La
   candidata principal es el estado de energía o la temperatura del portátil
   tras la suspensión de la tarde, pero no está demostrada.
4. **Con concurrencia 1 ya hay throttling bajo PROFILE_A**: 1.8–2.6 s
   estrangulados en cada bloque de unos 8 s. Q2 paraleliza con 2 workers, y
   PROFILE_A no está libre de contención de CPU aun con una sola consulta.
   Va al reporte (sección 2, "verificación del baseline").

Consecuencias que hay que tener en cuenta:

- **Las latencias dependen del estado del host.** Antes de F7 y F8: equipo
  conectado a corriente, plan de energía de alto rendimiento, sin suspensión,
  y anotarlo. El criterio CV < 15 % de la celda piloto (F7) es el que
  detectará si el ruido del host es demasiado.
- **Tamaño de las celdas:** si Q1 en Postgres tarda ~30–45 s con 1 CPU de
  holgura, bajo PROFILE_C y con concurrencia 50 es probable que se completen
  pocas consultas en 300 s, o ninguna. El caso de A4 (y el ajuste 2) va a
  ocurrir de verdad.

#### Diagnóstico repetido (2026-11-01, a pedido de Alix)

`results/f5/f5_3/diagnostico_latencia_20261101T210642Z.txt`. Mismo plan de
energía ("Equilibrado", conectado a corriente):

| | Primer diagnóstico (F5.3) | Repetido | G3 |
|---|---|---|---|
| Q1 por el adaptador | 47.3 s / 32.9 s | **11.3 s / 9.5 s** | 8.6 s (`EXPLAIN`) |
| Q2, mediana | ~1.5 s | **1.06 s** (`EXPLAIN` 914 ms) | 607 ms (`EXPLAIN`) |
| loadavg al empezar | 2.17 | 0.36 | — |

**La lentitud fue transitoria.** No era el adaptador ni el cpuset, y la
configuración de energía no cambió. El estado del host varió por sí solo, y
la causa exacta no está establecida. Para el experimento: el mismo equipo, con
la misma configuración, da latencias distintas según el momento. Por eso el
crudo de cada repetición guarda el estado del host (`host_antes`: loadavg y
memoria), y el CV < 15 % de F7 es el control.

### 2026-11-01 — F5.4: el runner completo

**Decisión de diseño (medida):** el cgroup del motor se lee **desde fuera** del
contenedor, en `/sys/fs/cgroup/docker/<id>/`, visible desde Ubuntu porque la
VM tiene un solo kernel. Cada `docker exec` cuesta ~250 ms y **gasta ~83 ms
de CPU del propio motor**: con PROFILE_C, muestrear la memoria cada segundo
así se comería ~8 % de su cuota. Desde fuera los valores son idénticos
(`cpu.max`, `memory.max`, `memory.swap.max` y `cpuset.cpus.effective`
comparados) y 100 lecturas consumen 0 ms de CPU del contenedor. Si el cgroup
no es visible, el runner no mide: no vuelve en silencio a `docker exec`.

Archivos nuevos:

- `benchmark_runner/metrics/{cgroup,spill}.py`
- `benchmark_runner/{workload,lifecycle,runner,cli}.py`
- `benchmark_runner/engines/fake.py`, solo para pruebas
- `scripts/flush_caches.sh`
- `tests/test_workload.py`

Además, `explain()` en los adaptadores (R-31).

- **`workload.py`:** N procesos `spawn`, cada uno con su conexión y fijado en
  `RUNNER_CPUSET`. Arranque común solo cuando todos están listos. Cada
  muestra se envía al terminar. Los ganchos de inicio y fin de la ventana se
  ejecutan en el instante exacto (±150 ms en las pruebas). Las consultas en
  vuelo tienen un tiempo de gracia y luego se cortan.
- **`lifecycle.py`:** por repetición, bajar → `flush_caches.sh` (efecto
  medido; aborta si no baja) → `up_profile.sh` con el perfil → límites
  reales comparados con el perfil (aborta si difieren). `SudoKeepAlive`
  renueva `sudo -n -v` cada 60 s, sin configuración permanente (V7).
- **`runner.py`:** `assemble_row()`, pura, decide la fila. Los timeouts por sí
  solos no son error (A4). El plan (R-31) se captura una vez por celda
  (`run_number` 1), **después** del enfriamiento. El crudo de cada repetición
  guarda las muestras, los relojes, el cgroup, el volcado, la limpieza, los
  límites y el estado del host.
- **`cli.py`:** `run-cell`. Sin `--smoke` exige `--confirmo-medicion-real`;
  sin credenciales de sudo se detiene antes de tocar nada. Las abortadas van
  a `abortadas.jsonl` y no producen fila.

**Cambio de esquema hecho en F5.4 (para revisión de Alix):** hasta F5.2 solo
las latencias podían ir vacías (con `status=error`). El runner escribía
**`0.0`** cuando faltaba la lectura de throttling o de memoria (por ejemplo,
si el contenedor muere por OOM y su cgroup desaparece). **Eso era inventar un
valor**: un 0 de throttling dice "se midió y dio cero". Se corrigió:
`cpu_throttled_seconds` y `max_rss_mb` también pueden ir **vacías**, y solo
con `status` `error` u `oom`; las latencias vacías se aceptan también con
`oom`; `throughput_qps` nunca va vacío. Escritor, validador y pruebas
actualizados.

**Otros defectos encontrados al probar, ya corregidos:**

1. Las lecturas en los bordes de la ventana habrían tumbado la repetición si
   el contenedor moría durante la medición: ahora registran el fallo y siguen.
2. `workload.py` contaba como "cortados" a workers que ya habían terminado y
   solo estaban cerrando su intérprete. Ahora se les espera y solo se cuentan
   los que tenían una consulta en vuelo.
3. La CLI pedía `sudo -v` antes de comprobar que la celda existía.

**Pruebas:** **192 de 192** (`.venv/bin/python -W error::ResourceWarning`;
con `python3` del sistema, 7 omitidas por falta de drivers). Con el motor falso:

- consultas rápidas: los bordes de la ventana caen en el instante correcto;
- consultas más largas que toda la repetición: termina en < 15 s cortando los
  workers, con 0 muestras;
- fallos y timeouts intercalados;
- un worker que no conecta aborta la repetición;
- cada regla de `assemble_row` se prueba, y **toda fila producida pasa `check_row`**.

**Protecciones comprobadas sin contenedores:** una medición real sin
`--confirmo-medicion-real` se rechaza (exit 2); `--smoke` sin credenciales de
sudo se rechaza (exit 2); una celda inexistente se rechaza antes de pedir
sudo. `flush_caches.sh` sin credenciales falla en 0.08 s sin pedir contraseña.

**Pendiente para F5.5 — `sudo` y la sesión de Claude:** las credenciales de
sudo se guardan **por terminal**, y la sesión de Claude no tiene terminal
propia (`not a tty`): un `sudo -v` de Alix en su terminal no le sirve. Hay dos
salidas:

- (a) Alix ejecuta la prueba de humo en su propia terminal
  (`sudo -v && .venv/bin/python -m benchmark_runner.cli run-cell --smoke …`)
  y Claude lee los resultados de `results/smoke/`.
- (b) La regla restringida de `sudoers` diseñada en SPEC A5 / V7 (opción 3).
  Es un permiso permanente: requiere aprobación explícita de Alix y se revisa
  antes de aplicarla.

### 2026-11-01 — Preparación de F5.5 (la ejecuta Alix en su terminal, opción (a))

Decisiones de Alix: confirma el cambio de esquema de F5.4 (columnas vacías
con `error`/`oom`); F5.5 por la opción (a); la regla de `sudoers` (b) se
revisa antes de F8 con el diseño a la vista.

- `scripts/smoke_f55.sh`: las 4 corridas de humo (abajo) con la salida en
  `results/smoke/`. Si ya existía, se mueve a `results/smoke_anterior_<fecha>`.
- `scripts/checks/monitor_host.sh`: sonda cada 5 s de la memoria de la VM,
  la memoria del árbol de procesos del runner y el disco temporal de
  Postgres (`docker exec du`, que consume algo de CPU del contenedor: por
  eso es una sonda y no va al CSV). Dos defectos corregidos antes de
  entregarlo: se contaba a sí mismo como runner, y la búsqueda por texto
  también contaba a cualquier shell que mencionara el comando. Ahora
  identifica al runner por sus argumentos exactos (`/proc/<pid>/cmdline`).
  Verificado: 0 procesos en reposo; 6 con un runner de prueba (principal,
  registro de recursos, forkserver y 3 workers).
- `cli.py --ventanas CAL MED ENF`: **solo con `--smoke`** (sin él, exit 2;
  hay prueba). Lo necesita la prueba de carga máxima: con 50 Q1 a la vez,
  20 s no alcanzan para llegar a la fase de ordenamiento.

| # | Corrida | Para qué |
|---|---|---|
| 1 | mongodb · PROFILE_C · Q2_MEM_LOW · c=1 · 5/20/5 | Circuito completo |
| 2 | postgresql · PROFILE_C · Q2_MEM_LOW · c=1 · 5/20/5 | Circuito completo |
| 3 | postgresql · PROFILE_A · Q1 · c=50 · 10/300/10, sin plan, con monitor | Disco temporal y memoria del runner en el peor caso conocido |
| 4 | mongodb · PROFILE_A · Q1 · c=50 · 10/60/10, sin plan, con monitor | Memoria del runner con pymongo |

### 2026-11-01 — F5.5: prueba de humo (ejecutada por Alix en su terminal)

Registro: `results/smoke/f55_20261101T213019Z.txt`. Host: conectado a corriente,
plan "Equilibrado". Los 4 pasos dieron exit 0. **`validate_csv.py`: VÁLIDO**
(4 filas). Todo en `results/smoke/`: no son resultados del experimento.

| # | Corrida | status | Completadas en ventana | Otras | throttled | anon máx. |
|---|---|---|---|---|---|---|
| 1 | mongodb · C · Q2_MEM_LOW · c=1 · 5/20/5 | error | 0 | 1 consulta de **27.3 s**, terminada 2 s después de la ventana | 14.7 s | 529 MiB |
| 2 | postgresql · C · Q2_MEM_LOW · c=1 · 5/20/5 | ok | 12 (p50 1.70 s) | 17 en total, 0 fallos | **62.7 s en 20 s** | 15 MiB |
| 3 | postgresql · A · Q1 · c=50 · 10/300/10 | spill | **4** (231–281 s) | **46 timeouts a 300 s** | 1 001 s en 300 s | 1 963 MiB |
| 4 | mongodb · A · Q1 · c=50 · 10/60/10 | error | 0 | 50 consultas de ~74 s, terminadas a +63.7 s | 236 s en 60 s | 879 MiB |

Funcionó como estaba diseñado:

- La limpieza de caché tuvo efecto en las 4: liberó 692, 641, 1 015 y 3 293 MiB.
- Límites verificados en las 4: `cpu.max`, `memory.max`, `memory.swap.max` = 0
  y `cpuset` 0–7.
- El runner corrió en las CPUs 8–11.
- Sin suspensión detectada y sin errores de lectura del cgroup.
- El plan (R-31) se capturó en las corridas 1 y 2.
- Las consultas en vuelo se cortaron al final, como prevé A4.
- Con menos de 2 muestras, la fila sale `error` con latencias vacías y
  **no se cae** (ajuste 2).

**Hallazgos (medidos, para decidir con Alix):**

1. **Percentiles censurados (no resuelto por A4).** En la corrida 3, 46 de
   50 consultas llegaron al límite de 300 s; las 4 completadas (231–281 s)
   dan p50/p95/p99 y la fila sale `spill`, no `error`, porque A4 solo
   exige ≥ 2 completadas. Pero ese P99 se calcula **solo con las que
   sobrevivieron**: el P99 real es ≥ 300 s. Decisión necesaria.
2. **Memoria de la VM con concurrencia 50 bajo PROFILE_A.** Runner: 52
   procesos y **2 089 MiB** con psycopg, 1 920 MiB con pymongo (~40 MiB por
   worker). Junto con el motor (anon 1.96 GiB y hasta 4 GiB de límite), la
   memoria disponible de la VM bajó a **2 075 MB** y se usaron **360 MB de
   swap**. Es el riesgo de L3/L7 materializado: el swap afecta al runner, no
   al motor (L7), y mete ruido en la latencia medida.
3. **Disco temporal de Q1 en Postgres con c=50:** pico de **32.5 GB**
   simultáneos en `pgsql_tmp` (monitor) y **36.9 GB escritos** en la ventana
   (Δ `temp_bytes`, 349 archivos). El disco virtual de Docker Desktop crece
   y no se encoge solo. Hay espacio (473 GB libres en C:), pero cada corrida
   de esa celda escribe decenas de GB.
4. **Con c=50, Q1 se comporta como un lote, no como un régimen sostenido:**
   las 50 consultas arrancan juntas y terminan juntas (Mongo: todas entre 74.0
   y ~75 s; Postgres: a 230–300 s). Con ventanas reales, en Postgres cada
   worker completa como mucho 1 consulta por ventana. Va al reporte como
   limitación de lectura.
5. **`cpu_throttled_seconds` puede superar la duración de la ventana** (62.7
   s en 20 s; 1 001 s en 300 s). No es un error: el kernel acumula el
   tiempo estrangulado por cada CPU donde el cgroup tenía trabajo, y Postgres
   corre en 3 procesos paralelos (`nr_throttled` = 200 de 200 periodos). Se
   declara en el reporte. Se contrasta con `container_cpu_cfs_throttled_seconds_total`
   de cAdvisor en F6.
6. **`max_rss_mb` (anon) no cuenta la memoria compartida:** Postgres da 15 MiB
   porque sus `shared_buffers` son memoria compartida, no anónima; la caché de
   WiredTiger de Mongo sí es anónima (529 MiB). Es la definición de RSS de
   cgroup v2, la que se espera que use cAdvisor (a verificar en F6). Comparar
   `max_rss_mb` entre motores requiere declararlo.
7. **Primera consulta en frío:** Q2 en Mongo bajo PROFILE_C tardó 27.3 s
   justo después de limpiar la caché (con PROFILE_A, ~2 s). Con el
   calentamiento de 5 s del humo no da tiempo a calentar; con los 60 s
   reales, se verá en F7. No se concluye nada de la cifra.
8. **Criterio de PLAN F5 "una celda completa en < 1 min":** Postgres sí (48 s
   de paso a paso, incluida la preparación); **Mongo no (95 s)**, por la
   consulta fría de 27 s, más la gracia para consultas en vuelo y la captura
   del plan.
9. **Captura de planes con c=50:** al cortar los workers quedan consultas
   huérfanas en el servidor (el motor no se entera de que el cliente se
   fue), así que un plan capturado justo después estaría distorsionado. Por
   eso las corridas 3 y 4 fueron sin plan.

### 2026-11-01 — Decisiones de Alix sobre los hallazgos de F5.5, y su implementación

1. **Censura (hallazgo 1):** variante de (b). `status=error` cuando la fracción
   de timeouts es ≥ 1 %; la fracción exacta y la validez de P50 (< 50 %), P95
   (< 5 %) y P99 (< 1 %) van al crudo (`censura`). Se declaran como datos
   censurados por la derecha. Escrito en SPEC A4. Implementación: `Sample.kind`
   distingue `timeout` de `error`; `WindowResult.timeout_fraction`;
   `runner.censoring()`; `assemble_row` devuelve también la censura. Pruebas:
   1 % exacto → error; < 1 % → ok; 3 % → P95 válido y P99 no; el caso real
   de la corrida 3 del humo (92 %) → error, con ningún percentil válido.
2. **Memoria del runner (hallazgo 2):** (b) procesos × hilos. Por defecto
   P = min(c, 10) y T = c / P (1×1, 10×1, 10×5); cada hilo con su propia
   conexión. **(c) descartada:** reabrir D-WSL1 invalidaría F0 y F1. Dos
   comprobaciones pedidas por Alix:
   - que el motor vea 50 conexiones de verdad: el crudo guarda
     `actividad_del_motor` en los bordes de la ventana (Postgres: clientes,
     consultas activas y workers paralelos de `pg_stat_activity`; Mongo:
     `serverStatus().connections` y `currentOp` sobre `orders`);
   - la comparación en humo 50×1 frente a 10×5: `scripts/smoke_f55b.sh`
     (A-B-A por motor) y `scripts/checks/compare_runner_modes.py`, con el
     **criterio fijado antes de correr**: 50 clientes en las 3 corridas, y
     p50, p95 y qps de B dentro del rango de las dos A ±10 %.
   `--procesos` solo se admite con `--smoke`.
3. **Planes:** solo en las celdas de concurrencia 1 (`run_number` 1). Para el
   reporte: el plan de c=1 no es el que se ejecuta con c=50, porque los workers
   paralelos de Postgres se agotan bajo carga. La sonda registra
   `workers_paralelos` y `max_parallel_workers` en cada borde de la ventana,
   como evidencia.
4. **Criterio "celda en < 1 min":** **declarado INCUMPLIDO** para Mongo (95 s)
   por la consulta en frío de 27 s, la gracia para consultas en vuelo y la
   captura del plan. Se cumple para Postgres (48 s). No se acortaron los
   tiempos del humo para forzarlo.

Suite: **202 de 202** (`.venv`); con `python3` del sistema, 7 omitidas.

### 2026-11-01 — F5.5b: 50 procesos frente a 10 × 5 hilos (ejecutada por Alix)

Registro: `results/smoke/f55b_20261101T215814Z.txt`; comparación en
`results/smoke/comparacion_modos.json`. Celda Q2_MEM_LOW · PROFILE_A · c=50,
ventanas 30/120/10, A-B-A por motor. Las 6 corridas dieron `ok` y el CSV de
humo es VÁLIDO.

| Motor | Modo | p50 | p95 | qps | Completadas | Runner (máx.) | Lo que vio el motor |
|---|---|---|---|---|---|---|---|
| Postgres | A1 50×1 | 24.7 s | 31.1 s | 2.225 | 267 | 2 125 MiB | 50 clientes, 50 activas, 7 workers paralelos |
| Postgres | B 10×5 | 26.2 s | 29.2 s | 1.983 | 238 | **476 MiB** | 50 / 50 / 7 |
| Postgres | A2 50×1 | 27.6 s | 34.0 s | 1.992 | 239 | 2 122 MiB | 50 / 50 / 7 |
| Mongo | A1 50×1 | 22.1 s | 33.7 s | 2.500 | 300 | 1 988 MiB | (sonda defectuosa: 152 / 104) |
| Mongo | B 10×5 | 23.6 s | 30.9 s | 2.217 | 266 | **459 MiB** | (152 / 102–104) |
| Mongo | A2 50×1 | 23.3 s | 32.9 s | 2.283 | 274 | 1 991 MiB | (152 / 102–105) |

Contra el criterio fijado de antemano:

- **Latencias y throughput: coinciden en los dos motores.** p50, p95 y qps
  de B caen dentro del rango de las A ±10 %.
- **Postgres: los 50 clientes se ven en las 3 corridas → COINCIDEN.**
- **Mongo: NO COINCIDEN, por un defecto de la sonda, no del runner.**

**Diagnóstico** (`scripts/checks/diag_mongo_connections.py` →
`results/f5/f5_5/diag_mongo_connections.json`, 10×5, sin `sudo`):

1. `command("currentOp", {filtro})` de pymongo manda el filtro como valor del
   comando y el servidor lo ignora. Mi sonda contó **todas** las operaciones
   activas: **50 y 49 `aggregate`** (las consultas de los workers), **51
   `hello`** (monitores del driver), el propio `currentOp` y 3 operaciones
   internas.
2. Las ~152 conexiones son 50 de trabajo + 100 de monitoreo (pymongo abre 2
   por `MongoClient`: streaming y RTT) + las de la sonda. Es el
   comportamiento normal del driver; Postgres no tiene equivalente. **Para el
   reporte:** Mongo atiende ~3 conexiones por cliente.

**Corregido:** `runner.mongo_activity()` pasa el filtro como campos del comando
y cuenta solo los `aggregate` sobre `bench.orders`. Prueba nueva
(`MongoActivityTest`) que comprueba cómo se arma el comando. Contra el
servidor real, en reposo: 0 consultas activas. `compare_runner_modes.py`
informa los crudos de F5.5b de Mongo como no comparables: no se reinterpretan
datos viejos con una regla nueva. `smoke_f55b.sh mongodb` permite repetir solo
Mongo. Suite: **203 de 203**.

**Memoria del runner con 10×5:** ~470 MiB, frente a ~2 GB con 50 procesos.

### 2026-11-01 — Antes de repetir Mongo: criterio, conexiones y vigilancia para F8

**Criterio de la comprobación 1, fijado ANTES de la repetición** (decisión de
Alix): **al menos 48 de 50 clientes con consulta activa en cada borde de la
ventana, en las 3 corridas**, para los dos motores. Motivo, tal como lo dejó
escrito Alix: se cambia porque una foto instantánea de un bucle cerrado puede
atrapar a un worker entre consultas (el diagnóstico vio 50 en un borde y 49 en
el otro), **no** porque el resultado no alcanzara la vara original. Está
escrito en `scripts/checks/compare_runner_modes.py` (`CRITERION_NOTE`) y se
guarda en cada `comparacion_modos.json`. Postgres lo cumple con 50/50 en las 3.

**¿Cuántos clientes de Mongo abre el modo 10×5?** **50, igual que 50×1.**

- Por código: en `workload._thread_loop` cada hilo llama a `build_engine()` y
  `connect()`, y cada `MongoEngine.connect()` crea su propio `MongoClient`
  (`maxPoolSize=1`).
- Por medición: `serverStatus.connections.current` = **153 en los tres modos**
  de F5.5b (50×1, 10×5, 50×1), y el diagnóstico con 10×5 vio 50 y 49
  `aggregate` simultáneos, imposible con menos de 50 clientes de una sola
  conexión de trabajo.

**Declaración para la comparación de modos:** los dos modos abren las
mismas conexiones (50 de trabajo y ~100 de monitoreo de pymongo, más la
sonda); solo cambia cuántos intérpretes de Python las alojan. La
comparación A-B-A no está sesgada por el número de conexiones. En Postgres
también son 50 en ambos modos (`pg_stat_activity`).

**Vigilancia para F8 (pedida por Alix), no solo un dato del reporte:** con
pymongo cada cliente abre ~3 conexiones (1 de trabajo y 2 de monitoreo que
envían `hello` periódicos). Con c=50 son ~150 conexiones contra un mongod que,
**bajo PROFILE_C, tiene 1 CPU y 1 GiB**. Cada conexión cuesta memoria y un
hilo en el servidor, y los `hello` cuestan CPU de una cuota ya estrangulada.
En F8 hay que mirar, por celda de Mongo con c=50 en PROFILE_C:
`conexiones_actuales` y `consultas_activas` en `actividad_del_motor`, `anon`
máximo y `oom_kill` del cgroup. Si ese costo fijo resulta medible, se
declara como parte de lo que Mongo paga por cliente (Postgres no tiene
equivalente) y no se oculta. También va en CLAUDE.md.

**Evidencia al repetir solo Mongo:** `smoke_f55b.sh mongodb` mueve el
`results/smoke/` actual (con el A-B-A de Postgres ya evaluado y el de Mongo
con la sonda defectuosa) a `results/smoke_anterior_<fecha>`, sin borrar
nada. La comparación nueva solo evalúa Mongo; la de Postgres queda en el
registro `f55b_20261101T215814Z.txt` y en esa carpeta.

### F5.5b — repetición de Mongo con la sonda corregida (2026-11-01, 23:52 UTC)

Corrida por Alix en su terminal: `sudo -v && scripts/smoke_f55b.sh mongodb`.
Registro: `results/smoke/f55b_20261101T235203Z.txt`; comparación:
`results/smoke/comparacion_modos.json`. Lo anterior quedó en
`results/smoke_anterior_20261101T235203Z/`. Host: con cargador, batería al
100 %, plan de energía "Equilibrado". Las tres corridas, `status=ok`, sin
timeouts ni errores.

| Corrida | Modo | p50 (ms) | p95 (ms) | qps | completadas | clientes activos inicio/fin | conexiones | runner (MiB máx.) |
|---|---|---|---|---|---|---|---|---|
| A1 | 50×1 | 21 613 | 24 068 | 2.1333 | 256 | 50 / 50 | 153 / 153 | 1 989 |
| B  | 10×5 | 23 382 | 32 428 | 2.3250 | 279 | **47** / 50 | 153 / 153 | 460 |
| A2 | 50×1 | 23 111 | 31 184 | 2.2333 | 268 | 50 / 50 | 153 / 153 | 1 988 |

**Resultado: NO COINCIDEN.** La comprobación 1, con el criterio fijado de
antemano (≥ 48 de 50 en cada borde y en las 3 corridas), **no se cumple**:
B tuvo 47 al inicio de la ventana. La comprobación 2 sí se cumple: p50, p95
y qps de B caen dentro del rango de A ampliado ±10 %. El criterio no se
modifica a la vista de este resultado.

Datos adicionales, obtenidos de los crudos sin correr nada más (las marcas
`(inicio, fin)` de cada consulta que guarda el runner):

- **Del lado del cliente, en B hubo 50 consultas en vuelo en el instante de
  inicio de la ventana**; muestreando cada 10 ms, nunca menos de 49 y una
  media en el tiempo de 50.000. El hueco entre que un worker termina una
  consulta y lanza la siguiente es < 1 ms en los tres modos.
- **En B terminaron 5 consultas entre 63 y 177 ms después del inicio de la
  ventana**, medidos del lado del cliente. La sonda no lee el motor justo en
  ese instante: `edge()` lee primero el reloj, luego el cgroup y `serverStatus`
  (spill), y solo después lanza `currentOp`. Ese desfase no se registra.
  Una consulta cuyo `aggregate` ya terminó en el servidor, pero cuya
  respuesta el cliente aún está recibiendo o decodificando, no aparece en
  `currentOp`. **Es una explicación compatible con los datos, no
  demostrada:** en A1 hubo una consulta que terminó a +79 ms y la sonda vio
  50, y sin el instante real de la foto no se puede ir más lejos.
- **A1 y A2 difieren mucho entre sí** (p95: 24.1 s frente a 31.2 s, un 30 %).
  Con ventanas de humo de 120 s y unas 260 muestras, la banda de la
  comprobación 2 resulta ancha. Que B caiga dentro dice poco a favor del modo
  y poco en contra; la estabilidad se evalúa en F7 (CV < 15 %).
- **A2 tuvo 49 workers terminados al final** (A1 y B, 0). La gracia (15 s)
  más el enfriamiento de humo (10 s) es menos que una consulta de ~23 s, así
  que las consultas en vuelo al cerrar la ventana se cortaron. No afecta a
  las métricas de la ventana, porque A4 las descarta de todas formas. Sí
  deja `aggregate` huérfanos en el servidor hasta que la corrida siguiente
  baja el contenedor. **Pendiente para F7/F8:** comprobar que enfriamiento +
  gracia cubre la latencia real de cada celda; en PROFILE_C la latencia será
  mayor.
- Memoria del runner: 50×1 ≈ 1 989 MiB y 10×5 ≈ 460 MiB. Se confirma el
  motivo del cambio.

### F5.5b — opción (b) de Alix: sonda con fotos cronometradas (criterio v3, PROPUESTO)

Alix eligió (b): mejorar la sonda y repetir solo Mongo. El resultado de la
v2 (47 < 48) se mantiene como incumplido; la v3 es una medición nueva con su
propio criterio, que se fija **antes** de correr.

Cambios (solo en la instrumentación; no cambian la carga ni las columnas del CSV):

- `runner.mongo_activity`: `t0_ns`/`t1_ns` encierran **solo** la llamada a
  `currentOp` (`serverStatus` va antes, fuera del intervalo). Los clientes en
  `getMore` (segunda parte de la misma consulta: Q2 devuelve 1000 documentos
  y el primer lote trae 101) cuentan como clientes con consulta activa;
  `getmore_activos` se guarda aparte. Postgres: el intervalo encierra la
  consulta a `pg_stat_activity`.
- `edge()`: reloj → cgroup (lectura de archivos del host, microsegundos;
  es columna del CSV) → **actividad** → spill. Antes la actividad iba al final.
- `metrics/concurrency.py` (nuevo): `PeriodicReader` toma una foto cada S s
  dentro de la ventana (`--actividad-cada S`, solo con `--smoke`); `cross()`
  cruza cada foto con las marcas del runner; `summarize()`.
- Cada muestra lleva su worker (`Sample.wid`; en el crudo,
  `[inicio_ns, fin_ns, ok, worker]`) y `LoadResult.unfinished_workers` lista
  los cortados al final (su última consulta seguía en vuelo).
- `EngineProbe` serializa sus lecturas con un candado (la serie corre en otro hilo).
- `scripts/smoke_f55b.sh` pasa `--actividad-cada 10`.
- Pruebas: `tests/test_concurrency.py` (nuevo) y casos nuevos en
  `tests/test_workload.py` (worker por muestra, cortados, `getMore`, intervalo
  de la foto, `--actividad-cada` solo con humo). Suite: **213/213**.

Verificación contra Mongo real, sin medición (`scripts/checks/check_probe_v3.py`,
PROFILE_A, 10×5, fotos cada 2 s; salida en `results/f5/f5_5/check_probe_v3.txt`):
11 fotos sin errores, de 18 a 103 ms cada una. En 9 el motor vio 50 y el runner
tenía 50 en vuelo; en una, 49/49. **En la única con faltantes (motor 46,
runner 50), 8 consultas terminaron en los 250 ms siguientes a la foto.**
Apoya la explicación de la respuesta en camino; no la demuestra para la
corrida de las 23:52.

Definiciones: `cliente_seguro` = workers con consulta en vuelo durante
**todo** el intervalo de la foto; `motor` = clientes con consulta activa según
la foto; `faltan` = `cliente_seguro − motor`.

**Criterio v3 PROPUESTO (falta que Alix lo fije):**

1. En cada una de las 3 corridas, al menos 10 fotos válidas y **mediana de
   `motor` ≥ 49** de 50.
2. **Media de `faltan` en B ≤ máx(media en A1, media en A2) + 1.** Esta es la
   pregunta de fondo: si los hilos de un proceso no llegaran a enviar sus
   consultas (GIL), el runner las contaría en vuelo y el motor no, y `faltan`
   crecería solo en B.
3. p50, p95 y qps de B dentro de [mín(A) × 0.9, máx(A) × 1.1] (sin cambio).

### F5.5b — corrida de Mongo con la sonda v3 (2026-11-02, 00:24 UTC)

Registro: `results/smoke/f55b_20261102T002424Z.txt`; comparación:
`results/smoke/comparacion_modos.json`. La corrida de las 23:52 quedó en
`results/smoke_anterior_20261102T002424Z/`.

**Estado del criterio:** se corrió **antes de que Alix confirmara** el
criterio v3. La propuesta ya estaba escrita en el código y en este documento
antes de la corrida, y no se ha modificado después; aun así no estaba
fijada, y el comparador lo registró así (`"estado": "PROPUESTO, sin fijar"`).
Se declara tal cual.

| Corrida | Modo | p50 (ms) | p95 (ms) | qps | fotos | motor mediana / mín. | faltan media / máx. | runner (MiB) |
|---|---|---|---|---|---|---|---|---|
| A1 | 50×1 | 21 840 | 33 315 | 2.4833 | 13 | 50 / 48 | 0.231 / 2 | 1 992 |
| B  | 10×5 | 21 714 | **24 194** | 2.1333 | 13 | 50 / 48 | −0.154 / 0 | 464 |
| A2 | 50×1 | 23 160 | 31 916 | 2.2917 | 13 | 50 / 48 | 0.231 / 2 | 1 990 |

- Comprobación 1 (mediana ≥ 49): **cumple** en las 3.
- Comprobación 2 (faltan B ≤ A + 1): **cumple** (−0.154 ≤ 1.231). Un valor
  negativo quiere decir que el motor vio una consulta que empezó a mitad de
  la foto.
- Comprobación 3: p50 y qps **cumplen**; **p95 de B NO cumple**: 24 194 ms
  frente a un rango de 28 725 a 36 647. B salió *más rápido* que A.
- Resultado global: **NO COINCIDEN**.

**Causa del p95, comprobada en los crudos de las dos tandas (6 corridas):**
todas las consultas de más de 28 s son la **primera consulta de cada worker**:
empiezan a +0 s, en frío, justo después del flush y del arranque del
contenedor, y terminan entre +27 y +35 s. **La ventana de humo empieza a
+30.3 s.** Según si esa primera tanda termina antes o después del borde, el
p95 cae en ~24 s (1.6 % de lentas en la ventana) o en ~31–33 s (9–16 %). Pasó
en los dos modos: en la tanda de las 23:52, A1 tuvo 24.1 s y B 32.4 s; en la
de las 00:24, al revés (B 24.2 s y A1 33.3 s). El p50 se mantuvo entre 21.6 y
23.4 s en las 6 corridas. Es un artefacto de un calentamiento de humo (30 s)
más corto que la primera consulta en frío; no depende del modo del runner.

**Pendiente para F7/F8 (no decidido):** A4 cuenta las consultas que terminan
dentro de la ventana aunque hayan empezado en el calentamiento. Si en alguna
celda la primera consulta en frío dura más que el calentamiento real (60 s),
por ejemplo en PROFILE_C, su p95 tendrá la misma bimodalidad. Conviene que
el runner registre por celda cuántas primeras consultas terminan dentro de
la ventana.

---

## Cierre de F5 (2026-11-01, decisión de Alix: opción (b))

**10×5 queda como modo por defecto** (`P = min(c, 10)`, `T = c / P`).

**En qué se sostiene la decisión y en qué no.** Se sostiene en p50,
throughput, concurrencia vista por el motor, conexiones y memoria del
runner. **No se sostiene en el p95.**

| Base | Evidencia |
|---|---|
| p50 | Dentro del rango de A ±10 % en las dos tandas de Mongo y en Postgres; entre 21.6 y 23.4 s en las 6 corridas de Mongo |
| Throughput | Dentro del rango en todas las tandas |
| Concurrencia vista por el motor | Postgres: 50/50 en cada borde. Mongo (sonda v3, 13 fotos por corrida): mediana 50 en las 3; `faltan` media de B −0.154 frente a 0.231 en A |
| Conexiones | 153 en todos los modos y corridas de Mongo: 10×5 abre 50 `MongoClient`, igual que 50×1 |
| Memoria del runner | 50×1 ≈ 1 990 MiB (llevaba la VM a swap en F5.5); 10×5 ≈ 460 MiB |

**p95: declarado INCUMPLIDO, con su causa.** En la tanda v3, el p95 de B
(24 194 ms) quedó fuera del rango de A (28 725–36 647 ms). Causa,
comprobada en los crudos de las 6 corridas de Mongo: **todas las consultas
de más de 28 s son la primera de cada worker**. Empiezan en frío a +0 s y
terminan entre +27 y +35 s, y **el calentamiento de humo termina a +30.3 s**,
justo al filo de esa consulta en frío. Si la primera tanda cae dentro de la
ventana, el p95 sube a ~31–33 s; si cae fuera, se queda en ~24 s.

**Por qué el modo no es la causa:** la discrepancia **se invirtió entre
tandas**. A las 23:52 el lento fue B (p95 32.4 s frente a 24.1 s de A1); a
las 00:24, A1 (33.3 s frente a 24.2 s de B). Un efecto del modo del runner
no cambia de signo de una tanda a otra; un borde de ventana que cae a uno u
otro lado de la primera consulta en frío, sí.

**Historia del criterio de concurrencia, completa:** v1 (50/50 en los
bordes) la cumplió Postgres; con Mongo no pudo evaluarse por el defecto de
la sonda. v2 (≥ 48 en los bordes, fijado antes de correr) dio 47 en Mongo:
**incumplido**. v3 (fotos cronometradas) quedó propuesta y **no llegó a
fijarse antes de correr**. Sus comprobaciones de concurrencia se cumplieron,
pero se citan como evidencia, no como criterio superado.

**Criterio PLAN F5 "celda de humo en < 1 min":** sigue **INCUMPLIDO** para
Mongo (95 s: de 21:30:21 a 21:31:56 en
`results/smoke_anterior_20261101T215814Z/f55_20261101T213019Z.txt`), por la
consulta en frío de 27 s, la gracia y la captura del plan. Postgres, 48 s.

**Se traslada a F7 (PLAN.md):** medir cuánto tarda la primera consulta en
frío en PROFILE_C y compararla con los 60 s de calentamiento del manual. Si
no cabe, las celdas de ese perfil salen con P95 y P99 contaminados por la
consulta en frío. Es una limitación del protocolo y se declara en el
reporte; no es un error del runner. Dato ya observado que conviene tener a
la vista: en el humo de F5.5, **Q1 de Mongo con c=50 en PROFILE_A** tuvo
una primera tanda de ~74 s, más que 60 s. Puede que la limitación no sea
solo de PROFILE_C.

**Pendientes que siguen abiertos:** gracia + enfriamiento frente a la
latencia real de cada celda (consultas huérfanas, F7/F8); conexiones de
Mongo en PROFILE_C (F8); diseño de sudoers (antes de F8); A2; V2; V7.

**Mapa de carpetas de humo** (cada `smoke_anterior_<sello>` lleva el sello
de la corrida que la MOVIÓ, no el de su contenido):

| Carpeta | Contenido |
|---|---|
| `results/smoke_anterior_20261101T215814Z/` | F5.5: humo de 4 pasos (21:30 UTC) |
| `results/smoke_anterior_20261101T235203Z/` | F5.5b, los dos motores (21:58 UTC): Postgres A-B-A aprobado; Mongo con la sonda defectuosa |
| `results/smoke_anterior_20261102T002424Z/` | Mongo, sonda corregida, criterio v2 (23:52 UTC): 47 < 48 |
| `results/smoke/` | Mongo, sonda v3 (00:24 UTC) |

Suite al cierre: **213/213** (`results/f5/tests_cierre_20261102T004918Z.txt`).
