# CHECKLIST.md — Verificación de entrega

Marcar solo con evidencia en `results/`, `tests/` o un comando ejecutado. Una casilla sin evidencia es una casilla sin marcar.

---

## 0. Decisiones

Tomadas el 2026-10-31:

- [x] **A1** — `payment.final_total` hermano de `payment.totals` (que contiene `subtotal`, `tax`, `discount`)
- [x] **A3.2** — Índice sobre el timestamp extraído como texto, sin tocar Q2; **no** se exige que el planner lo use
- [x] **A4** — Solo consultas completadas; pocas o cero muestras se tratan y marcan explícitamente, sin inventar percentiles
- [x] **A5** — Flush por repetición, con registro del efecto medido
- [x] **A8** — Distribuciones propuestas con semilla fija y versionada
- [x] **A12** — Se aceptan los resultados reales aunque no aparezcan spill ni OOM
- [x] **D-WSL1** — Se conserva la VM en 7.159 GiB con su swap global; sin `.wslconfig`. PROFILE_A queda declarado como baseline con holgura limitada

Pendiente del docente (no bloquea F1):

- [ ] **A2** — Propuesta: 54 celdas / 162 corridas, variante de Q2 en `query_id`. El runner se diseña parametrizable para soportar 36 o 54 sin reescribirlo

Verificaciones de F0 **completadas** (2026-10-31, con salida de comandos):

- [x] Plataforma real determinada: Windows 11 + WSL2 2.6.3.0 + Docker Desktop (distros `Ubuntu` y `docker-desktop`)
- [x] Hardware: 6 núcleos / 12 lógicos, 14.8 GiB RAM, 473 GB libres en C:
- [x] VM: 12 CPUs y 7.159 GiB visibles para contenedores; swap 2 GiB
- [x] cgroups v2 activo (`cgroup2fs`)
- [x] Docker Engine 29.4.1, Compose v5.1.3, Cgroup Version 2
- [x] Límites aplicados de verdad: `cpu.max=100000 100000`, `memory.max=1073741824`, `memory.swap.max=0`
- [x] Archivos de métricas del cgroup presentes
- [x] `sudo` disponible en Ubuntu; Docker accesible desde Ubuntu
- [x] Limitaciones del entorno virtualizado documentadas (L1–L7 en SPEC §6)

- [x] **V1** El flush desde Ubuntu **tiene efecto** sobre el caché de los contenedores: 787 MB → 387 MB. Limpieza efectiva, no caché frío
- [ ] **V2** Ruta de respaldo (contenedor privilegiado): documentada en SPEC A5 pero **no ejecutada**. Sin evidencia, sin marcar
- [x] **V3** Directorio de trabajo `/home/alix_anahi` sobre ext4 nativo, no `/mnt/c/`
- [x] **V4** 954 GB libres en la VM (tope real: 473 GB de C:); Docker ya usa ~51 GB de otros proyectos
- [x] **V5** Ruido en reposo: `loadavg` 0.38/0.12/0.04, 6.2 GiB disponibles, swap sin usar
- [x] **V6** Throttling observable y coherente: `--cpus=0.5` × 10 s → 5.02 s estrangulados

Verificaciones de F0 **pendientes**:

- [x] **V8** Comportamiento de `mem_swappiness` bajo cgroups v2 confirmado con `docker inspect`, con los avisos de `docker compose up` (ninguno) y con `docker create --memory-swappiness=0` directo (*Memory swappiness discarded*) — `results/env/f1/V8_mem_swappiness_20261101T171426Z.txt`, SPEC A7
- [ ] **V8** Declarado en la sección 1 del reporte (el reporte aún no existe)
- [x] **V7** `sudo` no interactivo para el flush — diseño revisado y **aprobado por Alix el 2026-11-02**, e instalado por ella: ayudante `/usr/local/sbin/bench-drop-caches` (`root:root 0755`, sin parámetros, fuera del repo) y regla `/etc/sudoers.d/bench-drop-caches` (`0440`, NOPASSWD solo para él), con `scripts/v7_revert_sudoers.sh` para deshacerlo. Comprobado en el humo de F8: el flush fue por la vía `ayudante_v7` y liberó caché sin contraseña. Detalle en `docs/V7_SUDOERS.md`
- [x] Volatilidad del cast texto→`timestamp` en la versión fijada de Postgres (A3.2) — `timestamp_in` y `timestamptz_in` son `STABLE`; índices con cast rechazados (`results/f3/g1/a32_index_variants.txt`)

Evidencia de F0:

