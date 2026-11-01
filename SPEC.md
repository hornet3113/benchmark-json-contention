# SPEC.md — Especificación del experimento

**Proyecto:** Contención de CPU y memoria en agregaciones JSON — MongoDB vs PostgreSQL JSONB
**Materia:** Bases de Datos en la Nube · IT2iD · UPChiapas · 2026
**Estado:** BORRADOR — contiene decisiones marcadas `PENDIENTE DE VALIDACIÓN` que no deben asumirse aprobadas.

Fuentes normativas:

- `playbook.pdf` (especificación técnica principal, 4 páginas)
- `playbook_sesion.pdf` (contrato de entrega, 13 diapositivas)

Regla de precedencia propuesta: ante conflicto, `playbook.pdf` define **qué se mide**; `playbook_sesion.pdf` define **qué se entrega**. Donde los dos chocan (ver §5, A2), se escala al docente.

---

## 1. Matriz de requisitos obligatorios

Tipo: **OBL** = exigido literalmente · **DER** = derivado inequívocamente del texto · **AMB** = exigido pero ambiguo (ver §5).

| ID | Requisito | Fuente | Tipo | Cómo se verifica |
|----|-----------|--------|------|------------------|
| R-01 | MongoDB: colección `orders`, sin sharding, motor WiredTiger | playbook.pdf §2, p.1 | OBL | `db.orders.stats().wiredTiger` existe; `sh.status()` sin shards |
| R-02 | MongoDB: índice en `timestamp` y en `order_id` | playbook.pdf §2, p.1 | AMB | `db.orders.getIndexes()` en evidencia |
| R-03 | PostgreSQL: tabla `orders (id UUID PRIMARY KEY, data JSONB)` | playbook.pdf §2, p.1 | OBL | `\d+ orders` en evidencia |
| R-04 | PostgreSQL: índice B-Tree sobre `timestamp` extraído del JSONB | playbook.pdf §2, p.1 | AMB | `\di+` + `EXPLAIN` que lo use |
| R-05 | Perfil A: 4.0 CPUs, 4096 m, `mem_swappiness=0` | playbook.pdf §3, p.1 | OBL | `cpu.max` y `memory.max` del cgroup del contenedor |
| R-06 | Perfil B: 2.0 CPUs, 2048 m, `mem_swappiness=0` | playbook.pdf §3, p.1 | OBL | ídem |
| R-07 | Perfil C: 1.0 CPU, 1024 m, `mem_swappiness=0` | playbook.pdf §3, p.1 | OBL | ídem |
| R-08 | Dataset: 500 000 registros JSON | playbook.pdf §4, p.1 | OBL | `count()` = 500000 en ambos motores |
| R-09 | 3 niveles de anidamiento, promedio ~3 ítems por registro | playbook.pdf §4, p.1 | AMB | Estadísticas del generador en `results/dataset_stats.json` |
| R-10 | Atributos: `order_id`, `timestamp`, `customer{id,tier,segment,geo{country,state,city,zip,coordinates}}`, `items[{sku,category,brand,qty,price,tax_pct,discounts}]`, `payment{method,status,transaction_id,gateway_latency_ms,totals}`, `metadata{channel,user_agent,session_id,flags}` | playbook.pdf §4, pp.1–2 | AMB | Validación de esquema sobre muestra |
| R-11 | Q1 MongoDB: pipeline literal `$unwind → $match price>50 → $group` | playbook.pdf §5.1, p.2 | OBL | Diff contra el PDF; archivo en `queries/` sin modificar |
| R-12 | Q1 PostgreSQL: SQL literal con `jsonb_array_elements` | playbook.pdf §5.1, p.2 | OBL | ídem |
| R-13 | Q2 MongoDB: `$match status=completed + timestamp>=2026-01-01 → $sort final_total desc → $limit 1000 → $project` | playbook.pdf §5.2, pp.2–3 | AMB | ídem |
| R-14 | Q2 PostgreSQL: SQL literal con `ORDER BY ... DESC LIMIT 1000` | playbook.pdf §5.2, p.3 | AMB | ídem |
| R-15 | Q2 sin índice previo sobre el total | playbook.pdf §5.2, p.2 | OBL | `getIndexes()` / `\di` no listan `final_total` |
| R-16 | Variantes Mongo: `allowDiskUse: false` y `true` | playbook.pdf §5.2, p.2 | OBL | Dos corridas distintas registradas |
| R-17 | Variantes PostgreSQL: `work_mem = '4MB'` y `'64MB'` | playbook.pdf §5.2, p.2 | OBL | `SHOW work_mem` por sesión en log |
| R-18 | Reportar **ambas** variantes de Q2 (sin spill y con spill/OOM) | playbook_sesion.pdf diapo 7/13 | OBL | Filas CSV de ambas variantes |
| R-19 | Concurrencias 1, 10, 50 | playbook.pdf §6, p.3 | OBL | Columna `concurrency` del CSV |
| R-20 | 3 repeticiones por escenario | playbook.pdf §6, p.3 | OBL | `run_number` ∈ {1,2,3} |
| R-21 | Ciclo: flush de caché (`sync; echo 3 > /proc/sys/vm/drop_caches`) → warmup 60 s → medición 300 s → cooldown 60 s | playbook.pdf §6, p.3; diapo 8/13 | AMB | Log con marcas de tiempo por fase |
| R-22 | Matriz de 36 celdas (2 motores × 3 perfiles × 2 queries × 3 concurrencias), cada una × 3 repeticiones | playbook.pdf §6, p.3; diapo 8/13 | AMB | Conteo de filas del CSV consolidado |
| R-23 | Telemetría: cAdvisor + Node Exporter + Prometheus con `scrape_interval: 1s` | playbook.pdf §7, p.3 | OBL | `prometheus.yml` versionado + targets `up==1` |
| R-24 | KPIs: `throughput_qps`, `latency_p50/p95/p99_ms`, `container_cpu_cfs_throttled_seconds_total`, `container_memory_rss_bytes`, `disk_spill_detected`, `oom_killed` | playbook.pdf §7, p.3 | AMB | Mapeo KPI→columna documentado en §4 |
| R-25 | Entregables de código: `docker-compose.yml` parametrizado, `synthetic_data_generator.py`, benchmark runner (k6 o Python multiproceso), `queries/`, `run_benchmarks.sh` | playbook.pdf §8.1, p.4; diapo 10/13 | OBL | Existencia en el repo con esos nombres |
| R-26 | Esquema CSV exacto de 14 columnas, **sin columnas inventadas ni renombradas** | playbook.pdf §8.2, p.4; diapo 9/13 | OBL | `scripts/validate_csv.py` compara encabezado byte a byte |
| R-27 | Una fila CSV por repetición + nota de estado (`ok`/`spill`/`oom`/`error`) | diapo 8/13 | OBL | Dominio cerrado en el validador |
| R-28 | Registrar siempre: `profile`, límites Docker **reales**, versión del motor, si hubo spill/OOM | diapo 5/13 | OBL | `results/env/` por corrida |
| R-29 | Reporte de métricas con las 7 secciones del playbook | playbook.pdf §8.3, p.4; diapo 10/13 | OBL | Índice del reporte |
| R-30 | Figuras: P99 vs concurrencia, throttling vs QPS, curva RSS | playbook.pdf §8.3 (sec. 4), p.4 | OBL | 3 figuras en `report/figures/` |
| R-30.1 | **La figura de P99 contra concurrencia muestra las dos vistas, o marca los puntos contaminados** (Alix, 2026-11-02, al aprobar F7-e). Con c=50 en PROFILE_B y C, hasta el 91 % de la ventana son primeras consultas en frío (F7.3): la curva sube en parte por el arranque en frío, y eso no puede quedar en una nota al pie. Las dos vistas se calculan de los crudos, que guardan cada muestra con su worker | F7.3, `docs/F7_PILOTO.md` | OBL | La figura distingue el P99 del CSV del P99 sin las primeras consultas |
| R-31 | Planes de ejecución: `explain executionStats` vs `EXPLAIN ANALYZE BUFFERS` | playbook.pdf §8.3 (sec. 5), p.4; diapo 11/13 | OBL | Un plan por motor × query × perfil en `results/explains/` |
| R-32 | Capturas o logs de spill/OOM como evidencia | diapo 10/13 | OBL | `results/logs/` referenciado desde el reporte |
| R-33 | Reproducibilidad: otro equipo debe poder reejecutar | diapo 10/13 | OBL | Ver §7 (lista de archivos) |
| R-34 | Celda piloto (1 motor × 1 query × 1 concurrencia) y validación del CSV **antes** de la matriz completa | diapo 13/13 | OBL | Fase 7 del PLAN |
| R-35 | El reporte responde las 6 preguntas del revisor con tablas/figuras, no con opiniones | diapo 11/13 | OBL | Trazabilidad pregunta→tabla en CHECKLIST |

