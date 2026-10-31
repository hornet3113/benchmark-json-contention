# F3 — Carga e indexación escalonada (CERRADA el 2026-11-01)

**Estado: cerrada.** G1, G2 y G3 fueron revisadas y aprobadas por Alix. F4 (equivalencia) se ejecutó dentro de G2 y se re-verificó en G3, y también está cerrada. PLAN.md, SPEC.md (A12), CLAUDE.md y CHECKLIST.md ya están actualizados. G2 y G3
se planean en detalle después de que Alix revise la evidencia de G1.

Qué cubre F3: cargar el dataset de F2 en los dos motores en tres compuertas
(G1 = 1 000 · G2 = 10 000 · G3 = 500 000), crear los índices del manual y
comprobar que los datos sobreviven a la carga sin cambiar. Una compuerta
cierra antes de pasar a la siguiente (PLAN F3).

---

## Criterios de G1 (PLAN F3, más tres añadidos)

- [x] Carga sin errores en ambos motores; conteos iguales a 1000 — `results/f3/g1/load_{mongo,postgres}.json`
- [x] Validación de esquema (R-10) sobre el 100 % de los registros cargados — 1 000 + 1 000, 0 inválidos (`compare.json`)
- [x] `final_total` llega como número **leído desde el motor** — Mongo `double` 1000/1000 · Postgres `number` 1000/1000 (`export_*.json`)
- [x] `timestamp` es string ISO-8601 en ambos — `string` en los dos motores; formato estricto validado en los 2 000 exportados
- [x] Documentos equivalentes entre motores por `order_id` (ver F3-e: los 1 000, en tres direcciones)
- [x] Índices creados; A3.2 resuelta en la práctica con la salida del comando como evidencia — `a32_index_variants.txt`
- [x] *Añadido:* `id::text = data->>'order_id'` en las 1 000 filas (SPEC §2, compromiso de F2) — 0 distintos (`export_postgres.json`)
- [x] *Añadido:* comparación en tres direcciones: 1 000 de 1 000 iguales — `compare.json`
- [x] *Añadido:* R-15, ningún índice sobre `final_total` — en ambos motores

De paso se archiva evidencia de R-01 (colección `orders` con WiredTiger, sin
sharding) y R-03 (`\d+ orders`). Todo queda en `results/f3/g1/`.


## Criterios de G2 (PLAN F3 y PLAN F4, más los de G1 repetidos a 10 000)

- [x] Conteos iguales a 10 000 — `results/f3/g2/load_{mongo,postgres}.json`
- [x] **Equivalencia de Q1 y Q2 entre motores** (F4), contra una referencia exacta calculada en Python (G2-b) — `results/f3/g2/equivalence.json`
  - [x] Q1: mismos 240 grupos, `count` exacto, `total_revenue` y `avg_revenue` < 1e-6
  - [x] Q2: mismos 1 000 `order_id` como conjunto, vector de `final_total` < 1e-6, mismo `customer_id`
  - [x] Las dos variantes de Q2 de cada motor devuelven lo mismo (G2-d)
  - [x] Empates documentados: no hay empate en la frontera; hay 7 valores repetidos dentro del Top-1000 → se compara como conjunto
- [x] Planes capturados (R-31): queda registrado si cada motor usa su índice de `timestamp` y si los planes se parecen — `results/explains/g2/`
- [x] Tiempo de carga a 10 000 → extrapolación a 500 000 — `results/f3/g2/load_extrapolation.json` (estimación)
- [x] Queries de `queries/` iguales a las extraídas del PDF (`extract_queries.py --check`, paso 0)
- [x] Repetido de G1: tres direcciones 10 000/10 000, esquema al 100 %, tipos, `id = order_id`, R-15


## Criterios de G3 (PLAN F3)

