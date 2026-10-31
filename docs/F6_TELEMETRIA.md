# F6 — Telemetría, spill y OOM (en curso, NO completada)

**Estado: plan aprobado por Alix el 2026-11-01, con un cambio en F6-f.**
Se empieza por F6.1. Cada paso se cierra con evidencia en `results/f6/`.

Qué cubre F6: Prometheus, cAdvisor y node_exporter (R-23), el cruce de esas
fuentes con el cgroup que ya lee el runner, y las sondas que demuestran que el
instrumento **sabría** ver throttling, spill y OOM (PLAN F6). No cambia ninguna
columna del CSV: las 14 columnas siguen saliendo del cgroup y de los motores
(SPEC §3, punto 3). Prometheus alimenta las curvas del reporte (R-30).

---

## Decisiones aprobadas (2026-11-01)

| # | Decisión |
|---|---|
| F6-a | Prometheus, cAdvisor y node_exporter se fijan **por digest** en `docker/images.env`, con la etiqueta de origen en el comentario, igual que los motores (F1) |
| F6-b | El monitoreo es un **proyecto de compose aparte** (`monitoring/docker-compose.monitoring.yml`, `name: benchmon`). El `down --remove-orphans` de `up_profile.sh` solo toca el proyecto `benchjson`; si compartieran proyecto, cada repetición tumbaría el monitoreo |
| F6-c | El monitoreo corre en `RUNNER_CPUSET` (8–11), nunca en las CPUs del motor (0–7), con tope de CPU y de memoria por servicio. Su consumo se **mide** en reposo y con carga y se declara (L3) |
| F6-d | cAdvisor con `--housekeeping_interval=1s` y `--allow_dynamic_housekeeping=false`. Sin esto cAdvisor puede espaciar sus lecturas hasta 60 s y Prometheus guardaría el mismo valor cada segundo: la resolución de 1 s sería falsa |
| F6-e | Al terminar cada repetición, el runner pide a Prometheus las series de la ventana (`query_range`, paso 1 s, con margen) y las guarda en `results/…/telemetry/<run_id>.json`. Solo biblioteca estándar (`urllib`) |
| F6-f | **(con el cambio de Alix)** Comprobación previa de `up==1` de los tres servicios antes de cada repetición. **Si la telemetría no responde, la repetición corre igual** y su fila se escribe en el CSV, porque las columnas salen del cgroup y no de Prometheus (SPEC §2). El hueco queda marcado en el archivo de telemetría y en el log. **Solo aborta si falla la lectura del cgroup.** **La matriz NO se detiene por fallos de telemetría** (Alix, 2026-11-02, cerrando F6-A1): las columnas salen del cgroup y las tres figuras obligatorias (R-30) salen del CSV y de la serie de 1 s del propio runner (`serie_cgroup_1s` en `results/raw/`), no de Prometheus. **En cada fallo de telemetría se registran memoria y swap de la VM** (`/proc/meminfo`: MemAvailable, SwapTotal/SwapFree; `/proc/vmstat`: pswpin/pswpout), para distinguir después un fallo inocuo de uno sintomático de presión de memoria |
| F6-g | Sonda de throttling con bucles de CPU (`docker exec` en el contenedor del motor, PROFILE_C, 2 bucles contra 1 CPU de cuota, 60 s), no con una query: el throttling sale mecánicamente, sin depender del planificador de cada motor |
| F6-h | El control cruzado del 5 % (cgroup frente a Prometheus) se hace con ventanas de **60 s o más**. Con muestreo a 1 s cada borde puede desviarse hasta 1 s de throttling: en 300 s es < 1 %; en 20 s de humo podría pasar del 5 % sin que nada esté mal |

### Ambigüedades abiertas de F6

- **F6-A1 — ¿Cuántos fallos seguidos de telemetría detienen la matriz?**
  **Cerrada (Alix, 2026-11-02): ninguno; la matriz no se detiene** (ver F6-f).
  Sigue valiendo cómo se marca: fallo = `up != 1` en la comprobación previa, o
  exportación fallida o vacía; un hueco parcial no es fallo y se marca con los
  intervalos que faltan.
- **F6-A2 — Qué fuente define `max_rss_mb` si cAdvisor no coincide con el
  cgroup.** **Resuelta en F6.2:** `container_memory_rss` es `anon`, comprobado
  con el contenedor congelado en los dos motores (registro de F6.2).
- **F6-A3 — `max_rss_mb` no cuenta lo mismo en los dos motores.** **Aprobadas
  (a) y (b) (Alix, 2026-11-02)**, más: **M3 (huella por 1 000 documentos) se
  calcula con `working_set` o declara explícitamente el sesgo**, porque con
  `max_rss_mb` Postgres sale artificialmente eficiente. Hecho: notas en SPEC §4
  y A11; `serie_cgroup_1s` con `shmem`, `file` e `inactive_file` (abajo).

---

## Pasos y criterios de aceptación

| Paso | Qué | Criterio (evidencia) |
|---|---|---|
| **F6.1** | Descargar y fijar imágenes; `monitoring/prometheus.yml` (`scrape_interval: 1s`) y el compose aparte; levantar el monitoreo | Los 3 targets con `up==1`; series de cAdvisor para `bench_*`; resolución real de 1 s; consumo en reposo medido. `results/f6/f6_1/` |
| **F6.2** | Definiciones: `container_memory_rss` de cAdvisor frente a `anon` del cgroup; throttling de cAdvisor frente a `cpu.stat`, en reposo y con carga | Documentado si `rss` equivale a `anon` en cgroups v2 (F6-A2) |
| **F6.3** | Sondas en `scripts/probes/`, sin filas en el CSV: throttling, spill en Postgres (sort sin `LIMIT`, `work_mem` 4MB), spill en Mongo (`$sort` sin `$limit`, `allowDiskUse:true`), OOM | Throttling > 0 y diferencia cgroup/Prometheus < 5 % (≥ 60 s). Spill visto por **los mismos detectores del runner** y confirmado en el `EXPLAIN`/`explain`. OOM con `oom_kill > 0`, clasificado `status=oom` por el clasificador del runner (fila impresa en `results/f6/probes/`, no escrita en el CSV) |
| **F6.4** | Runner: comprobación previa (F6-f) y exportación (F6-e), con pruebas contra un Prometheus falso | Pruebas en verde; después Alix corre un humo con sudo |
| **F6.5** | Cierre en este documento | Alix lo revisa antes de tocar PLAN, CLAUDE y CHECKLIST |