- [ ] Salida de todos los comandos de F0 archivada en `results/env/f0/` — *existe `F0_salidas_observadas.md` (2026-11-01), pero es una **transcripción** de pantalla, no salida capturada; respaldo primario: capturas de pantalla. Alix decide si basta para marcar*
- [ ] Ninguna casilla marcada sin su comando correspondiente ejecutado

---

## 1. Requisitos del manual

### Motores e indexación
- [x] R-01 Mongo: colección `orders`, WiredTiger, sin sharding — `export_mongo.json` (`r01`): `wiredTiger`, mongod standalone
- [x] R-02 Mongo: índices en `timestamp` y `order_id` (captura de `getIndexes()`) — `results/f3/g3/export_mongo.json` (`indices`)
- [x] R-03 Postgres: `orders (id UUID PRIMARY KEY, data JSONB)` — `\d+ orders` en `results/f3/g3/export_postgres.json` (`r03_tabla`)
- [x] R-04 Postgres: índice B-Tree sobre timestamp extraído del JSONB — `idx_orders_timestamp`, `btree ((data ->> 'timestamp'))` (`results/f3/g3/export_postgres.json`)
- [ ] R-04 …"con `EXPLAIN` que lo use" — **no se cumple y no se puede cumplir sin modificar Q2**: el `EXPLAIN` de Q2 muestra `Seq Scan` (`results/explains/g3/postgres_q2_*.json`), porque el índice es de texto y Q2 convierte con `::timestamptz`. A3.2 decidió no exigirlo y reportarlo como hallazgo
- [x] R-15 Ningún índice sobre `final_total` en ninguno de los dos motores — `results/f3/g3/export_*.json` (`r15_indices_con_final_total: []`)

### Perfiles de recursos
Evidencia de cierre: `results/env/f1/PROFILE_*_20261101T1728*Z` y `…T1729*Z.{txt,json}`, generada con `verify_limits.sh` corregido y `capture_env.py` (PLAN F1).

- [x] R-05 PROFILE_A: `cpu.max` y `memory.max` reales = 4.0 CPU / 4096 m — `400000 100000` / `4294967296` en ambos motores
- [x] R-06 PROFILE_B: 2.0 CPU / 2048 m — `200000 100000` / `2147483648` en ambos motores
- [x] R-07 PROFILE_C: 1.0 CPU / 1024 m — `100000 100000` / `1073741824` en ambos motores
- [x] `memory.swap.max` = 0 en los tres (A7) — seis de seis
- [x] Límites leídos **dentro** del contenedor, no solo declarados en el compose — `docker exec … cat /sys/fs/cgroup/…` vía `capture_env.py`
- [x] `mem_swappiness` declarado en el compose como exige el manual, y su comportamiento real bajo cgroups v2 documentado (V8) — SPEC A7, `V8_mem_swappiness_20261101T171426Z.txt`
- [x] Evidencia por perfil y motor en `results/env/f1/` con digest de imagen y versión del motor — MongoDB 8.2.12 y PostgreSQL 18.6, digests en `image.repo_digests`
- [x] Prueba negativa de OOM con límites de PROFILE_C: exit 137, `memory.events oom_kill 1`, `OOMKilled=true` — `OOM_PROFILE_C_SEVERE_20261101T171903Z.txt`

### Dataset — carga escalonada
- [x] **G1** 1 000 registros cargados en ambos motores, esquema validado al 100 % — `results/f3/g1/compare.json`
- [x] **G1** `final_total` es número leído **desde el motor** (`jsonb_typeof` / `typeof`), no desde el archivo — `results/f3/g1/export_*.json`
- [x] **G1** `timestamp` es string ISO-8601 en ambos motores — `results/f3/g1/export_*.json`
- [x] **G2** 10 000 registros cargados; equivalencia Q1/Q2 verificada — `results/f3/g2/equivalence.json`
- [x] **G2** Planes capturados: queda registrado si cada motor usa o no su índice de timestamp — `results/explains/g2/`
- [x] **G3** R-08 500 000 registros en ambos motores, conteos iguales — `results/f3/g3/load_*.json`
- [x] **G3** Equivalencia Q1/Q2 re-verificada a escala real — `results/f3/g3/equivalence.json`
- [x] **G3** Planes re-capturados (la selectividad cambia con el volumen) — `results/explains/g3/`
- [x] R-09 3 niveles de anidamiento verificados; media de ítems en [2.9, 3.1] — `results/dataset_stats.json` (`anidamiento_niveles: {3: 500000}`, media 2.9991); prueba `test_profundidad_exactamente_3`
- [x] R-10 Todos los atributos de §4 presentes — validador `generator/schema.py`: 0 inválidos de 500 000 (`results/dataset_stats.json`); `tests/test_generator_schema.py` incluye pruebas de clave faltante y de clave de más
- [x] Mismo hash con la misma semilla (determinismo) — dos generaciones de 500 000: `0cd7fadb…0414` (`results/f2/F2_3_20261101T181011Z_verificacion.txt` §1)
- [x] `results/dataset_stats.json` publicado
- [x] Ninguna etapa se saltó: no se cargaron 500 k sin pasar G1 y G2 — registros `results/f3/g1/run_20261101T183329Z.txt` → `g2/run_20261101T185807Z.txt` → `g3/run_20261101T191648Z.txt`, cada uno revisado por Alix antes del siguiente