- [x] `countDocuments()` = `count(*)` = 500 000 — `results/f3/g3/load_{mongo,postgres}.json`, `export_*.json`
- [x] Equivalencia Q1/Q2 **re-verificada a escala real** contra la referencia exacta — `results/f3/g3/equivalence.json`
- [x] Índices listados y capturados; **ninguno** sobre `final_total` (R-15) — `export_*.json`
- [x] Planes re-capturados — `results/explains/g3/`, resumen en `results/f3/g3/plan_summary.json`
- [x] Tiempo de carga y tamaño en disco por motor, con índices por separado — `load_*.json`, `export_*.json` (`tamano_en_disco`), `load_vs_estimate.json`
- [x] Espacio libre verificado contra la estimación de SPEC §6 — `results/f3/g3/espacio_libre.txt`
- [x] Repetido de G1/G2 a 500 000: tres direcciones 500 000/500 000, esquema al 100 %, tipos, `id = order_id`

---

## Decisiones aprobadas (2026-11-01)

| # | Pregunta | Decisión |
|---|---|---|
| F3-a | ¿Con qué perfil se carga? | PROFILE_A. Los datos viven en el volumen nombrado y sirven a los tres perfiles: se carga una vez y luego cada perfil solo reinicia el contenedor |
| F3-b | ¿Índice único en `order_id` de Mongo? | **No**, literal "índice simple" (R-02). La unicidad la garantiza el generador y G1 la comprueba |
| F3-c | ¿Índices antes o después de cargar? | **Después**, en ambos motores. Los tiempos de carga y de indexado se miden por separado |
| F3-d | ¿`data JSONB NOT NULL`? | No: literal `orders (id UUID PRIMARY KEY, data JSONB)` (R-03) |
| F3-e | ¿Comparar un documento o todos? | **Todos, en tres direcciones**: archivo fuente = exportado de Mongo = exportado de Postgres, documento por documento |

---

## Problemas resueltos en el diseño

1. **JSONB reordena las claves** (primero por longitud y luego alfabéticamente).
   `validate_record` exigía el orden y habría rechazado el 100 % de lo leído de
   Postgres. Se le agrega `strict_order=False` solo para documentos leídos de un
   motor; el generador sigue validándose en modo estricto.
2. **`docker-entrypoint-initdb.d` no se ejecutaría.** Las imágenes solo corren
   esos scripts con el volumen vacío, y los volúmenes se inicializaron en F1:
   no habría error, simplemente no correrían. `load_dataset.sh` ejecuta el DDL
   de forma explícita.