---

## 2. Arquitectura técnica

Tres planos separados, para que la carga de trabajo no contamine lo medido:

```
┌──────────────────────── HOST (Linux, cgroups v2) ─────────────────────────┐
│                                                                           │
│  PLANO DE CARGA            PLANO BAJO PRUEBA        PLANO DE OBSERVACIÓN  │
│  ┌──────────────────┐      ┌─────────────────┐      ┌──────────────────┐  │
│  │ benchmark_runner │─────▶│  mongo | postgres│◀─────│ cAdvisor         │  │
│  │ (proceso host,   │      │  cgroup limitado │      │ node_exporter    │  │
│  │  N procesos)     │      │  por perfil A/B/C│      │ Prometheus (1 s) │  │
│  └────────┬─────────┘      └────────┬────────┘      └────────┬─────────┘  │
│           │                         │                        │            │
│           │ latencias por query     │ cgroup v2 (cpu.stat,   │ series     │
│           │ (reloj monotónico)      │ memory.peak, memory.   │ temporales │
│           ▼                         ▼ events)                ▼            │
│      ┌─────────────────────────────────────────────────────────────┐      │
│      │  Agregador → results/raw/<cell>.json → measurements.csv      │      │
│      └─────────────────────────────────────────────────────────────┘      │
└───────────────────────────────────────────────────────────────────────────┘
```

Decisiones de arquitectura y su razón:

1. **Solo un motor corre a la vez.** Levantar Mongo y Postgres simultáneamente los hace competir por el page cache del host y rompe la comparabilidad. `run_benchmarks.sh` levanta un perfil de un motor, mide, lo baja.
2. **El runner vive en el host, fuera del cgroup medido.** Si el runner estuviera dentro del contenedor limitado, consumiría la CPU que se le quiere restringir al motor y el experimento mediría otra cosa. Se le asigna su propio `cpuset` para que tampoco robe núcleos al motor.
3. **Dos fuentes de métricas de recursos, con jerarquía explícita.** El valor que va al CSV se toma de los archivos cgroup v2 leídos justo antes y justo después de la ventana de 300 s (delta exacto, sin aliasing de muestreo). Prometheus/cAdvisor alimenta las **curvas** del reporte (figura de RSS, throttling vs QPS). Esto se documenta para que un revisor sepa de dónde salió cada número.
4. **Latencia medida en el cliente**, con reloj monotónico, por query completada. Incluye round-trip de red del socket Docker: es lo que percibe la aplicación, y es simétrico entre motores.
5. **Los planes de ejecución se capturan fuera de la ventana medida** (durante el cooldown), porque `EXPLAIN ANALYZE` y `explain executionStats` ejecutan trabajo real y distorsionarían el throughput.
6. **El CSV se escribe una fila por repetición, al cerrar la repetición**, nunca al final de la matriz: si la corrida de 19 h se interrumpe, lo medido hasta ahí sobrevive.

### Cómo aterriza esta arquitectura en Windows + WSL2 + Docker Desktop

```
┌───────────────── Windows 11 · Ryzen 5 PRO 5675U · 14.8 GiB ─────────────────┐
│  Caché de archivos de Windows sobre el .vhdx  ← fuera de alcance (L4)       │
│ ┌──────────── VM de WSL2 · 12 CPUs lógicas · 7.159 GiB · kernel único ─────┐│
│ │  distro "Ubuntu"                     distro "docker-desktop"             ││
│ │  ┌────────────────────┐              ┌─────────────────────────────────┐ ││
│ │  │ Python: generador, │──localhost──▶│ contenedor del motor (cgroup    │ ││
│ │  │ runner, scripts .sh│   :27017     │ limitado por perfil A/B/C)      │ ││
│ │  │ repo en ~/ (L6)    │   :5432      │ cAdvisor · node_exporter · Prom │ ││
│ │  └────────────────────┘              └─────────────────────────────────┘ ││
│ │     ↑ mismas CPUs y misma memoria que el motor (L5)                      ││
│ │     cgroups v2 · vm.drop_caches global al kernel de la VM                 ││
│ └──────────────────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────────────────┘
```

Consecuencias operativas de este reparto:

- **Python y los scripts Bash se ejecutan desde la distribución `Ubuntu`**, que ya tiene la integración de Docker Desktop habilitada (`docker version` respondió desde ahí en F0).
- **El repositorio, el dataset y los volúmenes viven en `~/` dentro de Ubuntu**, nunca en `/mnt/c/` (L6).
- **La latencia se mide desde Ubuntu hacia el puerto publicado del contenedor.** Ese camino atraviesa la integración de Docker Desktop. Es el mismo camino para los dos motores, así que la comparación sigue siendo justa, pero el valor absoluto incluye ese tramo y se declara.
- **El `cpuset` del runner** es la única separación posible entre carga y motor, porque ambos están en la misma VM (L5).
- **cAdvisor y node_exporter observan la VM**, no Windows. `container_memory_rss_bytes` y `container_cpu_cfs_throttled_seconds_total` son correctos para el contenedor; las métricas "de host" son de la VM.

### Modelo de datos equivalente

| Aspecto | MongoDB | PostgreSQL | Por qué así |
|---------|---------|------------|-------------|
| Identidad | `_id` ObjectId + campo `order_id` (string UUID) | `id UUID PRIMARY KEY` + `data->>'order_id'` igual a `id` | El manual pide ambas formas; mantener el mismo UUID permite cruzar resultados documento a documento |
| `timestamp` | **string** ISO-8601 | **string** dentro del JSONB | El manual dice "ISO-8601" (§4) y el pipeline Q2 compara contra un literal de texto. Si se guardara como `Date` en Mongo, el `$gte` contra string no haría match por el bracketing de tipos de BSON |
| Números (`qty`, `price`, `final_total`) | `double` BSON | número JSON → `::numeric` al consultar | Diferencia real de semántica: Postgres suma en decimal exacto, Mongo en punto flotante. Las sumas se comparan con tolerancia relativa, no con igualdad |
| `coordinates` | arreglo `[lon, lat]` de doubles | ídem | Nivel 3 de anidamiento |

---

## 3. Estructura de carpetas

```
benchmark-json-contention/
├── README.md                      # arranque en 10 pasos para un tercero
├── SPEC.md  PLAN.md  CHECKLIST.md
├── docker/
│   ├── docker-compose.yml         # R-25: perfiles parametrizados por .env
│   ├── profiles/{a_baseline,b_medium,c_severe}.env
│   ├── mongo/init.js              # índices R-02
│   └── postgres/{init.sql,postgresql.conf}
├── monitoring/
│   ├── prometheus.yml             # scrape_interval: 1s (R-23)
│   └── docker-compose.monitoring.yml
├── generator/
│   ├── synthetic_data_generator.py  # R-25, nombre exacto
│   ├── schema.py                  # contrato de atributos (R-10)
│   └── distributions.py           # catálogos y pesos, con semilla fija
├── queries/
│   ├── mongo/{q1_unwind_group.json,q2_sort_topk.json}
│   └── postgres/{q1_unwind_group.sql,q2_sort_topk.sql}
├── benchmark_runner/
│   ├── cli.py  config.py  matrix.py
│   ├── engines/{base.py,mongo.py,postgres.py}
│   ├── workload.py                # bucle cerrado, warmup/medición/cooldown
│   ├── metrics/{cgroup.py,prometheus.py,spill.py,percentiles.py}
│   ├── csv_writer.py              # único punto que conoce el esquema (R-26)
│   └── explain.py                 # R-31
├── scripts/
│   ├── run_benchmarks.sh          # R-25, nombre exacto
│   ├── flush_caches.sh            # R-21, requiere sudo
│   ├── load_dataset.sh
│   ├── validate_csv.py
│   └── capture_env.py             # R-28: límites reales + versiones + digests
├── tests/                         # pytest
├── results/
│   ├── raw/  explains/  logs/  env/
│   ├── dataset_stats.json
│   └── measurements.csv
└── report/
    ├── reporte_metricas.md        # 7 secciones (R-29)
    └── figures/
```

---

## 4. Esquema CSV y mapeo de KPIs

Encabezado **literal**, sin espacios tras las comas, en este orden (R-26):

```
timestamp_epoch,engine,profile,query_id,concurrency,run_number,throughput_qps,latency_p50_ms,latency_p95_ms,latency_p99_ms,cpu_throttled_seconds,max_rss_mb,disk_spill,status
```