### Queries
- [x] R-11/R-12 Q1 idéntica al PDF en ambos motores (diff contra playbook.pdf §5.1) — `scripts/extract_queries.py --check` (`queries/README.md`)
- [x] R-13/R-14 Q2 idéntica al PDF, salvo desviaciones declaradas — idéntica, sin desviaciones (`queries/README.md`)
- [ ] R-16 Mongo: corridas con `allowDiskUse` false **y** true — *ya ejecutadas en la verificación de equivalencia (G2/G3); faltan las corridas del benchmark (F7/F8)*
- [ ] R-17 Postgres: corridas con `work_mem` 4MB **y** 64MB — *ídem; `SHOW work_mem` ya se registra por sesión (`queries_postgres.json`)*
- [ ] R-18 Ambas variantes de Q2 presentes en el CSV
- [x] Equivalencia Q1: grupos idénticos, `count` exacto, montos dentro de 1e-6 — `results/f3/g2/` y `results/f3/g3/equivalence.json`
- [x] Equivalencia Q2: los 1 000 `order_id` coinciden como conjunto — `results/f3/g2/` y `results/f3/g3/equivalence.json`

### Protocolo
- [ ] R-19 Concurrencias 1, 10, 50
- [ ] R-20 3 repeticiones por escenario
- [ ] R-21 Flush + warmup 60 s + medición 300 s + cooldown 60 s, con marcas de tiempo en log
- [ ] Flush con **efecto medido**, no solo código de salida: delta de `buff/cache` registrado por repetición — *implementado y visto en humo (`preparacion.flush` en cada crudo de `results/smoke*/raw/`); se marca con las corridas reales*
- [ ] Declarado en la sección 2 del reporte que la capa de caché de Windows sobre el `.vhdx` queda fuera de alcance, y que lo alcanzable es un estado repetible entre repeticiones
- [ ] R-22 Conteo de celdas conforme a lo decidido en A2

### Telemetría
- [x] R-23 Prometheus con `scrape_interval: 1s`; cAdvisor y node_exporter con `up==1` — `monitoring/prometheus.yml`; `results/f6/f6_1/check_monitoring_reposo_20261102T032714Z.json`, `results/f6/f6_3/check_monitoring_cadvisor_2cpu_*.json`, bajo carga `results/f6/f6_4/humo_f64/check_f64.json`
- [x] **R-24** Los 8 KPIs **mapeados** a columnas o a `status` — SPEC §4 (con las notas de interpretación de F6.2: throttling acumulado por CPU, `max_rss_mb` frente a `working_set`)
- [ ] **R-24** Los 8 KPIs **obtenidos en la matriz** (F8). En humo y en las sondas ya salieron: `results/f6/f6_4/humo_f64/`, `results/f6/probes/`
- [x] Throttling observado distinto de cero en PROFILE_C bajo carga de CPU — `results/f6/probes/throttling_profile_c_{postgresql,mongodb}_*.json` (143 s y 222 s en 120 s); humo Postgres C c=1: 338 s

Capacidad de detección (sondas, **no** resultados del benchmark):
- [x] Sonda de spill en Postgres (sort sin `LIMIT`) detectada por `temp_bytes` y por `EXPLAIN ANALYZE` — `results/f6/probes/spill_postgres_c_severe_20261102T044223Z.json`
- [x] Sonda de spill en Mongo (`$sort` sin `$limit`) detectada por contadores y `usedDisk` — `results/f6/probes/spill_mongo_c_severe_20261102T044309Z.json` (también sin `$project`: con él no llega a 100 MB)
- [x] Sonda de OOM contra `memory.max` clasificada como `status=oom` — `results/f6/probes/oom_engine_{postgresql,mongodb}_*.json` (dentro del contenedor del motor, por `assemble_row`); el OOM ya era observable en F1
- [x] Las sondas viven en `scripts/probes/`, no en `queries/`, y no producen filas del CSV — `results/f6/f6_5/sondas_sin_csv_20261102T105619Z.txt`
- [ ] En el reporte están etiquetadas como verificación de instrumento, en la sección 2