F6.1–F6.3 no necesitan sudo (no limpian caché) y van con un solo motor arriba.

**Lo que F6 no puede cerrar.** En PLAN F6, "medición real": "si ninguna celda
produce spill, registrar la vía alternativa" solo se responde después de F8;
"`disk_spill` refleja lo observado" está implementado y visto en humo, pero se
marca con las corridas reales.

**Riesgos.** cAdvisor puede no resolver los nombres de contenedor en Docker
Desktop (alternativa: identificarlos por id, que el runner ya conoce). La
memoria de la VM es justa con PROFILE_A + runner + monitoreo + caché: se mide
en F6.1, no se supone. Si el `$sort` de la sonda de Mongo no supera los 100 MB
no vuelca: se agranda la **sonda**, nunca la query del manual.

---

## Registro de ejecución

### F6.1 — Monitoreo arriba (2026-11-02, 03:18–03:31 UTC)

Sin sudo y con un solo motor arriba cada vez (Postgres y luego Mongo, ambos
en PROFILE_C). Evidencia en `results/f6/f6_1/`.

**Imágenes (F6-a)** — `docker_pull_20261102T031832Z.txt`, fijadas en `docker/images.env`:

| Servicio | Etiqueta de origen | Digest |
|---|---|---|
| Prometheus | `prom/prometheus:v3.15.1` | `sha256:fa330227…f191a2` |
| cAdvisor | `ghcr.io/google/cadvisor:v0.60.6` | `sha256:b8e7d109…bd07a` |
| node_exporter | `prom/node-exporter:v1.12.1` | `sha256:1b4e4438…f1be0` |

cAdvisor ya no se publica en `gcr.io` (última: v0.55.1); sale de `ghcr.io/google/cadvisor`.

**Archivos nuevos:** `monitoring/prometheus.yml` (validado con `promtool check
config`), `monitoring/docker-compose.monitoring.yml` (proyecto `benchmon`),
`scripts/up_monitoring.sh`, `scripts/down_monitoring.sh`,
`scripts/checks/check_monitoring.py`.

**Tres problemas encontrados y cómo se resolvieron** (cada intento tiene su `up_monitoring_*.txt`):

