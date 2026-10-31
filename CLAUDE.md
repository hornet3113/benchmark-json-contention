# Instrucciones del proyecto — léeme antes de tocar nada

Proyecto universitario **evaluado**: benchmarking de MongoDB frente a
PostgreSQL JSONB bajo contención de CPU y memoria.
Materia: Bases de Datos en la Nube · IT2iD · UPChiapas · 2026.

La persona con la que trabajas es Alix. Prefiere lenguaje llano y explicaciones
claras por encima de la redacción académica. Escribe en español.

## Actúa como

Ingeniero de software especializado en Python, Docker, MongoDB, PostgreSQL y
benchmarking.

## Reglas de trabajo (no negociables)

1. Respeta los requisitos del manual y señala las ambigüedades **antes** de decidir.
2. Trabaja por fases pequeñas y verificables.
3. Antes de cambios importantes, presenta un plan.
4. Escribe código modular, reproducible y documentado.
5. Incluye pruebas automatizadas y criterios de aceptación.
6. **No declares una fase completa sin evidencia de ejecución o pruebas.**
7. **No inventes métricas, capturas, logs ni resultados.** Si algo no se ejecutó,
   se dice que no se ejecutó.
8. Conserva el esquema CSV exigido por el manual: 14 columnas exactas, sin
   añadir, quitar ni renombrar ninguna.
9. Explica qué hace el código y qué debe comprender Alix para defenderlo ante
   el docente.
10. Al terminar cada fase, resume: archivos modificados, comandos ejecutados,
    pruebas aprobadas, pendientes y siguiente acción.

Prioriza exactitud experimental, trazabilidad y reproducibilidad por encima de
la velocidad.

## Fuentes de requisitos

- `docs/manual/playbook.pdf` — especificación técnica principal (4 páginas)
- `docs/manual/playbook_sesion.pdf` — contrato de entrega (13 diapositivas)

Regla de precedencia: ante conflicto, `playbook.pdf` define **qué se mide**;
`playbook_sesion.pdf` define **qué se entrega**.

## Documentos de trabajo — léelos antes de proponer nada

| Archivo | Qué contiene |
|---|---|
| `SPEC.md` | Matriz de requisitos con referencia a archivo y página, arquitectura, esquema CSV, ambigüedades A1–A12 y decisiones tomadas |
| `PLAN.md` | Fases F0–F9 con dependencias, criterios de aceptación, riesgos y estrategia de pruebas |
| `CHECKLIST.md` | Verificación de entrega |
| `docs/F1_INFRAESTRUCTURA.md` | Procedimiento, criterios y registro de ejecución de F1 (cerrada) |
| `docs/F2_GENERADOR.md`, `docs/F3_CARGA.md` | Plan y registro de F2 y de F3/F4 (cerradas) |
| `docs/F5_RUNNER.md` | Plan, decisiones F5-a…F5-i, registro de humo y cierre de F5 |
| `docs/F6_TELEMETRIA.md` | Plan, decisiones F6-a…F6-h, ambigüedades F6-A1…A4, registro y cierre de F6 |

Estos documentos son el estado acumulado del proyecto. **No los rehagas ni los
reinterpretes desde cero**: léelos, y si algo te parece equivocado, dilo en vez
de cambiarlo por tu cuenta.

## Entorno de ejecución

- Windows 11 + WSL2 (distribución `Ubuntu`) + Docker Desktop.
- Todo se ejecuta desde `Ubuntu`. El repositorio vive en el sistema de archivos
  de WSL2 (`~/benchmark-json-contention`), **nunca** bajo `/mnt/c/`.
- cgroups v2 confirmado. Los límites de Docker se aplican de verdad (verificado
  en F0 leyendo el cgroup desde dentro del contenedor).
- Hardware: Ryzen 5 PRO 5675U, 6 núcleos físicos / 12 lógicos, 14.8 GiB de RAM.
  La VM de WSL2 ve 12 CPUs y 7.159 GiB.
- Limitaciones del entorno virtualizado: `SPEC.md` §6, L1–L7. Van declaradas en
  la sección 1 del reporte, no escondidas.

## Estado actual (2026-11-02)