Resultados reales:
- [ ] `disk_spill` y `status` reflejan lo observado, sin valores por defecto
- [ ] Si no hubo spill en ninguna celda, se reporta así y M2 se responde con esa evidencia
- [ ] Si las dos variantes de Q2 dieron resultados equivalentes, se explica por qué (top-K acotado) en vez de omitirlo

---

## 2. CSV (crítico — diapo 9/13)

*El escritor y el validador ya garantizan lo de esta sección (`tests/test_csv_schema.py`, `tests/test_status_domain.py`; CSV de humo `VÁLIDO`). Las casillas se marcan sobre el CSV final de F8.*

- [ ] Encabezado **exacto**: `timestamp_epoch,engine,profile,query_id,concurrency,run_number,throughput_qps,latency_p50_ms,latency_p95_ms,latency_p99_ms,cpu_throttled_seconds,max_rss_mb,disk_spill,status`
- [ ] 14 columnas, ni una más
- [ ] Ninguna columna renombrada
- [ ] `profile` usa los IDs literales del playbook
- [ ] `status` ∈ {`ok`,`spill`,`oom`,`error`}
- [ ] `disk_spill` booleano consistente con `status`
- [ ] Una fila por repetición
- [ ] Sin filas duplicadas por clave (engine, profile, query_id, concurrency, run_number)
- [ ] Sin celdas vacías no justificadas
- [ ] `validate_csv.py` pasa sobre el CSV final
- [x] Prueba negativa: una columna extra hace fallar el validador — `tests/test_csv_schema.py` (`test_columna_extra_hace_fallar`, también renombrada y reordenada); `results/f5/tests_cierre_20261102T004918Z.txt`

---

## 3. Entregables de código (playbook.pdf §8.1)

- [x] `docker-compose.yml` parametrizado por perfiles — ejercitado con los 3 perfiles × 2 motores en F1 (`results/env/f1/up_*.txt`, `PROFILE_*`)
- [x] `synthetic_data_generator.py` (nombre exacto) — `generator/synthetic_data_generator.py`; ejecutado en `results/f2/F2_3_20261101T181011Z_generacion.txt`
- [x] Benchmark runner (Python multiproceso) — `benchmark_runner/` (10 procesos × 5 hilos para c=50); humo ejecutado en `results/smoke*/` con CSV `VÁLIDO`; suite 213/213 en `results/f5/tests_cierre_20261102T004918Z.txt` (PLAN F5)
- [x] `queries/` con las agregaciones Mongo y el SQL de Postgres — 4 archivos extraídos del PDF (`queries/README.md`)
- [x] `run_benchmarks.sh` (nombre exacto) — `scripts/run_benchmarks.sh`: recorre la matriz, reanudable desde el CSV (`benchmark_runner/schedule.py`), parametrizable para 36 o 54 celdas (A2) y por bloques. Probado en humo con motores reales: `results/f8_humo/run_benchmarks_20261102T145001Z.txt`

---

## 4. Reporte (playbook.pdf §8.3) y preguntas del revisor (diapo 11/13)

Secciones:
- [ ] 1. Especificaciones del host y del entorno Docker
- [ ] 2. Método de medición y verificación del baseline
- [ ] 3. Resultados consolidados (throughput, P95/P99, throttling)
- [ ] 4. Análisis gráfico: P99 vs concurrencia · throttling vs QPS · curva RSS
- [ ] 5. Planes de ejecución: `explain executionStats` vs `EXPLAIN ANALYZE BUFFERS`
- [ ] 6. Interpretación: límites de memoria, volcado a disco, throttling de cgroups
- [ ] 7. Recomendaciones técnicas para despliegues documentales en la nube

Trazabilidad de las 6 preguntas:
- [ ] 1. ¿Baseline comparable? → sección 2 + hash del dataset + diff de queries
- [ ] 2. ¿P50/P95/P99 o solo promedios? → sección 3, con el método de percentil declarado
- [ ] 3. ¿Hubo throttling CFS y cuántos segundos? → sección 3, columna `cpu_throttled_seconds`
- [ ] 4. ¿Spill u OOM, en qué perfil y concurrencia? → sección 6 + `results/logs/`
- [ ] 5. ¿Cuántas repeticiones y cómo se resume? → sección 2 (media o mediana, declarado y justificado)
- [ ] 6. ¿El plan de ejecución respalda el cuello de botella? → sección 5