| Columna | Dominio propuesto | Origen del dato |
|---------|-------------------|-----------------|
| `timestamp_epoch` | entero, segundos UTC | Inicio de la ventana de medición |
| `engine` | `mongodb` \| `postgresql` | Configuración de la celda |
| `profile` | `PROFILE_A_BASELINE` \| `PROFILE_B_MEDIUM` \| `PROFILE_C_SEVERE` | IDs literales de playbook.pdf §3 |
| `query_id` | `Q1` \| `Q2_MEM_LOW` \| `Q2_MEM_HIGH` | Ver ambigüedad A2 — **PENDIENTE DE VALIDACIÓN** |
| `concurrency` | 1 \| 10 \| 50 | |
| `run_number` | 1 \| 2 \| 3 | |
| `throughput_qps` | float, queries completadas ÷ 300 | Runner |
| `latency_p50/p95/p99_ms` | float, 3 decimales | Percentiles sobre latencias completadas en la ventana |
| `cpu_throttled_seconds` | float | Delta de `throttled_usec` en `cpu.stat` del cgroup ÷ 1e6 (equivale a `container_cpu_cfs_throttled_seconds_total`) |
| `max_rss_mb` | float | Pico de `anon` en `memory.stat` vía muestreo 1 s, contrastado con `memory.peak` |
| `disk_spill` | `true` \| `false` | Ver ambigüedad A6 |
| `status` | `ok` \| `spill` \| `oom` \| `error` | Precedencia: `oom` > `error` > `spill` > `ok` |

Nota de diseño: `oom_killed` es KPI (R-24) pero **no tiene columna**. Se codifica en `status=oom`, porque diapo 9/13 prohíbe agregar columnas. `disk_spill` sí tiene columna propia, así que una corrida puede terminar con `disk_spill=true` y `status=spill` a la vez; `status=ok` con `disk_spill=true` queda prohibido por el validador.

**Notas de interpretación medidas en F6.2** (`docs/F6_TELEMETRIA.md`, aprobadas por Alix el 2026-11-02). No cambian ninguna columna:

- **`cpu_throttled_seconds` puede ser mayor que la duración de la ventana.** El kernel suma el tiempo de throttling de **cada CPU** en la que el cgroup tenía hilos listos para correr; cAdvisor reporta la misma suma. Medido: 104.6 s en 91 s (Postgres) y 162 s en 91 s (Mongo), con 2 bucles contra 1 CPU de cuota. El eje de la figura de throttling (R-30) no debe acotarse a la ventana, y el reporte lo explica.
- **`max_rss_mb` no cuenta lo mismo en los dos motores (F6-A3).** Es `anon` de `memory.stat`, que es exactamente `container_memory_rss` de cAdvisor (comprobado con el contenedor congelado). Pero los `shared_buffers` de Postgres son memoria compartida (`shmem`), no `anon`, mientras que el caché de WiredTiger de Mongo sí es `anon`. Con `max_rss_mb`, Postgres sale **artificialmente eficiente**. Se declara en la sección del reporte que interpreta la memoria; `results/raw/` guarda además `shmem`, `file` y `memory.current` cada 1 s (`serie_cgroup_1s`), y la exportación de Prometheus incluye `container_memory_working_set_bytes`.
- **Throttling de fondo.** Parte del throttling de Mongo en PROFILE_C ocurre en reposo, sin benchmark (~4 s por minuto en F6.2). La línea base en reposo por perfil y motor se mide en F6.3 y se declara junto a la columna.

---

## 5. Ambigüedades del manual y resoluciones propuestas

Ninguna de estas resoluciones está aprobada. Cada una lleva impacto y qué pasa si el docente decide lo contrario.

### A1 — `payment.final_total` frente a `payment.totals` ⚠️ ALTA

**El conflicto.** playbook.pdf §4 (p.2) define `payment` como objeto con `{method, status, transaction_id, gateway_latency_ms, totals}`: no menciona `final_total`, y sugiere que los importes viven dentro de `totals`. Pero Q2 (§5.2, pp.2–3) ordena por `"payment.final_total"` en Mongo y por `data->'payment'->>'final_total'` en SQL, es decir, **hijo directo de `payment`**. Los dos no pueden ser ciertos a la vez sin una decisión explícita.

**Opciones.**

| Opción | Qué implica | Costo |
|--------|-------------|-------|
| (a) `payment.totals = {subtotal, tax, discount}` y `payment.final_total` como hermano | Las queries del manual corren **literalmente**; `totals` existe como exige §4 | Ninguno funcional; hay que justificar que `final_total` no vive dentro de `totals` |
| (b) Duplicar: `payment.totals.final_total` **y** `payment.final_total` | Cubre ambas lecturas | Redundancia en 500 k documentos; un revisor puede leerlo como parche |
| (c) Solo `payment.totals.final_total` y reescribir Q2 | Respeta §4 al pie | **Viola R-13/R-14**: modifica las queries literales del manual |

**Propuesta: opción (a).** Es la única que no toca ni el esquema exigido ni las queries exigidas. Se documenta en el reporte como decisión explícita.

**Trampa técnica asociada.** `final_total` debe generarse como **número JSON**, no como string. En Postgres el `::numeric` fuerza el orden numérico; en Mongo `$sort` ordenaría lexicográficamente si fuera string (`"9.5" > "100.0"`), y los Top-1000 de ambos motores **no coincidirían**. La prueba de equivalencia de la Fase 4 existe justamente para atrapar esto.

### A2 — 36 escenarios frente a las variantes de Q2 ⚠️ ALTA

**El conflicto.** playbook.pdf §6 (p.3) y diapo 8/13 fijan 36 celdas = 2 motores × 3 perfiles × 2 queries × 3 concurrencias, × 3 repeticiones = **108 corridas**. Pero §5.2 (p.2) exige dos variantes de estrés de memoria para Q2 y diapo 7/13 dice explícitamente que hay que reportar **ambas**. Si Q2 son dos configuraciones distintas, el conteo real es:

- Q1: 2 × 3 × 3 = 18 celdas
- Q2: 18 × 2 variantes = 36 celdas
- **Total: 54 celdas → 162 corridas**

Y además el CSV (§8.2) **no tiene columna para la variante**, mientras diapo 9/13 prohíbe inventar columnas.

**Opciones.**

| Opción | Celdas | Respeta R-18 | Respeta R-26 |
|--------|--------|--------------|--------------|
| (a) Codificar la variante en `query_id`: `Q1`, `Q2_MEM_LOW`, `Q2_MEM_HIGH` | 54 | Sí | Sí (`query_id` es un valor, no una columna nueva) |
| (b) Agregar columna `variant` | 54 | Sí | **No** |
| (c) Una sola variante de Q2 por perfil (p. ej. restrictiva en C, permisiva en A) | 36 | **No** | Sí |
| (d) 36 celdas y las variantes solo como anexo cualitativo | 36 | Parcial | Sí |

**Propuesta: opción (a).** Mantiene el esquema intacto y cumple el requisito de reportar ambas variantes; el reporte presenta "36 celdas canónicas" donde Q2 aporta dos sub-filas por celda.

**Costo que obliga a validar esto antes de implementar:** 162 corridas × 420 s = **18.9 h** solo de ventanas de tiempo, sin contar flush, arranque de contenedores, recarga de dataset y captura de planes. Realista: 24–30 h de máquina. Con la lectura de 36 celdas serían ~12.6 h. **Esta pregunta hay que hacérsela al docente antes de la Fase 8**, porque duplica el costo del proyecto.

### A3 — Índices y tipos de datos: condiciones de comparabilidad ⚠️ ALTA

Tres subproblemas distintos.

**A3.1 — "Índice simple en `timestamp` y `order_id`" (Mongo).** Puede leerse como dos índices de un campo o como uno compuesto `{timestamp: 1, order_id: 1}`. *Propuesta:* dos índices simples e independientes. Razón: "índice simple" es término técnico de MongoDB y se opone a "compuesto"; además ninguna query usa los dos campos juntos.

**A3.2 — Índice B-Tree sobre `timestamp` extraído del JSONB (Postgres).** ✅ RESUELTA en F3-G1 (2026-11-01). Dos problemas encadenados, y el segundo pesa más que el primero.

*Problema 1 — qué índice se puede crear. Comprobado contra el servidor* (PostgreSQL 18.6, `results/f3/g1/a32_index_variants.txt`, script `scripts/checks/a32_index_variants.sql`):