| Fase | Estado |
|---|---|
| F0 — Validación del entorno | Cerrada con reservas: V2 y V7 documentadas sin ejecutar; V8 resuelta en F1 |
| F1 — Infraestructura Docker | **CERRADA (2026-11-01)** con evidencia en `results/env/f1/` |
| F2 — Generador de dataset | **CERRADA (2026-11-01)** con evidencia en `results/f2/` y `results/dataset_stats.json` |
| F3 — Carga escalonada (G1/G2/G3) | **CERRADA (2026-11-01)** con evidencia en `results/f3/` |
| F4 — Queries y equivalencia | **CERRADA (2026-11-01)**: ejecutada en G2, re-verificada en G3 |
| F5 — Runner de benchmark | **CERRADA (2026-11-01)** con evidencia en `results/f5/`, `results/smoke*/` y `results/env/f5/` |
| F6 — Telemetría, spill y OOM | **CERRADA (2026-11-02)** con evidencia en `results/f6/` |
| F7 — Celda piloto | **En curso** (empezando: plan) |
| F8–F9 | No iniciadas |

Resultado de F1, en breve: MongoDB **8.2.12** (wiredTiger) y PostgreSQL
**18.6**; límites reales iguales al manual en 3 perfiles × 2 motores;
`memory.swap.max=0` en los seis; OOM observable en PROFILE_C. Detalle y
digests en `PLAN.md` F1 y `SPEC.md` §6.

Resultado de F2, en breve: `data/orders_500000_seed42.jsonl` (no
versionado), SHA-256 `0cd7fadb…0414`, determinista con semilla 42 y Python
3.14.4. Metas de A8 dentro de ±1 punto; 175 049 filas pasan el filtro de Q2;
no hay empate en la fila 1000 de Q2, pero sí 20 valores repetidos dentro del
Top-1000. Detalle en `PLAN.md` F2 y `docs/F2_GENERADOR.md`.

Resultado de F3/F4, en breve: los 500 000 documentos están cargados en los
dos motores e idénticos a la fuente (comparación en tres direcciones); Q1 y Q2
coinciden con una referencia exacta en Python en todas las variantes. **Q1
vuelca 1.4 GiB a disco en Postgres; Q2 no vuelca en ningún motor** (SPEC A12).
Los planes de Q2 son asimétricos: Mongo usa su índice de `timestamp` y
Postgres hace `Seq Scan` (R14). Detalle en `PLAN.md` F3/F4 y `docs/F3_CARGA.md`.

Resultado de F5, en breve: runner en `benchmark_runner/`, probado solo en
humo (no hay corridas reales). **c=50 = 10 procesos × 5 hilos**; la decisión
se sostiene en p50, throughput, concurrencia vista por el motor, conexiones
(153 en ambos modos) y memoria del runner (~460 MiB frente a ~1 990 MiB),
**no en el p95**. El p95 de la comparación A-B-A queda **incumplido con su
causa**: la primera consulta en frío de cada worker (27–35 s) cae al filo
del calentamiento de humo (30.3 s), y la discrepancia se invirtió entre
tandas. También incumplido: "celda de humo en < 1 min" en Mongo (95 s).
Detalle en `PLAN.md` F5 y en el cierre de `docs/F5_RUNNER.md`.

Resultado de F6, en breve:
- **Monitoreo:** Prometheus, cAdvisor y node_exporter fijados por digest, en
  `monitoring/` (proyecto de compose aparte, `benchmon`, en las CPUs 8–11).
  Cuesta < 0.1 núcleos bajo carga.
- **Definiciones:** `container_memory_rss` = `anon` (comprobado con el contenedor
  congelado), y el throttling coincide entre cgroup y Prometheus al < 1 %.
- **Sondas:** las cuatro (throttling, spill en Postgres, spill en Mongo, OOM)
  detectadas por los mismos detectores y el mismo clasificador del runner.
- **Runner:** comprobación previa con recuperación (F6-A4); exportación por
  repetición a `telemetry/<run_id>.json`; `serie_cgroup_1s` en el crudo. Un
  fallo de telemetría no detiene la matriz (F6-A1).
- **Al reporte:**
  - el throttling se acumula por CPU y puede superar la ventana;
  - `max_rss_mb` excluye los `shared_buffers` de Postgres (M3 con `working_set`, SPEC A11);
  - Mongo tiene throttling en reposo (C ≈ 27 s y B ≈ 3.6 s por 300 s).

Detalle en `PLAN.md` F6 y en el cierre de `docs/F6_TELEMETRIA.md`.