1. `032120Z`: el daemon rechazó `/:/host:ro,rslave` en node_exporter ("path /
   is mounted on / but it is not a shared mount"). En Docker Desktop `/` no es
   un montaje compartido. Se quitó `rslave`; `/proc` y `/sys` se ven igual.
2. `032133Z`: cAdvisor solo reportaba la raíz `/`. Su log: "Registration of
   the docker container factory failed: … dial unix
   /run/containerd/containerd.sock: no such file". Docker Desktop no expone
   ese socket, y los montajes de `/` y `/var/run` apuntan a la distro Ubuntu, no
   a la VM de Docker. Solución: `--raw_cgroup_prefix_whitelist=/docker/`, que
   lee los cgroups `/docker/<id completo>` (el mismo árbol que el runner).
   **Consecuencia: las series no tienen etiqueta `name`; se identifican por
   `id="/docker/<id>"`**, que el runner ya conoce.
3. `check_monitoring_reposo_20261102T032355Z.json`: falló la resolución.
   ~40 muestras en 58 s, paso mediano 1.37–1.55 s, máximo 1.99 s. Causa,
   leída en el código de cAdvisor v0.60.6 (`lib/manager/container.go`, `func
   jitter`): cada espera es `intervalo + rand × jitter_factor × intervalo`, con
   `jitter_factor=1.0` por defecto, es decir, entre 1 y 2 s. Se añadió
   `--jitter_factor=0`. En la misma corrida, node_exporter con `cpus: 0.25`
   acumuló **16 s de throttling en 60 s** con solo 0.06 núcleos de media (las
   ráfagas de cada scrape no cabían, y el scrape tardaba 0.2–0.3 s). Se subió a 0.5.

**Resultado después de los cambios:**

| Comprobación | Evidencia | Resultado |
|---|---|---|
| `up==1` en los 3 jobs, al inicio y al final | `check_monitoring_reposo_20261102T032714Z.json` | Sí. Scrape: cAdvisor 0.02–0.03 s, node 0.05–0.08 s, prometheus 0.01 s |
| Resolución real de 1 s | mismo archivo | 58 muestras en 58 s para los 4 contenedores; paso mediano 1.002 s, máximo 1.006 s |
| Series de `bench_postgres` | mismo archivo | Sí (por id) |
| Series de `bench_mongo` tras cambiar de motor **sin reiniciar el monitoreo** | `check_monitoring_reposo_cambio_a_mongo_20261102T032918Z.json` | Sí: el id nuevo aparece solo, 28 muestras en 28 s, paso máximo 1.004 s. Es lo que pasará en cada repetición |
| Series que usa el experimento (R-24, playbook §7) | mismo archivo | `container_cpu_cfs_throttled_seconds_total`, `…_periods_total`, `container_cpu_usage_seconds_total`, `container_memory_rss`, `container_memory_working_set_bytes`; `node_memory_MemAvailable_bytes`, `node_memory_SwapFree_bytes`, `node_disk_read/written_bytes_total`, `node_vmstat_pswpin/out`: todas presentes |
| Límites reales del monitoreo (F6-c) | `limites_monitoreo_20261102T033055Z.txt` | Los tres en `cpuset.cpus=8-11`, `memory.swap.max=0`; Prometheus 1 CPU/512 MiB, cAdvisor 1 CPU/256 MiB, node_exporter 0.5 CPU/64 MiB |
| Pruebas | `tests_20261102T033007Z.txt` | 213/213 OK (no se tocó código del runner) |

**Consumo del monitoreo en reposo**, leído del cgroup desde fuera (no de
Prometheus), 60 s, `032714Z`:

| Contenedor | Núcleos medios | `memory.current` máx. |
|---|---|---|
| Prometheus | 0.027 | 54.1 MiB |
| cAdvisor | 0.040 | 26.3 MiB |
| node_exporter | 0.059 | 10.1 MiB (throttling residual 0.7 s en 60 s) |
| **Total** | **0.126** de las 4 CPUs del runner | **90.5 MiB** |

`MemAvailable` de la VM con Postgres en reposo: ~5.1 GiB. El consumo **con
carga** se mide en F6.2/F6.3, junto a una carga real.

**Observaciones para pasos siguientes:**

- **Series de contenedores borrados (para F6.4).** Con Mongo arriba,
  `count(container_memory_rss)` devolvía 9 series para 4 contenedores vivos.
  cAdvisor pone su propia marca de tiempo a cada muestra, y con marcas
  explícitas Prometheus no aplica el vencimiento ("staleness"): la serie de un
  contenedor borrado sigue saliendo unos 5 min en las consultas puntuales. La
  exportación **debe** filtrar por el id del contenedor de esa repetición y por
  el rango de la ventana, nunca por "el último valor".
- **CPU de Postgres en reposo (para F6.2).** De 58 muestras de
  `container_cpu_usage_seconds_total`, solo 29 tienen valores distintos (en los
  contenedores de monitoreo, 58 de 58). Puede ser solo que Postgres en reposo
  no gasta CPU todos los segundos; se confirma bajo carga al cruzar con `cpu.stat`.

**Estado:** los criterios de F6.1 tienen evidencia. Pendiente de la revisión de
Alix antes de marcarlo en PLAN.

### F6.2 — Definiciones: cgroup frente a cAdvisor/Prometheus (2026-11-02, 03:35–03:49 UTC)

PROFILE_C, un motor arriba cada vez, sin sudo. Evidencia en `results/f6/f6_2/`.

**Qué dice el código** (cAdvisor v0.60.6, `lib/container/libcontainer/handler.go`):
con cgroups v2, `ret.Memory.RSS = s.MemoryStats.Stats["anon"]` (línea 832) y el
throttling sale de `ThrottlingData.ThrottledTime`, es decir, `throttled_usec` de
`cpu.stat` (línea 785). Lo que sigue lo comprueba con datos.

**Método** (`scripts/checks/check_definitions.py`): lecturas propias del cgroup
cada 0.2 s; 60 s en reposo y 90 s con carga sintética dentro del contenedor
(2 bucles de CPU contra 1 CPU de cuota y una escalera de memoria de 200 y 300 MB
con `dd`). Cada muestra de Prometheus se compara con las dos lecturas propias
que la encierran. Los contadores se comparan (a) en las mismas marcas de tiempo
(definición) y (b) en los bordes de la fase, como los calcula el runner
(control cruzado del 5 %, F6-h).

| Comprobación | Postgres `033532Z` | Mongo `034432Z` |
|---|---|---|
| `rss` = `anon`, con carga (comparaciones exactas) | **74 de 74** | **33 de 33** |
| `rss` = `anon`, en reposo | 56 de 57 (1 difiere 112 KiB) | 42 de 43 (1 difiere 40 KiB) |
| `working_set` = `memory.current − inactive_file` | 46/46 reposo, 61/61 carga | sin diferencias en las estables |
| Throttling con carga, definición (a) | 0.046 % | 0.053 % |
| **Throttling con carga, control cruzado (b), criterio < 5 %** | **0.11 %** | **0.03 %** |
| Uso de CPU con carga, (a) / (b) | 0.03 % / 0.67 % | 0.07 % / 0.52 % |
| Throttling acumulado con carga (cgroup) | 104.6 s en 91.2 s | 162.1 s en 91.3 s |
| Uso de CPU con carga | 90.5 s en 91.2 s (la cuota de 1 CPU, exacta) | 91.7 s en 91.3 s |

**Las dos diferencias en reposo se resolvieron congelando el contenedor**
(`scripts/checks/check_frozen.py`, `docker pause` y reanudado garantizado en
`finally`). Con `cgroup.freeze=1` ningún proceso corre y `anon` no puede moverse:
**`rss` = `anon` y `working_set` iguales en 20 de 20 muestras, en los dos motores**
(`check_frozen_bench_mongo_20261102T034742Z.json`,
`check_frozen_bench_postgres_20261102T034840Z.json`). Las diferencias en reposo
eran de tiempo: `anon` cambió y volvió entre dos lecturas propias. En Postgres,
`check_anon_blips_bench_postgres_20261102T033844Z.json` (lecturas cada ~10 ms)
encontró 1 pico así por minuto (44 KiB, < 200 ms); la causa probable, no
comprobada, es el lanzador de autovacuum (despierta cada 60 s por defecto). En
Mongo el detector de picos simples no encontró ninguno, pero su `anon` cambia
~19 veces por segundo (`034314Z`), así que puede ir y volver en varios pasos.

Los archivos `check_definitions_*_033532Z` (Postgres) y `*_034432Z` (Mongo)
conservan su veredicto `rss_igual_a_anon_en_todas_las_estables: false`: el
criterio estricto se fijó antes de correr y no se cambió después. La
explicación es la prueba con el contenedor congelado, no un criterio más laxo.

**Error del script, corregido:** `check_definitions_bench_mongo_20261102T034039Z.json`
marca `throttling_control_cruzado_<5%: false` con una diferencia de **0.0**. Era
`(x or 1) < 0.05`, y 0.0 es falso en Python. Se corrigió y se repitió la corrida
(`034432Z`). El archivo se conserva; sus datos son válidos, su veredicto no.

**F6-A2 resuelta:** `container_memory_rss` **es** `anon`. `max_rss_mb` (cgroup)
y la curva de RSS (Prometheus) miden lo mismo; no hay que elegir fuente.

**Hallazgos que van al reporte:**

1. **`cpu_throttled_seconds` puede ser mayor que la duración de la ventana.**
   El kernel suma el tiempo de throttling de cada CPU en la que el cgroup tenía
   hilos listos para correr. Con 2 bucles en 2 CPUs y una cuota de 1 CPU,
   ~1 s de throttling por segundo de reloj; Mongo, con más hilos repartidos,
   llegó a 1.8 s/s. No es un error: cAdvisor reporta la misma suma. Pero quien
   lea el CSV podría suponer que "segundos de throttling ≤ segundos de ventana".
   Hay que explicarlo en el mapeo de KPIs (SPEC §4, R-24).
2. **El control cruzado del 5 % depende de cuánto throttling haya.** Mongo en
   reposo (PROFILE_C) acumuló ~4 s de throttling en 60 s: la definición (a)
   coincidió al 0.0 %, pero el control cruzado (b) dio **7.5 %**, porque los
   bordes de Prometheus quedan a 0.3–0.6 s de los del runner y, con tan poco
   throttling, ese desfase pesa mucho. Es el efecto de F6-h y no aparece con
   carga sostenida (0.03–0.11 %). En celdas de la matriz con poco throttling, la
   curva de Prometheus y la columna pueden diferir más del 5 % sin que nada
   esté mal.
3. **Asimetría de `max_rss_mb` entre motores (nueva ambigüedad F6-A3, abajo).**
4. **Mongo en reposo, en PROFILE_C, ya tiene throttling** (~4 s por minuto, con
   0.26–0.29 núcleos de media): sus ráfagas de fondo no caben en la cuota de 1 CPU.
5. **Duda de F6.1 resuelta:** la CPU de Postgres en reposo dio 60 valores
   distintos de 60 muestras (91 de 91 con carga). Las repeticiones vistas en
   F6.1 eran de un Postgres recién arrancado y sin actividad, no de cAdvisor.

**Consumo del monitoreo con carga** (en las CPUs del motor; cgroup): 0.12
núcleos (corrida de Postgres) y 0.21 (segunda de Mongo), en las 4 CPUs del
runner. Con el runner y sus 10 procesos compitiendo en 8–11 se mide en el humo de F6.4.

**Pruebas:** `tests_20261102T034941Z.txt`, 213/213 (solo cambiaron scripts de `scripts/checks/`).

### F6-A3 — `max_rss_mb` no cuenta lo mismo en los dos motores (abierta)

`results/f6/f6_2/postgres_memory_stat_20261102T034926Z.txt`: Postgres usa
`shared_buffers` = 128 MiB (16384 × 8 kB) en **memoria compartida**
(`shared_memory_type=mmap`). El kernel la cuenta como `shmem` (dentro de `file`),
**no** como `anon`. En reposo: `anon` 5.2 MiB, `shmem` 15.2 MiB. El caché de
WiredTiger de Mongo se reserva con `malloc` y **sí** es `anon` (~260 MiB en
reposo en F6.2). Por eso `max_rss_mb` de Postgres excluye su búfer principal y el
de Mongo lo incluye. La columna está bien medida (es lo que el manual llama RSS
y lo que reporta cAdvisor), pero compararla entre motores sin decir esto
llevaría a concluir que Postgres "usa menos memoria".

No toca el CSV ni las 14 columnas. **Aprobado por Alix el 2026-11-02**, junto con la regla de M3:
- declararlo en la sección del reporte que interpreta la memoria y en el mapeo
  de KPIs de SPEC §4;
- en F6.4, guardar también `shmem` y `file` en `results/raw/` (no en el CSV) y
  exportar `container_memory_working_set_bytes`, para que el reporte muestre la
  memoria total de cada motor junto a `max_rss_mb`.

### Cambio en el runner pedido por Alix: la serie de 1 s va a `results/raw/` (2026-11-02)

**Antes:** el runner muestreaba `anon` cada 1 s, pero en `results/raw/` solo
escribía cuántas muestras tomó y el máximo (`memoria_anon: {muestras, max_mib}`).
Si Prometheus faltaba, la curva de RSS se perdía.

**Ahora:** `raw["serie_cgroup_1s"] = {"columnas": [...], "filas": [...]}` con
TODAS las lecturas de la ventana: `monotonic_ns` (el mismo reloj de `ventana_ns`),
`anon`, `shmem`, `file`, `inactive_file`, `memory_current`, `throttled_usec`,
`usage_usec`. `max_rss_mb` sigue saliendo solo de `anon`. Las lecturas son de
archivos del cgroup desde fuera: no consumen CPU del motor (F5-a).

- `benchmark_runner/metrics/cgroup.py`: `Cgroup.sample()`, `SAMPLE_COLUMNS`; `AnonSampler` guarda filas completas.
- `benchmark_runner/runner.py`: escribe `serie_cgroup_1s`.
- `tests/test_cgroup.py` (nuevo, 6 pruebas): orden de columnas, serie completa
  y no solo el máximo, `max_rss` solo de `anon` aunque `shmem` sea grande,
  contenedor muerto registrado sin perder lo leído, sin muestras → `None` (no 0).
- Se comprobará con un motor real en el humo de F6.4.

### F6.3 — Sondas y línea base (2026-11-02, 03:59–05:01 y 10:22–10:30 UTC)

Sin sudo, un motor arriba cada vez. Las sondas usan las piezas del runner, no
copias (`scripts/probes/probe_common.py`: `Cgroup`, `AnonSampler`,
`EngineProbe.read`, `assemble_row`, `container_state`). **Ninguna escribe en el
CSV**: la fila del clasificador va en el JSON con `query_id = SONDA_…`.
Evidencia en `results/f6/probes/` y `results/f6/f6_3/`.

**Sondas (PLAN F6, "capacidad de detección"):**

| Sonda | Archivo | Resultado |
|---|---|---|
| Throttling, Postgres PROFILE_C (2 bucles, 120 s) | `throttling_profile_c_postgresql_20261102T043706Z.json` | 143.4 s de throttling, 1197/1200 periodos, 119.98 s de CPU (la cuota exacta). **Control cruzado cgroup/Prometheus: 0.14 %** |
| Throttling, Mongo PROFILE_C (2 bucles, 120 s) | `throttling_profile_c_mongodb_20261102T043942Z.json` | 222.5 s, 1200/1200 periodos, 119.99 s de CPU. **Control cruzado: 0.20 %** |
| Spill Postgres (Q2 sin `LIMIT`, `work_mem` 4MB, ×3) | `spill_postgres_c_severe_20261102T044223Z.json` | 175 049 filas (= F2). `temp_bytes` +32.7 MB, `temp_files` +9. EXPLAIN: `external merge`, Disk, ~3.5 MB por proceso (principal + 2 workers). **status=spill, disk_spill=true** |
| Control negativo Postgres (Q2 tal cual, ×3) | mismo archivo | Sin volcado; EXPLAIN `top-N heapsort` en memoria. **status=ok** |
| Spill Mongo (Q2 sin `$limit` ni `$project`, allowDiskUse, ×3) | `spill_mongo_c_severe_20261102T044309Z.json` | 175 049 documentos. `metrics.query.sort.spillToDisk` +8 874, `spillToDiskBytes` +212 MB. explain: `usedDisk: true`, 175 049 registros y 195 MB volcados. **status=spill, disk_spill=true** |
| Control negativo Mongo (Q2 tal cual, allowDiskUse, ×3) | mismo archivo | Sin volcado; `usedDisk: false`. **status=ok** |
| OOM dentro de Postgres (PROFILE_C) | `oom_engine_postgresql_20261102T045007Z.json` | `tail` muere (137) en 11.9 s; `oom_kill` +1; el motor sigue respondiendo. **status=oom** |
| OOM dentro de Mongo (PROFILE_C) | `oom_engine_mongodb_20261102T045034Z.json` | 137 en 10.9 s; `oom_kill` +1; el motor sigue respondiendo. **status=oom** |

En la sonda de throttling la comparación (a), en las mismas marcas de tiempo,
salió vacía: Prometheus tiene muestras un segundo antes del primer borde y ahí
no hay lectura propia para interpolar. Es una limitación del script; la (a) ya
quedó establecida en F6.2. El criterio del PLAN es la (b).

**Observaciones de las sondas (no son criterios):**

- **`OOMKilled=True` con `Running=True`.** Docker marca el contenedor en cuanto
  el kernel mata **cualquier** proceso de su cgroup, aunque el proceso principal
  siga vivo. En la matriz no hay procesos ajenos al motor dentro del contenedor:
  un `oom` ahí sería un proceso del motor (un backend de Postgres, o mongod
  entero). Para el reporte: `status=oom` dice que el kernel mató algo del motor,
  no necesariamente que el motor cayó; `estado_contenedor_final` del crudo dice cuál fue.
- **La sonda de Mongo se fue haciendo más lenta**: 31 s, luego 62 s y luego 161 s en
  PROFILE_C. No se investigó.
- **Los contadores no cuentan igual los volcados:** `serverStatus` registra 8 874
  en las 3 corridas, y el `explain` solo 2 en una corrida. El detector solo exige
  que el contador suba, así que no le afecta.

**Línea base de throttling en reposo** (pedido de Alix;
`scripts/probes/throttling_baseline.py`, `results/f6/f6_3/baseline/resumen_20261102T035910Z.json`).
Igual que una repetición real pero sin consultas: up → healthy → 60 s →
**ventana de 300 s** (comparable con la columna). Sin flush (necesitaría sudo).

| Motor | Perfil | Throttling en 300 s | s/min | Periodos con throttling | Núcleos medios | En los 60 s previos |
|---|---|---|---|---|---|---|
| Postgres | A | 0.000 s | 0 | 0 % | 0.040 | 0.000 s |
| Postgres | B | 0.000 s | 0 | 0 % | 0.039 | 0.000 s |
| Postgres | C | 0.387 s | 0.08 | 18.6 % | 0.049 | 0.002 s |
| Mongo | A | 0.215 s | 0.04 | 0.15 % | 0.388 | 0.000 s |
| Mongo | B | **3.647 s** | 0.73 | 1.2 % | 0.422 | 0.008 s |
| Mongo | C | **26.666 s** | 5.33 | 28.0 % | 0.321 | 6.521 s |

**Para el reporte:** parte del `cpu_throttled_seconds` de Mongo **no lo causa el
benchmark**. En PROFILE_C son ~27 s por ventana de 300 s **en reposo**, y en
PROFILE_B ~3.6 s. Mongo en reposo usa 0.32–0.42 núcleos (Postgres, 0.04), y
sus ráfagas no caben en 1 o 2 CPUs. La línea base se declara junto a la
columna y en la figura de throttling. Es una sola medición por combinación, sin
repeticiones: sirve de orden de magnitud, no de valor exacto para restar.
(No se investigó qué hace Mongo en reposo.)

**Fallo real de telemetría encontrado durante F6.3, y su corrección.**
node_exporter murió por OOM (64 MiB, código 137) a las 04:48:24 UTC, con
`up{job="node"}` intermitente desde las 04:11. Su log: el colector
`filesystem` no entiende los montajes `9p` de WSL y falló en **todos** los
scrapes desde el arranque (4 905 errores). A ratos tardaba 6–42 s (201 veces más
de 1 s); los scrapes colgados se acumularon hasta el OOM. **La verificación de
F6.1 no lo vio**: solo miraba `up`, que sigue en 1 aunque falle un colector.

- Monitoreo: se apagan los colectores por defecto y se encienden solo los que
  el experimento usa: `meminfo`, `vmstat`, `diskstats`, `pressure` (PSI de memoria,
  útil para F6-f), `cpu`, `stat` y `loadavg`. Con los de por defecto, además,
  `zfs`, `nfs`, `bcachefs`, `infiniband`… quedaban en
  `node_scrape_collector_success=0` (`check_monitoring_tras_quitar_filesystem_20261102T045305Z.json`).
- `check_monitoring.py`: exige además **que no falle ningún colector** y registra
  la duración máxima de scrape.
- Fue un fallo inocuo, no de presión de memoria: la VM tenía ~5 GiB disponibles.
  Es justo el caso que F6-f pide distinguir registrando memoria y swap.

**Ajustes de topes de CPU (F6-c), con su evidencia:**

1. node_exporter 0.5 → **1.0**: con 0.5 seguía con ~5 s de throttling por minuto
   y scrapes de hasta 0.44 s (`…_solo_colectores_usados_20261102T045544Z.json`).
2. cAdvisor 1.0 → **2.0**: con 1.0 tuvo ráfagas de throttling y la lectura de **su
   propio** cgroup salió tarde. Se perdieron 2 muestras de su serie a las
   04:59:51, con los 150 scrapes completos (máx. 0.22 s) y la serie de
   node_exporter sin huecos (`…_node_1cpu_20261102T045840Z.json`, que por eso
   marca `resolucion_1s: false`). El mismo mecanismo podría atrasar la lectura
   del motor.
3. Resultado (`check_monitoring_cadvisor_2cpu_*.json`, 120 s): todo `true`,
   ningún contenedor de monitoreo con throttling, scrape máx. 0.027 s, paso máx.
   1.006 s, 0.073 núcleos en total. **Prometheus: `memory.current` 392 MiB**, de
   los que solo 66 MiB son `anon`; el resto es caché de archivos de su base de
   datos (recuperable y dentro de su tope de 512 MiB). Ocupa memoria de la VM:
   hay que mirarlo en el humo de F6.4 con PROFILE_A, donde el margen es justo.

**La VM se congeló mientras se esperaba a Alix (no durante una medición):**
Prometheus no tiene muestras entre las 09:49:49 y las 10:21:15 UTC. Los scrapes
de más de 1 s caen justo al reanudar (`scrape_durations_20261102T102238Z.txt`).
Dato para F7: en WSL2, `CLOCK_BOOTTIME − CLOCK_MONOTONIC` siguió en 0, así que
la congelación **no** aparece como suspensión en `CLOCK_BOOTTIME`. La detecta
la comparación entre el reloj de pared y el monotónico (F5-d), que es la que usa el runner.

**Pruebas:** `results/f6/f6_3/tests_20261102T045112Z.txt`, 224/224 (213 + 6 de
`test_cgroup.py` + 5 de `test_probes.py`). Los cambios posteriores son del
compose y de `scripts/checks/check_monitoring.py`, que no tienen pruebas
unitarias: su evidencia son las corridas de arriba.

### Propuesta F6-A4 (para F6.4): qué hace la comprobación previa si la telemetría falla

Con F6-A1 la matriz no se detiene. Pero los contenedores de monitoreo tienen
`restart: "no"`: si uno muere (como node_exporter hoy), **todas las
repeticiones restantes** quedan sin sus curvas. Propuesta: cuando la
comprobación previa falla, el runner (1) registra memoria y swap de la VM,
(2) ejecuta `scripts/up_monitoring.sh` una vez (es idempotente y solo recrea lo
caído), (3) vuelve a comprobar y anota el resultado, y (4) la repetición corre
igual, con o sin telemetría. La comprobación previa incluiría `up==1` **y**
`node_scrape_collector_success==1` en el último minuto. **Aprobada por Alix el 2026-11-02.**

**Estado de F6.3:** los cinco criterios de "capacidad de detección" de PLAN F6
tienen evidencia (throttling, spill en Postgres, spill en Mongo, OOM y control
cruzado < 5 %); el de `up==1` se volvió a comprobar tras la corrección. Los dos
de "medición real" dependen de la matriz (F8). Pendiente de la revisión de Alix
antes de marcar nada en PLAN.

### F6.4 — Telemetría en el runner (2026-11-02, 10:24–10:40 UTC)

**Código:**

- `benchmark_runner/telemetry.py` (nuevo):
  - `preflight`, la comprobación previa de F6-A4: `up==1` de los 3 jobs y ningún
    colector fallido en el último minuto. Si falla, registra la memoria de la VM,
    ejecuta `up_monitoring.sh` una vez, vuelve a comprobar (esta vez con el valor
    actual de los colectores) y anota todo.
  - `export`: las series de la ventana, con 5 s de margen.
  - `gaps`: los huecos, incluidos los de los bordes.
  - `vm_memory`: lee de `/proc` `MemAvailable`, el swap, `pswpin/out`, `oom_kill` y la presión de memoria (PSI).
  - `summary`: el resumen para el crudo y el log.
  - Nada de esto lanza excepciones.
- **Exportación con muestras crudas, no con `query_range`:** cAdvisor pone sus
  propias marcas de tiempo y Prometheus no vence sus series, así que `query_range`
  rellenaría los huecos repitiendo el último valor y los escondería.
- `benchmark_runner/runner.py`:
  - la comprobación previa va **antes** de `prepare`, para que un reinicio del monitoreo nunca caiga en una ventana;
  - la exportación va después del enfriamiento, en `results/…/telemetry/<run_id>.json`;
  - el crudo lleva `telemetria` (resumen y ruta);
  - **un cgroup ilegible al empezar → `RunAborted`** (en `abortadas.jsonl`, sin fila): es lo único que aborta por instrumentación (F6-f);
  - `prometheus_get=None` desactiva la telemetría (solo pruebas y diagnósticos).
- `benchmark_runner/cli.py`:
  - imprime el estado de la telemetría y sus motivos;
  - cada fallo o incidente se anota en `telemetria_eventos.jsonl`, con la memoria y el swap de la VM;
  - **no detiene nada** (F6-A1).
- **Fallo de telemetría** = comprobación previa sin recuperar, o exportación
  fallida (Prometheus inalcanzable, o sin muestras de `container_memory_rss` o del
  throttling del motor). **No es fallo** que haya huecos: se marcan con sus
  límites. Tampoco una comprobación previa que falló pero se recuperó: queda en los motivos.

**Pruebas:**

- `tests/test_telemetry.py`, 24 pruebas contra un Prometheus falso:
  - un job caído, un job ausente y un colector fallido aunque `up=1` (el caso de F6.3);
  - Prometheus inalcanzable: falla, no lanza;
  - recuperación una sola vez, con memoria registrada al fallar y tras recuperar;
  - huecos dentro de la ventana y en los bordes;
  - exportación sin series del motor: queda `fallida`;
  - las consultas del motor van filtradas por id;
  - espera al último scrape;
  - el resumen distingue fallo de incidente;
  - `vm_memory` con un `/proc` falso.
- Suite completa: `results/f6/f6_4/tests_*.txt`, **248/248**.

**Contra el Prometheus real, sin sudo** (`scripts/checks/check_telemetry_live.py`,
`results/f6/f6_4/check_telemetry_live_20261102T103356Z.json`):

1. Con todo sano: ok, sin recuperar nada.
2. `docker stop benchmon_node_exporter` a propósito: detecta `up{job=node}=0.0`,
   registra la memoria de la VM, `up_monitoring.sh` lo recupera y la segunda
   comprobación da ok. **2.4 s en total.**
3. Ventana de 60 s de `bench_postgres` (PROFILE_C, en reposo): exportación
   **completa**, 70 muestras en 70 s (60 + 2 × 5 de margen) en cada serie del
   motor y del host. `node_disk_*` tiene 6 series (una por disco).

**Pendiente: el humo con un motor real y carga, que corre Alix con sudo:**
`scripts/smoke_f64.sh` (4 repeticiones; ventanas 30/120/10). Lo analiza
`scripts/checks/check_smoke_f64.py`:

- la serie de 1 s cubre la ventana y su máximo es **exactamente** `max_rss_mb`;
- la telemetría no falla;
- la columna de throttling difiere < 5 % de Prometheus cuando hay ≥ 1 s de throttling;
- informa además la memoria mínima de la VM y el consumo del monitoreo y los scrapes bajo carga.

Su ejecución en seco sobre los crudos de F5 (sin telemetría) marcó "REVISAR", como debía.

**Humo de F6.4, corrido por Alix con sudo (2026-11-02, 10:40–10:53 UTC).**
`results/smoke/f64_20261102T104051Z.txt` y `results/smoke/check_f64.json`.
Ventanas 30/120/10 s; plan de energía "Equilibrado", con batería al 77 %. No hubo
eventos de telemetría (`telemetria_eventos.jsonl` no se creó) ni repeticiones
abortadas. `validate_csv.py`: VÁLIDO.

| Repetición | status | Telemetría | Serie 1 s | `max_rss_mb` (serie = columna) | rss Prometheus | Throttling: columna / Prometheus | working_set máx. | MemAvailable mín. de la VM |
|---|---|---|---|---|---|---|---|---|
| Postgres A c=50 | ok | completa, sin huecos | 120 filas en 120 s | 126.79 = 126.79 | 126.79 (0.003 %) | 435.81 / 433.42 s (**0.55 %**) | 1 049.5 MiB | 4 587 MiB |
| Mongo A c=50 | ok | completa, sin huecos | 120 en 120 s | 921.79 = 921.79 | 915.31 (0.70 %) | 478.42 / 475.66 s (**0.58 %**) | 1 149.6 MiB | 3 926 MiB |
| Postgres C c=1 | ok | completa, sin huecos | 120 en 120 s | 16.51 = 16.51 | 16.55 (0.21 %) | 337.89 / 338.43 s (**0.16 %**) | 891.4 MiB | 4 966 MiB |
| Mongo C c=1 | ok (6 completadas: baja densidad, A4) | completa, sin huecos | 120 en 120 s | 547.18 = 547.18 | 546.25 (0.17 %) | 76.44 / 76.42 s (**0.04 %**) | 940.0 MiB | 4 589 MiB |

- **Monitoreo bajo carga**, con el runner y sus 10 procesos en las mismas CPUs
  (8–11), según cAdvisor: Prometheus 0.019–0.031 núcleos y ≤ 92 MiB; cAdvisor
  0.030–0.052 núcleos y ≤ 31 MiB; node_exporter 0.011–0.016 núcleos y ≤ 9 MiB.
  **Ningún contenedor de monitoreo tuvo throttling.** Scrape máximo: 0.092 s
  (cAdvisor, con Postgres A c=50). `up` mínimo: 1 en los tres jobs.
- **VM:** ni swap (`pswpout` +0) ni presión de memoria apreciable (≤ 0.03 s). El
  mínimo de `MemAvailable` fue 3.9 GiB (Mongo A c=50): con PROFILE_A queda
  margen, pero esto es con 120 s y no con 300.
- **La asimetría de F6-A3, con datos.** Postgres A c=50: `max_rss_mb` = 127 MiB
  pero `working_set` = 1 050 MiB (`shmem` 162 MiB). Mongo: 922 y 1 150. Con
  `max_rss_mb`, Postgres parecería usar 7 veces menos memoria; con
  `working_set`, la diferencia es de ~10 %. **Matiz para M3:** `working_set`
  incluye también la caché de páginas activa de los archivos de datos que se
  carga al contenedor. Postgres depende de ella por diseño (lee a través de la
  caché del sistema operativo), y cuenta contra `memory.max`, así que es memoria
  que el motor usa bajo el límite; pero tampoco es "memoria del proceso". Hay
  que decirlo en el reporte junto a la regla de M3.
- **El throttling supera la ventana también con carga real:** Postgres C con
  c=1 acumuló 338 s en 120 s. Una sola consulta con 2 workers paralelos son 3
  procesos en 3 CPUs contra 1 CPU de cuota. Es el hallazgo de F6.2, ahora con Q2.

---

## Cierre de F6 — PROPUESTA para revisión de Alix (2026-11-02)

**No se ha tocado PLAN, CLAUDE ni CHECKLIST.** Esto es lo que propongo marcar,
cada casilla con su archivo.

### PLAN F6 — capacidad de detección (sondas)

| Casilla | Propuesta | Evidencia |
|---|---|---|
| `up == 1` para cAdvisor y node_exporter | [x] | `results/f6/f6_1/check_monitoring_reposo_20261102T032714Z.json`; después de la corrección de F6.3, `results/f6/f6_3/check_monitoring_cadvisor_2cpu_*.json`; bajo carga, `results/f6/f6_4/humo_f64/check_f64.json` (`up` mín. 1) |
| Sonda de throttling en PROFILE_C > 0 | [x] | `results/f6/probes/throttling_profile_c_{postgresql,mongodb}_*.json` (143 s y 222 s en 120 s) |
| Sonda de spill en Postgres (`temp_bytes` + EXPLAIN externo) | [x] | `results/f6/probes/spill_postgres_c_severe_20261102T044223Z.json` |
| Sonda de spill en Mongo (contadores + `usedDisk`) | [x] | `results/f6/probes/spill_mongo_c_severe_20261102T044309Z.json` |
| Sonda de OOM: `oom_kill > 0` y `status=oom` | [x] | `results/f6/probes/oom_engine_{postgresql,mongodb}_*.json` |
| cgroup frente a Prometheus < 5 % | [x] | Sondas: 0.14 % y 0.20 %. F6.2: 0.11 % y 0.03 %. Humo: 0.04–0.58 % |

### PLAN F6 — medición real: **no se marca ninguna**

- "`disk_spill` y `status` reflejan lo observado": implementado y visto en humo
  y en las sondas, pero la casilla habla de la matriz → F8.
- "`disk_spill=false` en todas es un resultado válido": es una decisión ya
  tomada (A12), pero su evidencia es la matriz → F8.
- "Si ninguna celda produce spill, la vía alternativa": solo después de F8.

### CHECKLIST, "Telemetría"

| Casilla | Propuesta | Evidencia |
|---|---|---|
| R-23 Prometheus `scrape_interval: 1s`; `up==1` | [x] | `monitoring/prometheus.yml` + las de `up` de arriba |
| R-24 Los 8 KPIs obtenidos y mapeados | [x], **o** esperar a F8 (decide Alix) | Mapeo: SPEC §4 con las notas de F6.2. Obtenidos en las 4 filas del humo y en las sondas de spill y OOM. Si "obtenidos" significa "en la matriz", es de F8 |
| Throttling distinto de cero en PROFILE_C bajo carga | [x] | Sondas de throttling, y humo Postgres C c=1 (338 s) |
| Sonda de spill en Postgres | [x] | igual que en PLAN |
| Sonda de spill en Mongo | [x] | igual que en PLAN |
| Sonda de OOM clasificada como `status=oom` | [x] | `oom_engine_*` |
| Las sondas viven en `scripts/probes/` y no producen filas | [x] | `results/f6/f6_5/sondas_sin_csv_20261102T105619Z.txt` (ninguna referencia al escritor del CSV; escriben en `results/f6/`) |
| En el reporte, etiquetadas como verificación del instrumento | [ ] | F9 |
| Resultados reales (3 casillas) | [ ] | F8 |

### Lo que F6 deja dicho para el reporte

1. `cpu_throttled_seconds` puede ser mayor que la ventana (es la suma por CPU) → SPEC §4.
2. `max_rss_mb` (anon) no incluye los `shared_buffers` de Postgres; M3 se
   calcula con `working_set` o declara el sesgo → SPEC §4 y A11, más el matiz de
   la caché de páginas (arriba).
3. Throttling en reposo por perfil y motor: Mongo C ≈ 27 s y Mongo B ≈ 3.6 s por
   ventana de 300 s, sin consultas.
4. Con poco throttling, el control del 5 % no es exigible (efecto de los bordes, F6-h).
5. `OOMKilled=True` no significa que el motor cayó: hay que mirar `Running` en el crudo.
6. El monitoreo cuesta < 0.1 núcleos y < 135 MiB bajo carga (más la caché de
   archivos de Prometheus, hasta 392 MiB en reposo), en las CPUs 8–11 (L3).
7. Cómo se adaptó el monitoreo a Docker Desktop/WSL2:
   - cAdvisor sin el conector de Docker, por eso las series van por id;
   - `jitter_factor=0`;
   - node_exporter sin `rslave` y solo con los colectores usados;
   - los topes de CPU, con el porqué de cada uno.

### Pendientes que F6 pasa a fases siguientes

- **F7:** la ventana de 300 s real con PROFILE_A (`MemAvailable` mínimo y
  memoria de Prometheus); en WSL2, `CLOCK_BOOTTIME` no ve la congelación de la
  VM (la detecta la comparación entre el reloj de pared y el monotónico).
- **F7/F8, sin investigar:** la sonda de spill de Mongo se fue haciendo más
  lenta (31 → 62 → 161 s), y Mongo usa 0.3–0.4 núcleos en reposo.
- **F8:** cada repetición deja `telemetry/<run_id>.json`; hay que contar los
  `telemetria_eventos.jsonl` al terminar la matriz.

### Archivos de F6

- **Monitoreo:**
  - `monitoring/prometheus.yml` y `monitoring/docker-compose.monitoring.yml`;
  - `docker/images.env` (3 digests);
  - `scripts/up_monitoring.sh` y `scripts/down_monitoring.sh`.
- **Runner:**
  - `benchmark_runner/telemetry.py` (nuevo);
  - cambios en `runner.py`, `cli.py` y `metrics/cgroup.py`.
- **Sondas:** `scripts/probes/probe_common.py`, `throttling_baseline.py`,
  `throttling_profile_c.py`, `spill_postgres.py`, `spill_mongo.py` y `oom_engine.py`.
- **Verificaciones:** `scripts/checks/check_monitoring.py`, `check_definitions.py`,
  `check_frozen.py`, `check_anon_blips.py`, `check_telemetry_live.py` y
  `check_smoke_f64.py`; además, `scripts/smoke_f64.sh`.
- **Pruebas:** `tests/test_cgroup.py` (6), `tests/test_probes.py` (5) y
  `tests/test_telemetry.py` (24). Total: **248/248**
  (`results/f6/f6_5/tests_cierre_20261102T105619Z.txt`).
- **SPEC:** notas de interpretación en §4 y la regla de M3 en A11.

**Copia estable del humo de F6.4:** `results/f6/f6_4/humo_f64/` (copia íntegra de `results/smoke/` al cerrar F6, para que las rutas citadas en PLAN no se rompan). **Mapa de carpetas de humo:** `results/smoke/` es el humo de F6.4
(`f64_20261102T104051Z`). El próximo script de humo lo moverá a
`results/smoke_anterior_<sello de esa corrida>`. Al correr `smoke_f64.sh`, el contenido anterior de
`results/smoke/` (el humo v3 de Mongo de F5, 00:24 UTC) pasó a
`results/smoke_anterior_20261102T104051Z/`: el sello es el de la corrida que lo movió, no el de su contenido.