| Variante | Resultado en el servidor |
|---|---|
| `((data->>'timestamp'))`, texto sin conversión | **Se crea** |
| `(((data->>'timestamp')::timestamp))` | `ERROR:  functions in index expression must be marked IMMUTABLE` |
| `(((data->>'timestamp')::timestamptz))`, la que usa Q2 | `ERROR:  functions in index expression must be marked IMMUTABLE` |

**Las dos variantes con conversión fallan**, no solo la de `timestamptz`. El motivo, medido en el catálogo:

```
 tipo        | funcion_entrada | volatilidad
-------------+-----------------+-------------
 timestamp   | timestamp_in    | s
 timestamptz | timestamptz_in  | s
```

La conversión de `text` a `timestamp` o `timestamptz` usa la función de entrada del tipo de destino, y **`timestamp_in` y `timestamptz_in` son `STABLE` (`s`)**, no `IMMUTABLE`. Un índice de expresión exige que todas sus funciones sean `IMMUTABLE`. Esto refuta lo que la versión anterior de este documento dejó como hipótesis ("bastaba usar `::timestamp`").

*Corrección de método.* La versión anterior proponía verificar la volatilidad buscando la función del cast en `pg_cast.castfunc`. Esa consulta estaba mal planteada: **`pg_cast` no tiene ninguna entrada de `text` a `timestamp` ni a `timestamptz`** (devolvió 0 filas), porque esa conversión no es un cast registrado. Por eso se eliminó de aquí. Lo que hay que consultar es la función de entrada del tipo (`pg_type.typinput` → `pg_proc.provolatile`), y sobre todo intentar crear el índice: el mensaje del servidor es la evidencia.

*Problema 2 — aunque el índice exista, Q2 probablemente no lo use.* El predicado de Q2 selecciona ~50 % de la tabla (ver A8). Con esa selectividad el planner elige recorrido secuencial sobre índice casi siempre, porque el acceso aleatorio al heap para medio millón de filas sale más caro. Es decir: **el índice puede estar bien construido y aun así no aparecer en el `EXPLAIN`**. Eso no es un defecto del trabajo, es un resultado que se reporta. Además, el índice de texto no coincide con la expresión `::timestamptz` del predicado de Q2, así que el planner no puede usarlo para ese filtro.

*Opciones, ordenadas por cuánto respetan el manual.*

| Opción | Índice creable | Q2 intacta | ¿Lo usaría el planner? |
|--------|----------------|-----------|------------------------|
| (1) Índice sobre el texto crudo `((data->>'timestamp'))` | **Sí (comprobado)** | Sí | No: no coincide con el predicado con conversión |
| (2) Índice sobre `((data->>'timestamp')::timestamp)` | **No (comprobado)**: `timestamp_in` es `STABLE` | Sí | — |
| (3) Opción 2 **más** cambiar el cast dentro de Q2 | **No**: depende de la opción 2 | **No** | — |
| (4) Función `IMMUTABLE` envolvente, invocada desde Q2 | Sí (no probado) | **No** | Solo si la selectividad lo justificara: probablemente no |

**Decisión (A3.2), confirmada por la prueba: opción (1).** Es la única que cumple R-04 al pie de la letra ("B-Tree sobre timestamp extraído del JSONB") sin tocar una sola letra de Q2, y la prueba de F3-G1 muestra que las opciones (2) y (3) ni siquiera son posibles. La (4) queda en reserva y solo se aplicaría con aprobación explícita del docente: además de modificar Q2, obliga a declarar `IMMUTABLE` una función que Postgres considera `STABLE`, y eso es una afirmación falsa ante el planner que habría que justificar.

*Consecuencia que hay que vigilar — asimetría de planes.* MongoDB sí puede elegir su índice de `timestamp` para el `$match` de Q2 aunque la selectividad sea baja. Si Mongo usa índice y Postgres hace recorrido secuencial, la diferencia de latencia no mide "documental vs JSONB": mide dos planes distintos. Hay que capturar ambos planes (R-31) y, si divergen, decirlo en la sección 5 del reporte en vez de atribuir la diferencia al motor.

**A3.3 — Asimetría de índices entre motores.** Tal como está escrito el manual, Mongo termina con 3 índices (`_id` automático, `timestamp`, `order_id`) y Postgres con 2 (PK sobre `id`, expresión sobre timestamp). Para el experimento esto casi no importa —ni Q1 ni Q2 filtran por `order_id`/`_id`— pero sí encarece la carga inicial de Mongo y su huella en disco. *Propuesta:* implementarlo literal como dice el manual y declarar la asimetría en la sección 2 del reporte, en vez de "emparejar" por cuenta propia.

**A3.4 — Tipos.** JSONB reordena claves, elimina duplicados y normaliza números; BSON preserva orden y tipos nativos. Consecuencia medible: el tamaño en disco y el costo de parseo **no son comparables campo a campo**, solo end-to-end. Y las sumas de Q1 difieren en los últimos dígitos (double vs numeric). *Propuesta:* generar precios con 2 decimales y comparar agregados con tolerancia relativa de 1e-6; registrar la diferencia observada en el reporte en vez de esconderla.

### A4 — Ventana de 300 s con queries más lentas que la ventana ⚠️ ALTA

En PROFILE_C (1 CPU) con concurrencia 50, Q1 recorre 500 k documentos haciendo `$unwind`. Es perfectamente posible que **ninguna query complete** en 300 s, o que completen 3 o 4. Con 4 muestras, un P99 no significa nada.

*Propuesta de política, a validar:*
- Se cuentan solo queries **completadas** dentro de la ventana; las en vuelo se descartan al cerrar.
- Con menos de 20 muestras completadas, los percentiles se escriben igual pero la celda se marca en el reporte como *baja densidad muestral* (el CSV no tiene columna para ello, así que va en el log y en la tabla del reporte).
- Timeout duro por query: 300 s. Si ninguna completa, `throughput_qps=0`, latencias vacías y `status=error`.

Sin esta política, la alternativa es inventar números — lo que el proyecto prohíbe.

**Ampliación decidida por Alix (2026-11-01, tras la prueba de humo F5.5): datos censurados por la derecha.** En el humo, Q1 en Postgres con concurrencia 50 tuvo 4 consultas completadas y 46 que llegaron al límite de 300 s. Con la regla anterior la fila salía `spill` con un P99 de 279 s calculado solo con las supervivientes, cuando el P99 real es ≥ 300 s. Una consulta que llega al límite es un dato **censurado por la derecha**: se sabe que tardaría al menos 300 s, pero no cuánto.

- Fracción de timeouts f = timeouts / (completadas + timeouts), entre las consultas que **terminaron** dentro de la ventana.
- El percentil p solo es válido si f < 1 − p: **P99 si f < 1 %, P95 si f < 5 %, P50 si f < 50 %**.
- **Con f ≥ 1 % la fila sale `status=error`.** Las latencias de las completadas se escriben igual y no se corrigen, y `disk_spill` sigue diciendo lo observado.
- La fracción exacta y la validez de cada percentil se guardan por repetición en `results/raw/` (campo `censura`), para que el reporte diga por celda qué percentiles valen.
- En el reporte se declara que son datos censurados por la derecha en 300 s.

Implementado en `benchmark_runner/runner.py` (`censoring`, `assemble_row`) y `config.py` (`CENSORED_ERROR_FRACTION`, `PERCENTILE_VALID_BELOW`), con pruebas en `tests/test_workload.py`.

### A5 — Ciclo de vida: granularidad y permisos

El manual (§6, p.3) no dice si el flush de caché es por celda o por repetición. *Propuesta:* **por repetición**, con reinicio del contenedor del motor antes de cada una. Razón adicional: reinicia también los contadores del cgroup, lo que hace que el delta de `cpu.stat` sea limpio.

**La limpieza de caché en Windows + WSL2 + Docker Desktop no es la del manual, y no se puede asumir.** Hay tres capas de caché y solo dos son alcanzables:

| Capa | Qué guarda | ¿Se puede limpiar? |
|------|------------|--------------------|
| 1. Buffer interno del motor | Caché de WiredTiger / `shared_buffers` de Postgres | **Sí**, reiniciando el contenedor del motor. Control total |
| 2. Caché de páginas del kernel de la VM de WSL2 | Bloques de archivo leídos por los contenedores | **Probablemente sí**, con `drop_caches` — pero hay que comprobarlo, no suponerlo (ver abajo) |
| 3. Caché de archivos de Windows sobre el `.vhdx` | Bloques del disco virtual donde vive todo | **No.** `drop_caches` no la toca. Solo `wsl --shutdown` o reiniciar Windows la liberan |