**Estado de los motores:** los volúmenes ya contienen los 500 000 documentos
con sus índices. **No volver a ejecutar `load_dataset.sh` ni `run_gate.sh`**
sin motivo: recrean la colección y la tabla.

### Lo siguiente, concretamente

F7 — celda piloto (Mongo y Postgres × PROFILE_C × Q2_MEM_LOW × c=1, tiempos
reales, 3 repeticiones). Presentar el plan antes de correr nada; las corridas
reales necesitan sudo y las corre Alix. Criterios de PLAN F7, que incluyen:
- CV < 15 % **y sin tendencia monótona** entre r1, r2 y r3;
- la primera consulta en frío frente a los 60 s, en los tres perfiles.

Antes de correr, el monitoreo debe estar arriba (`scripts/up_monitoring.sh`).

### Herramientas que ya existen (F1)

- `scripts/capture_env.py` — **único** lugar que lee el cgroup, `docker
  inspect`, la versión y el digest del motor y el host. No dupliques esa
  lógica: impórtalo (el runner de F5 debe usarlo).
- `scripts/verify_limits.sh` — llama a `capture_env.py` y compara contra
  los `EXPECT_*` del perfil. `VERIFY_OUTDIR` desvía la salida en pruebas.
- `scripts/probes/oom_profile_c.sh` — sonda de OOM (no produce filas del CSV).
- `generator/` (F2) — `synthetic_data_generator.py --size 1000|10000|500000`
  escribe `data/orders_<n>_seed42.jsonl` y sus estadísticas.
  `generator/schema.py:validate_record` es el contrato del registro:
  **reutilízalo en F3** para validar lo que devuelva cada motor.
- F3/F4 — `scripts/load_dataset.sh` (carga, DESTRUCTIVO), `scripts/verify_gate.py`
  (exporta, verifica y compara en tres direcciones en streaming),
  `scripts/check_equivalence.py` (`run`, `compare`, `summarize`; referencia
  exacta con `Decimal`), `scripts/extract_queries.py` (queries del PDF;
  `--check` al inicio de cada corrida) y `scripts/run_gate.sh`.
- F5 — `benchmark_runner/` (`python -m benchmark_runner.cli run-cell`;
  `--smoke` escribe en `results/smoke/`; sin `--smoke` exige
  `--confirmo-medicion-real`; `--procesos`, `--ventanas` y `--actividad-cada`
  solo con `--smoke`). `scripts/flush_caches.sh` (sudo), `scripts/smoke_f55*.sh`,
  `scripts/validate_csv.py` y `scripts/checks/` (monitor del host, comparación
  de modos, diagnósticos). Cada `results/smoke_anterior_<sello>` lleva el sello
  de la corrida que la movió, no el de su contenido (mapa en `docs/F5_RUNNER.md`).
- F6 — Monitoreo y telemetría:
  - `scripts/up_monitoring.sh` y `down_monitoring.sh` (monitoreo; el runner
    llama a `up_monitoring.sh` si la comprobación previa falla);
  - `benchmark_runner/telemetry.py`;
  - `scripts/checks/check_monitoring.py`, que exige `up`, la resolución de
    1 s y ningún colector fallido.
- F6 — Sondas, en `scripts/probes/`, sin filas en el CSV: `probe_common.py`,
  `throttling_profile_c.py`, `throttling_baseline.py`, `spill_postgres.py`,
  `spill_mongo.py` y `oom_engine.py`.
- F6 — Verificaciones: `check_definitions.py`, `check_frozen.py`,
  `check_telemetry_live.py` y `check_smoke_f64.py`; humo: `scripts/smoke_f64.sh`.
- Pruebas: `.venv/bin/python -m unittest discover -s tests -v` (248 al cierre
  de F6; con el `python3` del sistema se omiten las que necesitan drivers).
  `pytest` no está instalado; las pruebas se escriben compatibles con los dos.
  Drivers fijados en `requirements.txt`, instalados en `.venv`.

### Decisiones ya tomadas — no reabrir sin motivo

- **A1**: `payment.final_total` es hermano de `payment.totals`.
- **A3.2**: índice B-Tree sobre el timestamp extraído como **texto**, sin
  modificar Q2. No se exige que el planner lo use; si no lo usa, se reporta.