Preguntas de métricas:
- [ ] M1 respondida con datos (P95/P99 vs perfil)
- [ ] M2 respondida con datos (spill/OOM por motor)
- [ ] M3 respondida con datos (huella por 1 000 documentos, denominador de los planes)

---

## 5. Integridad experimental

- [ ] Ningún número del reporte escrito a mano: todos trazables a `results/`
- [ ] Ninguna captura, log o métrica fabricada
- [ ] Ninguna sonda de detección presentada como resultado del benchmark
- [ ] Ningún fenómeno esperado (spill, OOM) reportado como ocurrido sin evidencia de que ocurrió
- [ ] Las celdas fallidas se reportan como fallidas, no se omiten
- [ ] Las desviaciones respecto del manual están declaradas, no escondidas
- [ ] Las limitaciones (baseline imperfecto, baja densidad muestral, booleano de spill) están escritas
- [ ] Las diferencias numéricas entre motores por tipos (double vs numeric) están documentadas

---

## 6. Reproducibilidad (diapo 10/13)

- [ ] `README.md` documenta el entorno Windows + WSL2 + Docker Desktop y advierte que otro equipo sobre Linux nativo obtendrá valores distintos
- [ ] `README.md` indica que el repositorio debe clonarse dentro del sistema de archivos de WSL2, no en `/mnt/c/`
- [ ] `.wslconfig` versionado en el repo si se decidió usarlo (D-WSL1)
- [ ] `README.md` con prerrequisitos, pasos numerados y tiempo esperado
- [ ] Advertencia explícita de `sudo` para el flush de caché
- [x] `requirements.txt` con versiones fijadas — `pymongo==4.19.0`, `dnspython==2.9.1`, `psycopg==3.3.6`, `psycopg-binary==3.3.6`; instalación registrada en `results/env/f5/pip_install_20261101T204524Z.txt`
- [x] Imágenes fijadas por digest, registrado en `results/env/` — `docker/images.env` usa `@sha256:…`; arranque y límites comprobados en `results/env/f1/PROFILE_A_BASELINE_*_20261101T1742*Z.{txt,json}`
- [x] Semilla del generador versionada — `SEED = 42` en `generator/distributions.py`; registrada en `results/dataset_stats.json` (`semilla: 42`) junto con el SHA-256 de cada fuente del generador
- [ ] `results/raw/` con latencias crudas (permite recalcular percentiles) — *el runner guarda cada muestra con su worker y la serie de 1 s del cgroup; ya hay corridas reales en `results/f7/raw/`. `results/raw/` se llena con la matriz (F8)*
- [ ] `results/explains/` con planes crudos — *parcial: G2 y G3 bajo PROFILE_A, más la celda del piloto en `results/f7/explains/` (uno por celda, en la repetición 1). R-31 pide uno por motor × query × perfil: se completa en F8*
- [ ] `results/env/` con límites reales, versiones y datos del host por corrida
- [ ] El README advierte que los valores absolutos dependen del hardware
- [ ] Prueba de reproducibilidad: un tercero sigue el README y obtiene un CSV válido

---

## 7. Preparación para la defensa

Preguntas que debo poder contestar sin leer notas:

- [ ] ¿Por qué el runner vive fuera del contenedor medido?
- [ ] ¿Por qué `timestamp` es string y no `Date` en Mongo?
- [ ] ¿Qué pasa si `final_total` fuera string? (orden lexicográfico ≠ numérico)
- [ ] ¿Por qué el throttling de CFS sube la latencia de cola y no tanto la mediana?
- [ ] ¿Por qué `$unwind` antes de `$match` es caro, y por qué no lo "optimicé"?
- [ ] ¿Qué es un top-K sort y por qué `LIMIT 1000` puede hacer que nunca haya spill?
- [ ] Si no hubo spill, ¿por qué eso responde M2 en vez de invalidar el experimento?
- [ ] ¿Cuál es la diferencia entre una sonda de detección y una medición del benchmark?
- [ ] ¿Por qué un índice puede estar bien construido y aun así no aparecer en el `EXPLAIN`?
- [ ] ¿Qué hace exactamente `jsonb_array_elements` y por qué el costo es comparable al `$unwind`?
- [ ] Diferencia entre spill a disco y OOM, y por qué `allowDiskUse:false` fuerza lo segundo
- [ ] Por qué `mem_swappiness: 0` no basta para desactivar el swap
- [ ] Qué método de percentil usé y por qué cambia el P99
- [ ] Por qué JSONB y BSON no son comparables campo a campo
- [ ] Qué decisiones tomé ante las ambigüedades del manual y qué alternativa descarté