*Por qué la capa 2 es una hipótesis y no un hecho.* Todas las distribuciones de WSL2 —`Ubuntu` y `docker-desktop`— comparten **un solo kernel de Linux** dentro de la misma VM, y `vm.drop_caches` es un parámetro global del kernel, no aislado por contenedor ni por distribución. De ahí se sigue que `sudo sh -c 'sync; echo 3 > /proc/sys/vm/drop_caches'` ejecutado desde Ubuntu debería limpiar también el caché que usan los contenedores. **Debería.** Es un razonamiento, no una medición, y el proyecto no admite evidencias razonadas.

*Procedimiento de verificación* — **ejecutado y confirmado el 2026-10-31**:

1. Llenar el caché leyendo un archivo grande desde un contenedor.
2. Anotar `buff/cache` de `free -h` en Ubuntu **y** en `docker-desktop` (`wsl -d docker-desktop -- free -h`).
3. Ejecutar el flush desde Ubuntu con `sudo`.
4. Volver a anotar en ambas vistas.
5. Si el caché baja en las dos, la vía está confirmada. Si no, se usa la ruta alternativa.

*Resultado medido.* Tras llenar el caché desde un contenedor (512 MB escritos y releídos), `free -m` en Ubuntu reportó:

| Momento | `buff/cache` |
|---------|--------------|
| Antes del flush | 787 MB |
| Después del flush | 387 MB |

Bajó 400 MB. **Lo que esto demuestra, con precisión:** el flush ejecutado desde la distribución `Ubuntu` **tiene efecto sobre el caché de páginas que usan los contenedores** de `docker-desktop`, porque comparten el kernel de la VM. La vía funciona y es la correcta.

**Lo que esto NO demuestra:** que el caché quede frío. Quedaron 387 MB sin liberar, y la capa 3 (caché de Windows sobre el `.vhdx`) sigue intacta por completo. Lo alcanzable en este entorno es una **limpieza efectiva y repetible** antes de cada repetición, no un arranque en frío. La diferencia importa para la comparación: si el estado de partida es el mismo en todas las celdas, la comparación entre motores sigue siendo válida aunque el punto de partida no sea cero. Así se redacta en la sección 2 del reporte, sin exagerar el alcance.

*Ruta de respaldo, no requerida.* Si en algún momento el flush dejara de hacer efecto, un contenedor privilegiado escribe sobre el mismo kernel sin intermediarios:

```bash
docker run --rm --privileged alpine sh -c 'sync; echo 3 > /proc/sys/vm/drop_caches'
```

*Problema operativo detectado: `sudo` pide contraseña.* En la verificación apareció `[sudo: authenticate] Password:`. En una corrida desatendida de horas, el script se quedaría colgado esperando que alguien escriba la contraseña, y la celda se perdería. Hay que resolverlo antes de F8, que es la corrida larga desatendida; opciones, de menos a más invasiva:

1. Ejecutar `sudo -v` al inicio y refrescar el permiso con un proceso que lo renueve cada pocos minutos mientras dura la corrida — no toca la configuración del sistema, pero depende de que ese proceso siga vivo.
2. Lanzar `run_benchmarks.sh` completo bajo `sudo` — simple, pero todo el experimento, Python incluido, correría como root. Mala idea.
3. Regla en `/etc/sudoers.d/` acotada a **un solo script de ruta absoluta, propiedad de root y no escribible por el usuario**, que no haga nada más que `sync` y el flush.

**No se configura nada todavía.** La opción 3 es la dirección razonable, pero una regla sin contraseña es un permiso permanente y merece diseñarse y revisarse antes de aplicarse, no escribirse de corrido. El diseño que hay que revisar contigo antes de tocar nada:

- El script debe estar fuera del repositorio (p. ej. `/usr/local/sbin/`), pertenecer a `root:root` y tener permisos `0755`. Si viviera en el repo y fuera editable por tu usuario, la regla equivaldría a darte root completo sin contraseña, que es exactamente lo que no queremos.
- La regla nombra ese único ejecutable por ruta absoluta, sin comodines ni argumentos libres.
- El script no acepta parámetros.
- Queda documentado en el repo cómo instalarlo y **cómo revertirlo**.

Mientras tanto, para la celda piloto y las pruebas de F1 basta la opción 1, que no deja nada permanente en tu sistema. La decisión de aplicar o no la opción 3 se toma antes de F8, que es la corrida larga desatendida. **PENDIENTE: V7.**

*Diseño de `flush_caches.sh`.* No basta con ejecutar el comando: hay que **medir que hizo efecto**. El script anota `buff/cache` antes y después, registra el delta en el log de la corrida y aborta si el caché no bajó habiendo caché que bajar. Así el revisor ve evidencia de que el flush ocurrió, no la afirmación de que se intentó.

*Lo que queda fuera del alcance, declarado.* La capa 3 permanece caliente entre repeticiones. Un "caché frío" perfecto no es alcanzable en este entorno; lo alcanzable es un estado **consistente y repetible** entre repeticiones, que es lo que la comparación necesita. Va escrito en la sección 2 del reporte.

### A6 — Detección de `disk_spill` y `oom_killed`

El manual los pide como booleanos pero no dice cómo obtenerlos. *Propuesta:*

- **Postgres:** delta de `pg_stat_database.temp_bytes` entre inicio y fin de la ventana. `>0` → spill. Confirmación cualitativa con `Sort Method: external merge` en el `EXPLAIN ANALYZE` capturado aparte.
- **MongoDB:** delta de contadores de spill en `serverStatus()` más `usedDisk` en el `explain`. Con `allowDiskUse:false` no hay spill posible por definición: lo que podría aparecer es un error por límite de memoria del stage `$sort`, que se registra como `status=error`. Ver A12: con `$limit 1000` ese límite probablemente nunca se alcance.
- **OOM:** `memory.events` del cgroup (`oom_kill > 0`) y `State.OOMKilled` de `docker inspect`. Ambos se guardan crudos en `results/logs/`.

*Advertencia honesta para el reporte:* un booleano colapsa una realidad graduada (volcar 2 MB y volcar 2 GB dan `true`). El volumen real de spill se reporta aparte, en la sección 6.

### A7 — `mem_swappiness: 0` no desactiva el swap, y bajo cgroups v2 no existe ✅ RESUELTA (V8, 2026-11-01)

**Parte 1, ya resuelta.** Con `mem_swappiness: 0` pero sin `memory-swap`, Docker asigna por defecto el doble de swap que de memoria, y el contenedor puede intercambiar en lugar de morir por OOM — con lo cual PROFILE_C nunca produciría el OOM que el experimento busca. *Decisión:* fijar `memswap_limit` igual a `mem_limit` en cada perfil (swap efectivo = 0) y verificarlo leyendo `memory.swap.max` del cgroup. Verificado en F0, y de nuevo en F1 en los 3 perfiles × 2 motores: da 0. Esto **no contradice** el manual; lo completa.

**Parte 2 — qué pasa con `mem_swappiness` bajo cgroups v2. Comprobado en la máquina (V8).**

*Cómo se detectó (2026-10-31).* Al resolver el `docker-compose.yml` con `docker compose config`, la clave `mem_swappiness` desaparece del resultado, mientras que `cpus`, `mem_limit` y `memswap_limit` sí aparecen.

*Qué se comprobó (2026-11-01).* Docker 29.4.1 · Compose 5.1.3 · cgroup v2 · kernel 6.6.87.2-microsoft-standard-WSL2. Evidencia: `results/env/f1/V8_mem_swappiness_20261101T171426Z.txt`, más los `up_*.txt` y `PROFILE_*.{txt,json}` de F1.

| Comprobación | Resultado |
|---|---|
| Avisos en los `docker compose up` capturados (3 perfiles × 2 motores, stdout+stderr) | Ninguno: `grep -iE 'warn\|discard'` → sin coincidencias |
| `docker inspect bench_mongo --format '{{.HostConfig.MemorySwappiness}}'` | `<nil>`. Vacío también en las 12 verificaciones de límites: `<no value>` en las 6 hechas con el script anterior y `null` en las 6 hechas con `capture_env.py` |
| `docker exec bench_mongo ls /sys/fs/cgroup/ \| grep -i swappi` | Sin coincidencias (exit 1); `memory.swappiness` ausente en ambos motores y en los tres perfiles |
| `docker compose config` con PROFILE_A | Resuelve `cpus`, `mem_limit` y `memswap_limit`, pero **no** `mem_swappiness` |
| `docker create --memory-swappiness=0 …` directo, sin Compose | Docker responde `WARNING: Your kernel does not support memory swappiness capabilities or the cgroup is not mounted. Memory swappiness discarded.` · `MemorySwappiness=<nil>` · sin `memory.swappiness` dentro · `memory.swap.max=0` |

*Qué se concluye, en tres capas.*