- **A4**: solo cuentan las consultas completadas dentro de la ventana; los casos
  con pocas o cero muestras se marcan, no se rellenan. **Ampliado (F5.5):** los
  timeouts son datos censurados por la derecha; con ≥ 1 % de timeouts en la
  ventana la fila es `error`; la fracción y la validez de cada percentil
  (P99 < 1 %, P95 < 5 %, P50 < 50 %) van a `results/raw/` (SPEC A4).
- **F5 (runner)**: 14 columnas medidas directamente; columnas vacías solo con
  `status` `error`/`oom`, nunca un 0 inventado; cgroup leído desde fuera del
  contenedor; motor en CPUs 0–7 y runner en 8–11; concurrencia 50 = 10
  procesos × 5 hilos (confirmado al cerrar F5, sin apoyarse en el p95);
  planes (R-31) solo en las celdas de concurrencia 1; throughput con 6
  decimales.
- **A5**: flush de caché por repetición, con el efecto medido (delta de
  `buff/cache`), no solo el código de salida.
- **A8**: distribuciones de `SPEC.md` §5 A8 con semilla fija y versionada.
- **A12**: se aceptan los resultados reales aunque no aparezcan spill ni OOM.
- **D-WSL1**: la VM se conserva en 7.159 GiB; sin `.wslconfig`. PROFILE_A se
  declara baseline con holgura limitada.
- **F6**:
  - las columnas salen del cgroup y Prometheus solo da curvas;
  - un fallo de telemetría **no** detiene la matriz (F6-A1) y se registra con
    la memoria y el swap de la VM;
  - la comprobación previa recupera el monitoreo una vez (F6-A4);
  - solo aborta un cgroup ilegible;
  - M3 se calcula con `working_set` o declara el sesgo (F6-A3).

### Pendientes abiertos

- **A2** — pendiente del docente: ¿36 celdas (108 corridas) o 54 (162)? Se
  propuso 54 con la variante de Q2 codificada en `query_id`. Mientras tanto, el
  runner debe diseñarse parametrizable para ambos conteos.
- **Evidencia de F0** — `results/env/f0/F0_salidas_observadas.md` es una
  transcripción de pantalla, no salida capturada. La casilla correspondiente de
  CHECKLIST queda sin marcar hasta que Alix decida si basta.
- **Conexiones de Mongo en PROFILE_C (vigilar en F8)** — pymongo abre ~3
  conexiones por cliente (1 de trabajo y 2 de monitoreo con `hello`
  periódicos): ~150 con c=50, contra un mongod de 1 CPU y 1 GiB. En cada celda
  de Mongo con c=50 en PROFILE_C mirar `actividad_del_motor` (conexiones y
  consultas activas), `anon` máximo y `oom_kill`. Si el costo es medible, se
  declara; Postgres no tiene equivalente. Detalle en `docs/F5_RUNNER.md`.
- **V7** — `sudo` pide contraseña y colgaría una corrida desatendida. Diseño
  restringido en `SPEC.md` A5. **No configurar nada permanente** sin que Alix
  lo apruebe explícitamente.
- **V2** — ruta de respaldo del flush: documentada, sin ejecutar.
- **Primera consulta en frío frente al calentamiento (F7)** — casilla en PLAN
  F7: medir la primera consulta en frío en **los tres perfiles** (A, B y C)
  contra los 60 s del manual (ampliado al aprobar F6). Si no cabe, P95/P99 de
  ese perfil quedan contaminados y se declara como limitación del protocolo,
  no como error del runner. Motivo: ya se vio una primera tanda de ~74 s en
  Q1 de Mongo con c=50 en PROFILE_A (humo F5.5).
- **Gracia + enfriamiento frente a la latencia (F7/F8)** — si una consulta
  dura más, el runner corta al worker y la consulta queda huérfana en el
  servidor hasta que se baja el contenedor. No afecta a la ventana (A4), pero
  hay que comprobarlo por celda.
- **De F6 a F7:**
  - medir con la ventana real de 300 s en PROFILE_A cuánta memoria le queda a
    la VM (`MemAvailable`) y cuánta ocupa Prometheus (hasta 392 MiB con su
    caché en reposo);
  - en WSL2, `CLOCK_BOOTTIME` no ve la congelación de la VM (la detecta la
    comparación entre el reloj de pared y el monotónico);
  - sin investigar: la sonda de spill de Mongo se degradó (31 → 62 → 161 s), y
    Mongo usa 0.3–0.4 núcleos en reposo.