3. **`COPY` en formato texto interpreta `\` y tabuladores.** F2 garantizó 0
   líneas con esos caracteres, así que se usa formato texto hacia una tabla
   intermedia y luego `INSERT … SELECT (doc->>'order_id')::uuid, doc`: el `id`
   sale del propio documento.
4. **Solo un motor a la vez** (CLAUDE.md). Cada motor se levanta, se carga, se
   exporta a archivo y se baja; la comparación se hace en el host, sobre los
   archivos exportados.

La carga y la exportación usan las herramientas de dentro de los contenedores
(`mongoimport` 100.17.0, `mongoexport`, `mongosh`, `psql` 18.6, verificadas
en las imágenes fijadas), pasando los datos por la entrada estándar: sin
montar carpetas (L6) y sin drivers en el host.

---

## Archivos

| Archivo | Qué hace |
|---|---|
| `docker/postgres/init.sql` | Borra y crea `orders (id UUID PRIMARY KEY, data JSONB)` (R-03) |
| `docker/postgres/indexes.sql` | Índice B-Tree sobre `(data->>'timestamp')` como texto (A3.2) |
| `docker/mongo/init.js` | Borra y crea la colección `orders` |
| `docker/mongo/indexes.js` | Índices simples `{timestamp: 1}` y `{order_id: 1}` (R-02, F3-b) |
| `scripts/load_dataset.sh <tamaño> <motor>` | Verifica el SHA-256 del archivo contra sus estadísticas de F2, recrea, carga por stdin, indexa, hace `VACUUM ANALYZE` y mide cada paso |
| `scripts/checks/a32_index_variants.sql` | Volatilidad de los casts y **prueba** de crear los índices `::timestamp` y `::timestamptz`; se borran después |
| `scripts/verify_gate.py` | `export`: exporta un motor, revisa tipos, `id`, índices y entorno. `compare`: valida el 100 % y compara en tres direcciones |
| `scripts/run_g1.sh` | Encadena todo y archiva la salida |

---

## Registro de ejecución

### 2026-11-01 — G1: 1 000 registros

Corrida: `scripts/run_g1.sh` → `results/f3/g1/run_20261101T183329Z.txt`.
Todos los pasos dieron exit 0. Perfil de carga: PROFILE_A (F3-a); el entorno
de cada motor está dentro de `export_*.json`: MongoDB 8.2.12 y PostgreSQL
18.6, ambos con `cpu.max=400000 100000` y `memory.max=4294967296`.

Cambios de código para G1:

- `generator/schema.py`: `validate_record(…, strict_order=False)` para lo
  leído de un motor, con 4 pruebas nuevas. **El dataset no cambia:**
  regenerar 1 000 con el código actual da el mismo SHA-256 que F2
  (`fd0b00da…b64c`). El `sha256_fuentes.schema.py` de
  `results/dataset_stats.json` había quedado con la versión anterior.
  **Resuelto el 2026-11-01:** se regeneraron los 500 000 con el código actual
  (`results/f2/F2_regeneracion_20261101T184059Z.txt`). Los datos dieron el
  mismo SHA-256 (`0cd7fadb…0414`) y cambiaron exactamente 3 campos:
  `generado_utc`, `segundos` (172.35 → 201.78) y
  `sha256_fuentes.schema.py` (`a0bdda43…` → `475440e8…`, que es el archivo en
  disco). El original se conserva, en solo lectura, en
  `results/f2/dataset_stats_500000_seed42_20261101T181011Z_original.json`.
  Los `dataset_stats_{1000,10000}_seed42.json` de `results/f2/` siguen con el
  hash anterior: no se regeneraron porque no se pidió.
- Nuevos: el DDL de `docker/{mongo,postgres}/`, `scripts/load_dataset.sh`,
  `scripts/checks/a32_index_variants.sql`, `scripts/verify_gate.py` (con 13
  pruebas en `tests/test_verify_gate.py`) y `scripts/run_g1.sh`. Suite:
  **75 de 75**.

**A3.2 — qué índice es creable** (`a32_index_variants.txt`):

| Variante | Resultado |
|---|---|
| `((data->>'timestamp'))`, texto sin cast | **creado** |
| `(((data->>'timestamp')::timestamp))` | `ERROR:  functions in index expression must be marked IMMUTABLE` |
| `(((data->>'timestamp')::timestamptz))`, el que usa Q2 | `ERROR:  functions in index expression must be marked IMMUTABLE` |

Por qué: `pg_cast` **no tiene ninguna fila** de `text` a
`timestamp`/`timestamptz` (0 filas), así que la conversión se hace por I/O,
con las funciones de entrada del tipo. `timestamp_in` y `timestamptz_in` son
`STABLE` (`s`), no `IMMUTABLE`. Esto **refuta** la hipótesis que SPEC A3.2
dejó sin verificar ("bastaba usar `::timestamp`") y muestra que la consulta
de verificación de SPEC A3.2, que busca la función en `pg_cast.castfunc`, no
encuentra esta conversión. La opción (1) de A3.2, ya decidida, era la única
viable.

La primera corrida dejó la salida de `psql` intercalada: los `ERROR` (stderr)
salían lejos de su sentencia por el búfer de stdout. Se conserva tal cual en
`a32_index_variants_20261101T183329Z_salida_intercalada.txt`; las conclusiones
eran las mismas (la sección 4 listaba solo el índice de texto). Se repitió con
`stdbuf -oL -eL` → `a32_index_variants.txt`, ya ordenado. `run_g1.sh` quedó
corregido.

**Comparación en tres direcciones** (`compare.json`): **1 000 de 1 000
iguales** (fuente = Mongo = Postgres). Faltantes: 0/0/0. Distintos: Mongo 0,
Postgres 0. Esquema al 100 %: 0 inválidos en fuente (estricto), Mongo y
Postgres (sin orden). Orden de claves igual al de la fuente: Mongo
1000/1000 (BSON lo conserva), Postgres 0/1000 (JSONB lo reordena, como se
anticipó).

**Tipos leídos desde el motor:**

| Campo | MongoDB (`$type`) | PostgreSQL (`jsonb_typeof`) |
|---|---|---|
| `payment.final_total` | `double` × 1000 | `number` × 1000 |
| `timestamp` | `string` × 1000 | `string` × 1000 |
| `order_id` | `string` × 1000 | `string` × 1000 |
| `items[].price` | `double` × 3075 | `number` × 3075 |
| `items[].qty` | `int` × 3075 | `number` × 3075 |

**Índices que quedaron:**

| Motor | Índice | Definición |
|---|---|---|
| MongoDB | `_id_` | `{_id: 1}` (automático) |
| MongoDB | `idx_orders_timestamp` | `{timestamp: 1}`, no único |
| MongoDB | `idx_orders_order_id` | `{order_id: 1}`, no único (F3-b) |
| PostgreSQL | `orders_pkey` | `UNIQUE btree (id)` (PK, R-03) |
| PostgreSQL | `idx_orders_timestamp` | `btree ((data ->> 'timestamp'::text))` (A3.2) |

Ninguno sobre `final_total` (R-15). Asimetría 3 frente a 2: la prevista en SPEC A3.3.

**Otros:**

- `id::text = data->>'order_id'` en 1000/1000 filas (0 distintos).
- `order_id` repetidos: 0 en ambos motores.
- R-01: `wiredTiger` en `storageStats`, mongod standalone (sin `isdbgrid` ni replica set).
- R-03: `\d+ orders` = `id uuid not null` + `data jsonb`, PK `orders_pkey`.
- **Persistencia del volumen (F3-a):** tras bajar y volver a levantar
  Postgres, siguen las 1 000 filas.

**Tiempos: no representativos a esta escala.** Mongo: carga 1.75 s · índices
4.99 s. Postgres: carga 0.99 s · índices 0.32 s · analyze 0.33 s. Con 1 000
registros dominan los arranques de `mongosh` y `mongoimport` (cada llamada
abre un proceso nuevo): los 4.99 s de índices en Mongo no miden el indexado.
No se extrapola nada desde G1; la extrapolación a 500 000 es criterio de G2.

### 2026-11-01 — G2: 10 000 registros y equivalencia de Q1/Q2 (F4)

Decisiones de G2 aprobadas por Alix: G2-a a G2-f y la opción (a) para la
copia literal (instaló `poppler-utils`).

Corrida: `scripts/run_gate.sh g2` → `results/f3/g2/run_20261101T185807Z.txt`.
Todos los pasos dieron exit 0.

**Queries literales.** `scripts/extract_queries.py` las recorta de
`pdftotext -layout` (poppler 26.01.0) y las escribe en `queries/`; la
procedencia y los SHA-256 están en `queries/README.md`. Cruzadas carácter por
carácter, sin espacios, con un segundo método de extracción: las 4 coinciden.
El literal de fecha del SQL de Q2 es `'2026-01-01 00:00:00Z'`, **con espacio**;
la primera extracción sin espacios no lo dejaba ver.

**Código nuevo:** `scripts/extract_queries.py`, `scripts/check_equivalence.py`,
`scripts/checks/tool_overhead.sh`, `scripts/run_gate.sh` (`run_g1.sh` no se
tocó) y `tests/test_equivalence.py`, con 22 pruebas. Suite: **97 de 97**. Al
escribir las pruebas aparecieron dos fallos:

- un defecto real: un cero `Decimal` formateado con `.3e` se mostraba como
  `0.000e+3`, que parece 1000; corregido con `float(...)`;
- una expectativa mal escrita en la propia prueba de empates.

**Equivalencia contra la referencia exacta:**

| Motor · variante | Q1 grupos | máx. dif. rel. total / avg | Q2 conjunto | máx. dif. rel. vector |
|---|---|---|---|---|
| Mongo · default / `allowDiskUse:false` | 240/240, count exacto | 9.9e-17 / 1.5e-16 | 1000/1000 iguales | 1.1e-16 |
| Mongo · `allowDiskUse:true` | — | — | 1000/1000 iguales | 1.1e-16 |
| Postgres · default (4MB) / `work_mem 4MB` | 240/240, count exacto | **0** / 2.6e-19 | 1000/1000 iguales | **0** |
| Postgres · `work_mem 64MB` | — | — | 1000/1000 iguales | **0** |

- Postgres suma en `numeric` exacto: diferencia 0. La de `avg` (2.6e-19) es
  el redondeo de la división.
- Las diferencias de Mongo (~1e-16) son la representación binaria de
  decimales como 567.24 en `double`, no un error de cálculo.
- Todas quedan muy por debajo de 1e-6.
- Referencia: 3 506 filas pasan el filtro de Q2, y es exactamente lo que
  devuelve la etapa `FETCH` de Mongo. Frontera del Top-1000: 567.24 frente a
  567.20, sin empate.

**Planes (PROFILE_A, 10 000):**

| | MongoDB | PostgreSQL |
|---|---|---|
| Q1 | `COLLSCAN` → `$unwind` → `$match` → `$group`; sin índice; `usedDisk: false` | `Seq Scan` paralelo (1 worker) → **`Sort` external merge en disco: 7 616 kB + 5 664 kB (worker)** → `Nested Loop` + `jsonb_array_elements` → `Incremental Sort` → `Aggregate` (Sorted); **1 662 bloques temporales = 13.0 MiB** (ver corrección abajo) |
| Q2 | **`IXSCAN` sobre `idx_orders_timestamp`** (4 960 claves) → `FETCH` (3 506) → `SORT` con `limitAmount: 1000` (top-K, 1.3 MB, `usedDisk: false`, 0 spills; igual con `allowDiskUse` true y false) | **`Seq Scan`** (no usa el índice, como predijo A3.2) → `Sort` **top-N heapsort 271 kB en memoria** → `Limit`; igual con 4MB y 64MB |

Hallazgos que van al reporte:

1. **Q1 vuelca a disco en Postgres ya con 10 000 documentos**, con el
   `work_mem` por defecto (4MB; el manual solo da variantes para Q2). El
   planner estima 330 000 filas tras `jsonb_array_elements` (33 por
   documento) cuando son 13 427 (1.34 por documento). Con esa estimación
   elige agregar ordenando, y ordena **los documentos completos** por país
   *antes* de desanidar, y eso es lo que no cabe en 4MB. Es efecto de la
   estimación del planner sobre JSONB, no del tamaño de los grupos (son
   240). A 500 000 se espera un ordenamiento externo mucho mayor: hay que
   medirlo en G3, no suponerlo. Esto **cambia la lectura de A12**: el spill
   aparece en Q1, no en Q2.
2. **Q2 no vuelca en ninguno de los dos motores** a 10 000: los dos usan un
   ordenamiento top-K (Postgres 271 kB, Mongo `limitAmount: 1000`), como
   anticipó A12. Las dos variantes de memoria dan el mismo plan. A 500 000
   se vuelve a comprobar.
3. **Planes asimétricos en Q2** (riesgo R14): Mongo usa su índice de
   `timestamp`; Postgres hace `Seq Scan`, porque su índice es de texto y el
   predicado convierte con `::timestamptz` (A3.2). La diferencia de latencia
   de Q2 medirá en parte planes distintos, no solo motores distintos.
4. Mongo ejecutó con el motor clásico (`explainVersion: 1`), no con SBE.

**Tiempo de carga** (arranque de las herramientas: mediana de 5 corridas
vacías; `mongoimport` 0.27 s, `mongosh` 1.29 s, `psql` 0.30 s):

| | Medido a 10 000 | Estimado a 500 000 (**no medido**) |
|---|---|---|
| Mongo | carga 1.56 s · índices 1.55 s (1.29 s son arranque de `mongosh`) | ~65 s + ~20 s ≈ **85 s** |
| Postgres | carga 1.64 s · índices 0.42 s · analyze 0.44 s | ~38 s + ~9 s + ~8 s ≈ **55 s** |

Supuestos: la carga y el analyze crecen de forma lineal y los índices como
n·log n. Es una estimación para planear G3; el valor real lo da G3.

#### Corrección (2026-11-01): bloques temporales de Q1 en G2

El resumen de planes de Postgres **sumaba** los `Temp Written Blocks` de todos
los nodos. En `EXPLAIN (BUFFERS)` cada nodo ya incluye los de sus hijos, así
que la suma contaba lo mismo varias veces: en G2 dio 8 310 bloques, y el valor
real es **1 662 bloques (13.0 MiB)**, el del nodo raíz. Coincide con los
7 616 + 5 664 kB del `Sort`.

- Afectaba solo a ese campo: en `results/f3/g2/{queries_postgres,equivalence}.json`
  y en el registro de arriba, ya corregido. No cambia ninguna conclusión.
- Detectado al revisar G3, donde la suma daba 861 438.
- Corregido en `pg_plan_summary()`. Prueba nueva: `TempBlocksTest`.
- Los resúmenes se recalcularon **desde los planes crudos guardados**, sin
  volver a ejecutar nada:
  `python3 scripts/check_equivalence.py summarize --gate g2|g3` →
  `results/f3/<gate>/plan_summary.json`.
- Los JSON originales de G2 se conservan como se generaron. El valor válido es
  el de `plan_summary.json`.

### 2026-11-01 — G3: 500 000 registros

Corrida: `scripts/run_gate.sh g3` → `results/f3/g3/run_20261101T191648Z.txt`.
Todos los pasos dieron exit 0. Durante el paso 3.b el equipo pareció
suspenderse (53 minutos de reloj frente a 3.5 minutos de proceso). No afecta
los resultados: ese paso lee archivos ya exportados, y los tiempos de carga
se midieron antes.

**Cambios de código para escalar.** Hasta G2 las comparaciones cargaban en
memoria los tres conjuntos de documentos; con 500 000 serían ~4–5 GB y la VM
tiene ~5 GB libres.

- `verify_gate.py`: la exportación va directo a disco (`sh_to_file`) y
  `compare()` compara en streaming por huella SHA-1 de la forma canónica de
  cada documento (`canonical_digest`, misma regla de igualdad que
  `first_difference`). Se agregan tamaños en disco.
- `check_equivalence.py`: la referencia exacta se calcula en una pasada
  (`truths`, `iter_exact`) y hay un subcomando `summarize`.
- Pruebas nuevas: `CanonicalDigestTest`, `CompareFilesTest` (archivos
  fabricados con un documento cambiado, uno faltante y uno de más),
  `UnaPasadaTest` y `TempBlocksTest`. Suite: **112 de 112**.
- **Regresión:** el `compare` nuevo, corrido sobre las exportaciones de G2,
  da exactamente lo registrado en G2 (`compare.json`; `equivalence.json` es
  idéntico salvo la fecha). Memoria máxima: 27 MB.

**Carga** (PROFILE_A), medida frente a lo estimado en G2:

| | Carga | Índices | Analyze | Total | Estimado en G2 |
|---|---|---|---|---|---|
| MongoDB | 68.9 s | 5.0 s | — | **73.9 s** | 85.4 s (×0.87) |
| PostgreSQL | 42.2 s | 7.4 s | 6.1 s | **55.7 s** | 55.0 s (×1.01) |

La estimación lineal de la carga acertó (×1.06 y ×1.10). La de índices con
n·log n sobreestimó en Mongo (5.0 s medidos frente a 20.2 s).

**Tamaño en disco:**

| | MongoDB (WiredTiger) | PostgreSQL |
|---|---|---|
| Datos | 216.2 MiB en disco (527.6 MiB sin comprimir) | 699.7 MiB (tabla) |
| Índices | 35.5 MiB: `_id_` 5.2 · `timestamp` 8.7 · `order_id` 21.6 | 38.4 MiB: `orders_pkey` 19.0 · `timestamp` 19.3 |
| Total colección / tabla | 251.7 MiB | 738.1 MiB |
| Directorio de datos (`du`) | 453.7 MiB | 1 792.7 MiB (incluye WAL de la carga) |

**Equivalencia contra la referencia exacta** (`equivalence.json`):

- **Q1:** 240 de 240 grupos y `count` exacto en ambos. Diferencia relativa
  máxima: Mongo 9.9e-17 (total) y 1.6e-16 (avg); Postgres **0** y 2.4e-19.
- **Q2:** los mismos 1 000 `order_id` y `customer_id` en las cuatro variantes.
  Vector de `final_total`: Mongo 8.1e-17, Postgres **0**.
- Las variantes de cada motor devuelven lo mismo.
- Referencia: 175 049 filas pasan el filtro, y es exactamente el `nReturned`
  del `FETCH` de Mongo. Frontera 1351.37 / 1351.29, sin empate. 20 valores
  repetidos dentro del Top-1000, como midió F2.

**Documentos** (`compare.json`): **500 000 de 500 000 iguales** en las tres
direcciones; 0 faltantes, 0 distintos; esquema al 100 % con 0 inválidos en
fuente, Mongo y Postgres. `id = order_id` en 500 000 de 500 000. Tipos:
`final_total` `double` (Mongo) y `number` (Postgres) en los 500 000;
`timestamp` y `order_id` `string`.

**Planes a 500 000** (`plan_summary.json`):

| | MongoDB | PostgreSQL |
|---|---|---|
| Q1 | `COLLSCAN` (500 000) → `$unwind` → `$match` → `$group`; `usedDisk: false` | `Seq Scan` paralelo (**2 workers**) → `Sort` external merge en disco en los 3 procesos (196 + 231 + 220 MiB de espacio de ordenamiento) → `Incremental Sort` (**también vuelca**) → `Aggregate`. **181 752 bloques = 1.4 GiB escritos**: `Sort` 165 978 propios, `Incremental Sort` 15 774. 8.6 s |
| Q2 | `IXSCAN` `idx_orders_timestamp` (250 207 claves) → `FETCH` (175 049) → `SORT` top-K `limitAmount: 1000` (1.4 MB, `usedDisk: false`, 0 spills); igual con `allowDiskUse` true y false | `Seq Scan` paralelo (2 workers) → `Sort` **top-N heapsort ~273 kB en memoria** en cada proceso → `Gather Merge` → `Limit`; igual con 4MB y 64MB; 0 bloques temporales |

Lo que confirma G3 respecto de G2:

1. **El volcado de Q1 en Postgres crece mucho con la escala**: de 13 MiB a
   1.4 GiB. Sigue causado por ordenar los documentos completos antes de
   desanidar (la estimación del planner sobre `jsonb_array_elements`).
2. **Q2 no vuelca en ningún motor**, con ninguna variante. Los dos usan
   top-K. La premisa de "estrés de buffer" de Q2 no se materializa a
   500 000 bajo PROFILE_A (A12). Falta ver PROFILE_C en la matriz.
3. **Planes de Q2 asimétricos** (R14): Mongo usa su índice; Postgres hace
   `Seq Scan` paralelo.
4. A esta escala Postgres paraleliza las dos queries (2 workers). Bajo
   PROFILE_C (1 CPU) esos workers competirán por la misma CPU: hay que
   tenerlo en cuenta al leer el throttling.

**Espacio** (`espacio_libre.txt`): 951 GB libres en la VM. Volúmenes de Docker:
4.6 GB en total, incluidos los de otros proyectos. Muy por debajo de los ~25 GB
estimados para el proyecto (SPEC §6, V4). Las exportaciones de G3
(`data/exports/g3_*.jsonl`, ~1 GB, no versionadas) siguen en disco.

**Estado de los motores al terminar:** los volúmenes contienen los 500 000
documentos con sus índices, en los dos motores. Es el estado de partida para F5.