1. **Kernel.** El cgroup v2 del contenedor no tiene `memory.swappiness`: era un control de cgroups v1. Sí tiene `memory.swap.max`, `memory.swap.current`, `memory.swap.high`, `memory.swap.peak` y `memory.swap.events`.
2. **Docker Engine.** Cuando recibe `--memory-swappiness=0`, lo descarta y lo dice con el aviso citado arriba.
3. **Compose.** No le pasa `mem_swappiness` a Docker; por eso `docker compose up` no avisa de nada: Docker nunca recibe el valor. *Por qué* lo omite Compose no se investigó; solo se observó que no lo manda.

El manual pide a la vez cgroups v2 (§3) y `mem_swappiness=0` (tabla de perfiles, §3), y bajo v2 lo segundo no se puede aplicar por contenedor. Es una tensión del manual, no un error de implementación. **No es un fallo:** lo que el manual busca (que el contenedor no use swap) lo garantiza `memory.swap.max = 0`, verificado en los 3 perfiles × 2 motores.

*Qué se hace.*

1. La clave `mem_swappiness` **se conserva** en el `docker-compose.yml` porque el manual la exige literalmente y el entregable debe mostrarla.
2. La garantía funcional de "sin swap" la da `memory.swap.max = 0`, que se verifica en cada captura.
3. `capture_env.py` registra `HostConfig.MemorySwappiness` y si existe `/sys/fs/cgroup/memory.swappiness`; `verify_limits.sh` lo muestra. **No se marca como fallo** si no existe: se registra y se declara.

*Para el reporte, sección 1.* "El perfil declara `mem_swappiness=0` como exige el manual. Bajo cgroups v2 ese control no existe por cgroup: Docker 29.4.1 lo descarta con el aviso *Memory swappiness discarded*. La restricción equivalente y verificable es `memory.swap.max=0`, que se comprueba en cada corrida." Honesto, verificable y no finge haber cumplido algo que el kernel ya no ofrece.

### A8 — Parámetros libres del dataset que cambian los resultados

El manual no especifica, y cada elección mueve las métricas:

| Parámetro | Propuesta | Por qué importa |
|-----------|-----------|-----------------|
| Rango de `timestamp` | Uniforme 2025-01-01 … 2026-12-31 | Define qué fracción pasa el filtro `>= 2026-01-01` de Q2 (≈50 %) |
| Proporción `payment.status='completed'` | 70 % | Define el tamaño del sort de Q2 (≈175 k filas) |
| Distribución de `items` | 1–6 ítems, media 3 | R-09 pide "promedio 3" |
| Fracción con `price > 50` | ≈45 % | Define el tamaño del group de Q1 |
| Cardinalidad `country` × `category` | 12 × 20 = 240 grupos | Define si el `$group` cabe en memoria; con pocos grupos, Q1 nunca estresa el buffer |
| Semilla PRNG | `42`, fija y versionada | Sin esto no hay reproducibilidad (R-33) |

Todas van en `generator/distributions.py` como constantes nombradas y se publican en el reporte, sección 1.

### A9 — "latest-stable" no es reproducible

Diapo 5/13 exige anotar la versión del motor; §2 dice "latest-stable". Son compatibles solo si se **fija** la versión al inicio y se registra el digest de la imagen. Ver §6.

### A10 — Qué contenedor se mide

Los KPIs `container_cpu_cfs_throttled_seconds_total` y `container_memory_rss_bytes` existen por contenedor. *Propuesta:* el CSV reporta **solo el contenedor del motor bajo prueba**. El consumo del runner, de Prometheus y de cAdvisor se documenta en la sección 1 del reporte pero no entra al CSV.

### A11 — M3 (huella por 1 000 documentos) no tiene columna

`M3` exige CPU/memoria por cada 1 000 documentos procesados, pero el CSV no tiene denominador. *Propuesta:* calcularlo en el reporte dividiendo entre los documentos realmente examinados, tomados de `executionStats.totalDocsExamined` y de las `rows` del `EXPLAIN ANALYZE` (sección 5 del reporte). No se agrega ninguna columna.

**Memoria en M3 (Alix, 2026-11-02, F6-A3):** la memoria por 1 000 documentos se calcula con `working_set` (`memory.current − inactive_file`, igual a `container_memory_working_set_bytes`), que incluye los `shared_buffers` de Postgres, **o** se declara explícitamente el sesgo si se usa `max_rss_mb`: con `anon`, Postgres sale artificialmente eficiente frente a Mongo (ver la nota de `max_rss_mb` en §4).

### D-WSL1 — Memoria y swap de la VM de WSL2 ✅ DECIDIDA (2026-10-31)

No es una ambigüedad del manual: es una decisión del entorno que afecta a si PROFILE_A es un baseline defendible.

**Situación.** Sin `.wslconfig`, WSL2 toma por defecto ~50 % de la RAM física: 7.159 GiB de los 14.8 GiB del equipo. PROFILE_A entrega 4 GiB al motor y deja ~3.1 GiB para el runner, la telemetría y el caché de páginas. La otra mitad de la RAM queda en Windows, sin usarse para el experimento.

**Opciones.**

| Opción | Efecto | Costo |
|--------|--------|-------|
| (a) Dejarlo como está | Cero configuración; el experimento corre | PROFILE_A compite con todo lo demás por 3.1 GiB; poco caché de páginas; el baseline queda estrecho |
| (b) Crear `.wslconfig` con `memory=10GB` y `swap=0` | PROFILE_A tiene holgura real; sin swap en la VM se elimina L7 | Deja ~4.8 GiB a Windows: hay que cerrar navegador y otras apps durante las corridas |
| (c) `memory=12GB` | Máxima holgura | Riesgo de que Windows empiece a paginar, lo que sería peor que el problema original |

**DECIDIDO (2026-10-31): opción (a).** Se conserva la VM en 7.159 GiB con su swap global, y no se crea `.wslconfig`.

Consecuencias que se declaran, no se disimulan:

- PROFILE_A opera con ~2.2 GiB de holgura para runner, telemetría y caché de páginas. Es un baseline **con holgura limitada**, y así se nombra en el reporte.
- El swap de la VM no afecta al contenedor medido (ver L7 corregida), pero sí puede afectar al runner bajo presión. Se vigila y se anota por corrida.
- Si en la celda piloto (F7) el coeficiente de variación del throughput supera el 15 %, esta decisión se revisa antes de gastar horas en la matriz.

**Si alguna vez se cambia, hay que rehacer las mediciones de F0** y volver a anotar la tabla del entorno: cambiar la VM a mitad del experimento invalidaría la comparación entre celdas medidas antes y después.

### A12 — La premisa de "estrés de buffer" puede no materializarse ⚠️ ALTA

Q2 es `$sort` seguido de `$limit 1000`, y `ORDER BY ... LIMIT 1000` del lado SQL. Los dos motores optimizan ese patrón:

- MongoDB fusiona `$sort` + `$limit` en un **top-K sort**, que mantiene en memoria del orden de K documentos, no el conjunto filtrado completo.
- PostgreSQL usa **top-N heapsort** cuando hay `LIMIT`, acotando la memoria a unas N tuplas en lugar de ordenar las ~175 k filas que pasan el filtro.

Consecuencia directa: con K = 1000 es perfectamente posible que `allowDiskUse:false` **nunca falle** y que `work_mem='4MB'` **nunca vuelque a disco**, y que las dos variantes de Q2 produzcan números casi idénticos. La propia diapo 7/13 rotula su ejemplo como *"(ficticio, formato)"*: ilustra el formato de lectura esperado, no predice el resultado.

Dos implicaciones que cambian el diseño del experimento:

1. **No se puede dar por hecho que habrá spill u OOM.** `disk_spill=false` en todas las celdas es un resultado legítimo y publicable. De hecho responde M2 ("qué motor gestiona mejor los buffers antes de volcar") de forma más interesante que el escenario esperado: la respuesta sería que, bajo este patrón de consulta, ninguno de los dos necesita volcar.
2. **La capacidad de detección se demuestra aparte del benchmark.** Que el instrumento sepa reconocer spill y OOM se prueba con **queries sonda** diseñadas para forzarlos (por ejemplo un sort sin `LIMIT`). Esas sondas viven en `scripts/probes/`, **nunca** en `queries/`, no producen filas del CSV y se reportan como verificación de instrumento, no como resultado del experimento.

Si tras la matriz no aparece ningún spill, la presión de memoria realista viene de otro lado y ahí hay que mirar: concurrencia 50 en Postgres implica hasta 50 asignaciones simultáneas de `work_mem`, y en MongoDB el caché de WiredTiger se dimensiona según la memoria del contenedor. Eso sí puede producir OOM en PROFILE_C, por agregación de concurrencia y no por el ordenamiento en sí.