## Trampas conocidas de este proyecto

- **cAdvisor en Docker Desktop no tiene etiqueta `name`**: sin el socket de
  containerd lee los cgroups crudos. Las series se filtran por
  `id="/docker/<id completo>"`. Como cAdvisor pone su propia marca de tiempo,
  Prometheus **no vence** las series de contenedores borrados (~5 min), y
  `query_range` rellena los huecos con el último valor. Por eso la exportación
  usa muestras crudas y filtra por el id de la repetición.
- **`up==1` no basta**: un colector de node_exporter puede fallar en cada
  scrape con `up=1`. En F6.3, el de `filesystem` (montajes 9p de WSL) terminó en
  un OOM real. Hay que mirar también `node_scrape_collector_success`.
- **`OOMKilled=True` con `Running=True`** es posible: Docker marca el contenedor
  si el kernel mata **cualquier** proceso de su cgroup.

- `final_total` **debe** ser número JSON, no string. Si fuera string, Mongo
  ordenaría lexicográficamente (`"9.5" > "100.0"`) y Postgres numéricamente: los
  Top-1000 no coincidirían y la comparación quedaría invalidada en silencio.
- `timestamp` se guarda como **string ISO-8601** en los dos motores. Como `Date`
  en Mongo, el `$gte` contra un literal de texto no haría match.
- Las queries de `queries/` se copian **literalmente** del manual y se leen desde
  disco, nunca embebidas en el código: el revisor debe poder compararlas con el PDF.
- Solo un motor corre a la vez. Si estuvieran los dos arriba competirían por el
  caché de páginas de la VM y la comparación dejaría de ser válida.
- Las sondas que fuerzan spill u OOM viven en `scripts/probes/`, nunca en
  `queries/`, y **no producen filas del CSV**. Mezclarlas con los resultados
  sería fabricar evidencia.
- **En Bash, nunca `{ … } | tee` si dentro se modifica una variable que se usa
  después**: el bloque corre en un subproceso y el cambio se pierde. Así,
  `verify_limits.sh` salía siempre con 0 (corregido en F1). Escribir a archivo
  y luego `cat`, o `exec > >(tee …)`.
- `order_id` sale del generador en forma canónica (minúsculas, `8-4-4-4-12`).
  En F3 el `id` de Postgres **se toma del documento**: `id =
  (data->>'order_id')::uuid`, nunca uno generado aparte. G1 comprueba que
  `id::text = data->>'order_id'` en todas las filas.
- El orden *dentro* del Top-1000 de Q2 no es determinista: hay
  `final_total` repetidos y Q2 no tiene desempate. Compara como conjunto.
- Las imágenes van **fijadas por digest** en `docker/images.env` (etiqueta de
  origen en el comentario). No volver a etiquetas móviles: para cambiar de
  versión, nuevo digest y repetir las verificaciones de F1.
- **Si el equipo se suspende durante una ventana de medición, esa celda queda
  inservible.** La VM de WSL2 se congela: las queries en vuelo se detienen y el
  reloj de pared avanza sin que corra nada. El throughput, las latencias y los
  deltas de cgroup de esa ventana ya no miden lo que dicen medir. Ocurrió en
  F3-G3: 53 minutos de reloj frente a 3.5 minutos de proceso, en un paso sin
  medición, así que no hizo daño. La repetición afectada se descarta y se
  repite; nunca se corrige a mano. El runner debe **detectarlo** (diseño en el
  plan de F5) y, antes de una corrida larga, el plan de energía de Windows debe
  impedir la suspensión.
- En `EXPLAIN (BUFFERS)` de Postgres los contadores de cada nodo **incluyen a
  sus hijos**. El total es el del nodo raíz; sumar los nodos cuenta lo mismo
  varias veces (pasó en G2: 8 310 registrados frente a 1 662 reales).
- `psql` guarda stdout en búfer y los `ERROR` (stderr) aparecen lejos de su
  sentencia. Para archivar salida con errores, usar `stdbuf -oL -eL psql …`.
- `mem_swappiness` no existe en cgroups v2 (V8, SPEC A7). Que no aparezca en
  `docker inspect` ni en el cgroup **no es un fallo**; la garantía es
  `memory.swap.max=0`.