**Mezclar las dos cosas sería fabricar evidencia.** Las sondas van etiquetadas como tales en el reporte.

**Comprobado en F3 (2026-11-01): A12 se confirma, y el estrés de memoria está en Q1, no en Q2.** Medido con `EXPLAIN (ANALYZE, BUFFERS)` y `explain("executionStats")` sobre los 500 000 documentos, bajo PROFILE_A, en la verificación de equivalencia de G3. **No es una corrida del benchmark**: concurrencia 1 y sin ventana de medición. Evidencia: `results/explains/g3/` y `results/f3/g3/plan_summary.json`.

| | MongoDB | PostgreSQL |
|---|---|---|
| **Q1** | Sin disco: `$group` en memoria (`usedDisk: false`) | **Vuelca 1.4 GiB** (181 752 bloques temporales): `Sort` external merge en los 3 procesos paralelos (196 + 231 + 220 MiB de espacio de ordenamiento) y también el `Incremental Sort` posterior. 8.6 s |
| **Q2** `allowDiskUse` false / true · `work_mem` 4MB / 64MB | Sin disco: `SORT` top-K (`limitAmount: 1000`, 1.4 MB, 0 spills), igual en las dos variantes | Sin disco: `top-N heapsort` de ~273 kB en memoria por proceso, 0 bloques temporales, igual en las dos variantes |

Qué confirma y qué cambia:

1. **Confirma A12 para Q2.** Los dos motores fusionan `ORDER BY`/`$sort` con `LIMIT 1000` en un ordenamiento top-K, y ninguna variante de memoria del manual llega a volcar. A 10 000 (G2) se vio lo mismo. Es probable que `disk_spill=false` en las celdas de Q2 sea un resultado legítimo, como anticipó este apartado.
2. **Cambia dónde está el estrés de memoria: en Q1 de Postgres**, la query que el manual presenta como "saturación de CPU" (§5.1). La causa es una mala estimación del planner: espera 33 filas por documento tras `jsonb_array_elements`, cuando hay 1.34 en promedio. Con eso elige agregar ordenando, y ordena **los documentos JSONB completos** por país *antes* de desanidar. Eso no cabe en el `work_mem` por defecto (4MB). El volcado creció con la escala: 13 MiB a 10 000 y 1.4 GiB a 500 000. No depende del número de grupos, que son 240. Mongo no presenta nada parecido.
3. **Q1 corre con el `work_mem` por defecto (4MB):** el manual solo da variantes de memoria para Q2. Decisión de Alix (2026-11-01): no ajustarlo y reportar el volcado como hallazgo.
4. **Consecuencias para la matriz, que hay que medir y no suponer:** con concurrencia 50, Postgres ejecutaría hasta 50 Q1 simultáneas, cada una con su propio ordenamiento externo. El uso de disco temporal y de E/S puede ser muy alto. Además, cada Q1 lanza 2 workers paralelos, que bajo PROFILE_C compiten por 1 CPU. La pregunta M2 ("qué motor gestiona mejor los buffers antes de volcar") se responde con Q1, no con Q2.
5. **Pendiente:** todo lo anterior es bajo PROFILE_A. Bajo PROFILE_B y PROFILE_C, con menos memoria, el resultado puede cambiar, incluido un posible OOM. Se observa en la matriz.

---

## 6. Herramientas y versiones

### Exigido por el manual

| Componente | Exigencia literal | Fuente |
|------------|-------------------|--------|
| MongoDB | "latest-stable", WiredTiger, sin sharding | §2, p.1 |
| PostgreSQL | "latest-stable", tabla con JSONB | §2, p.1 |
| Docker + cgroups v2 | Perfiles de recursos | §3, p.1 |
| cAdvisor | Métricas de contenedor | §7, p.3 |
| Node Exporter | Métricas de host | §7, p.3 |
| Prometheus | `scrape_interval: 1s` | §7, p.3 |
| Runner | k6 **o** Python multiproceso | §8.1, p.4 |

### Recomendación mía (no exigido — requiere tu visto bueno)

| Componente | Versión propuesta | Por qué |
|------------|-------------------|---------|
| MongoDB | `mongo:8.2` fijado por digest | La serie estable actual es la 8.2 (8.0 es el major release). "latest-stable" → 8.2; el digest se anota en `results/env/` |
| PostgreSQL | `postgres:18` fijado por digest | 18 es la versión más reciente (liberada el 25-sep-2025) |
| **Runner: Python, no k6** | Python 3.11+, `multiprocessing` | k6 no tiene drivers nativos de Mongo ni Postgres: requeriría compilar extensiones xk6 y aun así mediría a través de capas no oficiales. Python usa los drivers de producción de cada motor, que es lo que un despliegue real usaría. El manual lo permite explícitamente |
| Driver Mongo | `pymongo` 4.x | Oficial; expone `allowDiskUse` y `explain` |
| Driver Postgres | `psycopg` 3.x (binary) | Soporta `SET work_mem` por sesión y `EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)` |
| Percentiles | `numpy` con interpolación lineal | Hay que **declarar el método**: P99 por "nearest-rank" y por interpolación dan números distintos y un revisor puede preguntarlo |
| Pruebas | `pytest` | R-33 |
| Figuras | `matplotlib` | Tres figuras obligatorias (R-30) |
| Gestión de entorno | `uv` o `venv` + `requirements.txt` con versiones fijadas | Reproducibilidad |

Ninguna versión se da por buena hasta ejecutar `docker pull` y registrar el digest real.

**Registrado en F1 (2026-11-01).** Las dos etiquetas existen (`docker pull` con exit 0). Versión y digest reales en la tabla de entorno de abajo; la evidencia está en `results/env/f1/docker_pull_20261101T164211Z.txt` y en cada `PROFILE_*.json` (`image.repo_digests`, `engine_version`). El archivo `results/env/versions.json` que mencionaba la versión anterior de este documento **no se creó**: los digests viven en las capturas de `capture_env.py`.

*Fijadas por digest (2026-11-01).* Las etiquetas son móviles: un `docker pull` futuro de `mongo:8.2` podría traer, por ejemplo, la 8.2.13. Por eso `docker/images.env` referencia ahora las imágenes **por digest** (`mongo@sha256:e0ce8c35…`, `postgres@sha256:3a426452…`), con la etiqueta de origen como comentario en la misma línea. Se comprobó que el contenedor arranca con exactamente ese digest (`docker inspect .Config.Image`) y que PROFILE_A sigue verificando en ambos motores: `results/env/f1/PROFILE_A_BASELINE_*_20261101T1742*Z.{txt,json}`.

### Entorno de ejecución medido (F0, 2026-10-31 · F1, 2026-11-01)

Todo lo de esta tabla proviene de salida de comandos, no de supuestos. Las filas de F0 vienen de la salida que reportó el estudiante; las marcadas (F1) se ejecutaron en la máquina y su salida está en `results/env/f1/`. Es el contenido de la sección 1 del reporte.

| Capa | Valor medido |
|------|--------------|
| Sistema operativo anfitrión | Windows 11 |
| Procesador | AMD Ryzen 5 PRO 5675U — 6 núcleos físicos, 12 procesadores lógicos |
| RAM física del equipo | 14.8 GiB |
| Espacio libre en C: | 473.06 GiB |
| Capa de virtualización | WSL2 2.6.3.0, kernel 6.6.87.2-1 |
| Distribuciones WSL2 | `Ubuntu` (donde corren Python y los scripts) y `docker-desktop` (donde corren los contenedores) |
| `.wslconfig` | No existe → la VM usa los valores por defecto |
| Memoria disponible para contenedores | **7.159 GiB** (tope por defecto de WSL2: ~50 % de la RAM física) |
| CPUs disponibles para contenedores | 12 (lógicas) |
| Swap dentro de la VM | 2.0 GiB |
| Docker Engine | 29.4.1 · Compose v5.1.3 · OSType linux · Cgroup Version 2 |
| MongoDB (F1) | **8.2.12**, motor `wiredTiger` · imagen `mongo:8.2` · `sha256:e0ce8c35124d4a9f9785532d1f268f39e9728ffa1cb38f46fa482436424c4bd3` |
| PostgreSQL (F1) | **18.6** (Debian 18.6-1.pgdg13+2) · imagen `postgres:18` · `sha256:3a4264520e121176619f54ff867d12774bc81e95e7b84db58d63bccdb6144b81` |
| Límites por perfil (F1) | Leídos dentro del contenedor, iguales en ambos motores: A `400000 100000` / `4294967296` · B `200000 100000` / `2147483648` · C `100000 100000` / `1073741824` · `memory.swap.max=0` en los seis ✔ |
| `mem_swappiness` (F1, V8) | Descartado: Compose no lo pasa y Docker lo rechaza con *Memory swappiness discarded*. Sin swap garantizado por `memory.swap.max=0` (ver A7) |
| OOM observable (F1) | Contenedor con límites de PROFILE_C que pide 2 GiB → exit 137, `memory.events oom_kill 1`, `OOMKilled=true` ✔ |
| Prueba de límites | `--cpus=1 --memory=1024m --memory-swap=1024m` → `cpu.max=100000 100000`, `memory.max=1073741824`, `memory.swap.max=0` ✔ |
| Archivos de métricas del cgroup | `cpu.stat`, `memory.stat`, `memory.peak`, `memory.events`, `memory.swap.max` presentes ✔ |
| `sudo` en Ubuntu | disponible (`/usr/bin/sudo`), pero **pide contraseña** — ver A5 |
| Sistema de archivos de trabajo | `/home/alix_anahi` sobre `/dev/sdf` (ext4 nativo de WSL2) ✔ |
| Espacio dentro de la VM | 1007 GB nominales, 954 GB libres — **limitado en realidad por los 473 GB libres de C:**, porque el disco virtual crece contra él |
| Uso actual de Docker | Imágenes 29.13 GB · Build cache 19.01 GB · Volúmenes 2.24 GB · Contenedores 0.40 GB |
| Ruido en reposo | `loadavg` 0.38 / 0.12 / 0.04 · 999 MiB usados · 6.2 GiB disponibles · swap sin usar |
| Flush de caché | Verificado: `buff/cache` 787 MB → 387 MB ✔ |
| Throttling observable | Verificado: `--cpus=0.5` con carga de 10 s → `throttled_usec` 5 022 196 (≈5.02 s) ✔ |

**Veredicto: el entorno es viable.** Los límites de CPU y memoria se aplican de verdad, hay cgroups v2 y existen todos los archivos que alimentan el CSV. El experimento se puede ejecutar.

### Limitaciones del entorno virtualizado — para la sección 1 del reporte

Estas no son defectos a esconder; son el contexto que un revisor necesita para interpretar los números. Van declaradas en el reporte.

**L1 — Los contenedores no corren sobre el hardware, corren sobre una VM.** Hay dos niveles de planificación: Windows reparte los núcleos a la VM de WSL2, y dentro de la VM el kernel de Linux reparte según `cpu.max`. Los límites del manual se cumplen **dentro de la VM**, que es lo que el manual pide, pero "4.0 CPUs" no significa 4 núcleos físicos dedicados.

**L2 — 12 CPUs lógicas son 6 núcleos físicos con SMT.** Cuando PROFILE_A pide 4.0 CPUs, el planificador puede entregarle hilos hermanos del mismo núcleo físico, que rinden bastante menos que 4 núcleos independientes. Consecuencia: el baseline es algo peor de lo que sería en hierro dedicado, y la diferencia entre PROFILE_A y PROFILE_B se comprime. Se declara.

**L3 — 7.159 GiB de memoria para todo lo que vive dentro de la VM.** PROFILE_A entrega 4 GiB al motor. Con ~1 GiB ya en uso en reposo, quedan ~2.2 GiB para el runner de Python con hasta 50 procesos, Prometheus, cAdvisor, node_exporter y el caché de páginas. Es ejecutable pero estrecho, y el caché de páginas es justamente lo que más influye en un benchmark de base de datos.

**Decidido (D-WSL1, 2026-10-31): se conserva la configuración actual.** No se crea `.wslconfig`. Consecuencia que se declara en la sección 1 del reporte: **PROFILE_A es un baseline con holgura limitada**, no un entorno sin contención en sentido estricto. Si en la celda piloto (F7) la variabilidad entre repeticiones supera el 15 %, esta decisión se revisa.

**L4 — Existe una capa de caché que `drop_caches` no alcanza.** Ver A5 revisada.

**L5 — El runner comparte la VM con el motor.** Python corre en la distribución `Ubuntu` y los contenedores en `docker-desktop`, pero **ambas viven dentro de la misma VM de WSL2** y compiten por las mismas 12 CPUs lógicas y los mismos 7.159 GiB. No hay aislamiento real entre el generador de carga y lo medido; solo hay el `cpuset` que le asignemos.

**L6 — Ubicación de los archivos: volúmenes nombrados frente a bind mounts.** Son dos cosas distintas y conviene no confundirlas.

| Tipo | Dónde vive realmente | Velocidad |
|------|----------------------|-----------|
| **Volumen nombrado** (`mongo_data:/data/db`) | Dentro del disco virtual de la distribución `docker-desktop`, en ext4 | Nativa. **Es lo que usamos para los datos de los motores** |
| **Bind mount desde el sistema de archivos de WSL2** (`/home/alix_anahi/...`) | En el ext4 de la distribución `Ubuntu` | Aceptable. Solo para archivos de configuración que se leen al arrancar |
| **Bind mount desde una ruta de Windows** (`/mnt/c/...`) | En NTFS, a través de una capa de traducción | Muy lento. **Prohibido para cualquier dato del experimento** |

Punto importante: un volumen nombrado **no** se ve afectado por dónde esté el archivo `docker-compose.yml`. Aunque el repositorio estuviera en `/mnt/c/`, los datos del motor seguirían viviendo en ext4. El riesgo real son los bind mounts a rutas de Windows y la lectura del dataset por el generador.

Verificado en F0: el directorio de trabajo es `/home/alix_anahi` sobre `/dev/sdf` (ext4 nativo) ✔. El diseño de F1 usa volúmenes nombrados para los datos y **ningún** bind mount a `/mnt/c/`.

**L7 — Swap: alcance correcto de la restricción.** *Corrección de una afirmación errónea de la versión anterior de este documento.* `memory.swap.max=0` es una restricción del cgroup y se cumple dentro de él: **el contenedor medido no puede intercambiar a swap, punto.** Los 2 GiB de swap de la VM no anulan esa restricción ni abren una puerta trasera para las páginas del motor. Verificado en F0.

Lo que sí sigue siendo cierto, y es una preocupación distinta y más estrecha: los procesos que viven **fuera** del cgroup medido —el runner de Python, Prometheus, cAdvisor— sí pueden intercambiar si la VM entra en presión de memoria. Eso no falsea las métricas del motor, pero sí puede meter ruido en los tiempos que mide el cliente. Mitigación: vigilar el uso de swap de la VM durante las corridas y anotarlo por corrida.

---

## 7. Archivos necesarios para que otro estudiante reproduzca el experimento

Agrupados por para qué sirven:

**Para levantar el entorno**
1. `README.md` — prerrequisitos, pasos numerados, tiempo esperado, advertencia de `sudo` para el flush
2. `docker/docker-compose.yml` + `docker/profiles/*.env`
3. `docker/mongo/init.js`, `docker/postgres/init.sql`, `docker/postgres/postgresql.conf`
4. `monitoring/prometheus.yml` + `docker-compose.monitoring.yml`
5. `requirements.txt` con versiones fijadas

**Para regenerar exactamente el mismo dataset**
6. `generator/synthetic_data_generator.py`, `generator/schema.py`, `generator/distributions.py` (semilla fija)
7. `results/dataset_stats.json` — conteos, media de ítems, cardinalidades, hash de verificación

**Para ejecutar lo mismo**
8. `queries/` completo (4 archivos, sin modificar)
9. `benchmark_runner/` completo
10. `scripts/run_benchmarks.sh`, `flush_caches.sh`, `load_dataset.sh`, `capture_env.py`

**Para auditar lo que ya se midió**
11. `results/measurements.csv` + `scripts/validate_csv.py`
12. `results/env/` — un JSON por corrida: digests, versiones, límites reales del cgroup, `nproc`, kernel, carga del host
13. `results/explains/` — planes crudos por motor/query/perfil
14. `results/logs/` — evidencia de spill/OOM y salida del flush
15. `results/raw/` — latencias crudas por corrida (permite recalcular percentiles con otro método)

**Para entender y discutir**
16. `SPEC.md`, `PLAN.md`, `CHECKLIST.md`
17. `report/reporte_metricas.md` + `report/figures/`
18. `tests/` completo

Criterio de aceptación de la reproducibilidad (diapo 10/13): un tercero clona, sigue el README, y obtiene un CSV con el mismo encabezado, el mismo número de filas y las mismas celdas marcadas `spill`/`oom`. Los valores absolutos **no** serán iguales —dependen del hardware—, y eso debe decirlo el README explícitamente.
