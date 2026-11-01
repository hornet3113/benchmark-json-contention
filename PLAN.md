# PLAN.md — Plan de implementación por fases

Regla transversal: **ninguna fase se declara completa sin evidencia de ejecución**. Cada fase cierra con un resumen de archivos modificados, comandos ejecutados, pruebas aprobadas, pendientes y siguiente acción.

Notación: `F0 → F1` significa que F1 no puede empezar sin que F0 esté cerrada.

```
F0 ─┬─ F1 ── F3 ─┬─ F4 ── F5 ── F6 ── F7 ── F8 ── F9
    └─ F2 ───────┘
```

---

## F0 — Validación de supuestos (sin código)

**Objetivo.** Cerrar las decisiones que no me corresponde tomar solo, antes de escribir una línea.

**Entradas.** `SPEC.md` §5.

**Trabajo.**
1. **Determinar la plataforma real.** Sistema operativo, versión, kernel, si hay virtualización de por medio, núcleos, RAM, disco libre. Sin asumir nada: lo que haya, se mide.
2. Verificar Docker: versión, que el demonio responda, driver y versión de cgroups, y que los límites de CPU y memoria **se apliquen de verdad** a un contenedor de prueba.
3. Verificar cgroups v2 y la disponibilidad de los archivos que alimentan el CSV (`cpu.stat`, `memory.stat`, `memory.peak`, `memory.events`, `memory.swap.max`).
4. Consultar al docente las ambigüedades de impacto alto: A1 (`final_total`), A2 (36 vs 54 celdas), A3.2 (índice de timestamp), A12 (si la premisa de spill no se materializa, qué se reporta).
5. Decidir y dejar escrita la política de A4 (ventana con pocas muestras completadas).

### Verificaciones COMPLETADAS (2026-10-31)

- [x] Plataforma determinada por comando: Windows 11 + WSL2 2.6.3.0 + Docker Desktop, distribuciones `Ubuntu` y `docker-desktop`.
- [x] Hardware: Ryzen 5 PRO 5675U, 6 núcleos físicos / 12 lógicos, 14.8 GiB RAM, 473 GB libres en C:.
- [x] Recursos visibles para contenedores: 12 CPUs, 7.159 GiB.
- [x] `stat -fc %T /sys/fs/cgroup` → `cgroup2fs`.
- [x] Docker Engine 29.4.1, Compose v5.1.3, OSType linux, Cgroup Version 2.
- [x] **Los límites se aplican de verdad:** contenedor con `--cpus=1 --memory=1024m --memory-swap=1024m` reporta desde dentro `cpu.max=100000 100000`, `memory.max=1073741824`, `memory.swap.max=0`.
- [x] Archivos de métricas presentes dentro del contenedor: `cpu.stat`, `memory.stat`, `memory.peak`, `memory.events`, `memory.swap.max`.
- [x] `sudo` disponible en la distribución Ubuntu.
- [x] Docker accesible desde Ubuntu (integración de Docker Desktop activa) → Python y Bash correrán ahí.
- [x] Limitaciones del entorno virtualizado documentadas en SPEC §6 (L1–L7).

### Verificaciones de entorno COMPLETADAS (2026-10-31)

- [x] **V1 — `drop_caches` tiene efecto sobre el caché de los contenedores.** Medido: `buff/cache` 787 MB → 387 MB tras el flush desde Ubuntu. Demuestra limpieza efectiva, **no** caché frío: quedan 387 MB sin liberar y la capa de Windows sobre el `.vhdx` permanece intacta. R-21 se cumple con el alcance que este entorno permite, declarado en SPEC A5.
- [ ] **V2 — Ruta de respaldo: documentada pero NO ejecutada.** El contenedor privilegiado está descrito en SPEC A5 como plan B. No se probó, así que no se marca como verificado. Solo se ejecutará si V1 deja de funcionar.
- [x] **V3 — Sistema de archivos nativo.** `~` resuelve a `/home/alix_anahi` sobre `/dev/sdf`, ext4 de WSL2. L6 evitado. *Ojo:* la sesión arranca en `/mnt/c/Users/...`, así que los scripts deben posicionarse explícitamente en el directorio del proyecto.
- [x] **V4 — Espacio suficiente.** 954 GB libres dentro de la VM, acotados en la práctica por los 473 GB de C:. El proyecto necesita ~25 GB estimados. Docker ya ocupa ~51 GB de otros proyectos; hay margen de sobra.
- [x] **V5 — Ruido en reposo bajo.** `loadavg` 0.38/0.12/0.04, 999 MiB usados, 6.2 GiB disponibles, swap sin tocar. Es la línea base contra la que se compara el ruido durante las corridas.
- [x] **V6 — El throttling se puede observar.** `--cpus=0.5` con 10 s de carga continua → `throttled_usec` 5 022 196, es decir ~5.02 s estrangulados de 10. La aritmética cuadra con el límite impuesto: el instrumento mide lo que dice medir.

### Verificaciones PENDIENTES

- [ ] **V2 — Ruta de respaldo del flush.** Solo si V1 deja de funcionar.
- [x] **V8 — Comportamiento de `mem_swappiness` bajo cgroups v2. RESUELTA en F1 (2026-11-01).** Compose no pasa la clave a Docker (`docker compose config` la omite; `compose up` no avisa); `docker inspect` da `MemorySwappiness=<nil>`; `memory.swappiness` no existe en el cgroup v2; y `docker create --memory-swappiness=0` directo devuelve `WARNING: … Memory swappiness discarded.` No es fallo: "sin swap" lo garantiza `memory.swap.max=0`. Evidencia: `results/env/f1/V8_mem_swappiness_20261101T171426Z.txt`. Detalle en SPEC A7.
- [ ] **V7 — `sudo` no interactivo para el flush.** En V1 apareció el prompt de contraseña y una corrida desatendida se colgaría ahí. **No se configura nada permanente todavía:** el diseño restringido está en SPEC A5 y se revisa antes de F8. Para F1 y la celda piloto se usa `sudo -v` con renovación, que no deja rastro en el sistema.

### Decisiones TOMADAS (2026-10-31)

- [x] **D-WSL1** — Se conserva la VM en 7.159 GiB con su swap global; no se crea `.wslconfig`. PROFILE_A queda declarado como baseline con holgura limitada. Se revisa si el CV de la celda piloto supera 15 %.
- [x] **A1** — Opción (a): `payment.final_total` como hermano de `payment.totals`, que contiene `{subtotal, tax, discount}`. Las queries del manual corren literalmente.
- [x] **A3.2** — Índice B-Tree sobre el timestamp extraído como **texto**, sin modificar Q2. Se captura el plan real y **no se exige** que el planner use el índice; si no lo usa, se reporta como hallazgo.
- [x] **A4** — Se registran solo las consultas completadas dentro de la ventana. Los casos con pocas muestras y los de cero muestras se tratan explícitamente y se marcan; no se rellenan percentiles inventados.
- [x] **A5** — Flush por repetición, con registro del delta de `buff/cache` como evidencia.
- [x] **A8** — Distribuciones propuestas en SPEC §5 A8, con semilla fija y versionada.
- [x] **A12** — Se aceptan los resultados reales aunque no aparezcan spill ni OOM. Las sondas de detección se reportan aparte, etiquetadas.

### Decisión PENDIENTE DE TERCEROS

- [ ] **A2** — Se propone al docente: **54 celdas, 162 corridas**, con la variante de Q2 codificada en `query_id`. Hasta su confirmación, el runner se diseña parametrizable para soportar ambos conteos sin reescribirlo.

**Estado de F0: cerrada con reservas explícitas.** V1 y V3–V6 completadas con evidencia. V2 documentada sin ejecutar. V7 diseñada sin aplicar, suficiente para F1 con la vía temporal. Decisiones tomadas salvo A2, que depende del docente y no bloquea F1 porque el runner se diseña parametrizable.

**Estado del entorno: apto.** Los límites se aplican, el throttling se observa y se cuantifica, el flush tiene efecto medido, el disco sobra y el ruido en reposo es bajo.

**Evidencia de F0.** Toda la salida de comandos de esta fase se conserva en `results/env/f0/`, en el archivo **`F0_salidas_observadas.md`** (agregado el 2026-11-01). Es una **transcripción** de las salidas que Alix vio en pantalla el 2026-10-31, no una captura automática con `tee`: los comandos se corrieron de forma interactiva, antes de que existiera el repositorio. Las capturas de pantalla originales son el respaldo primario, y cada comando está anotado para poder repetirlo. Las verificaciones marcadas corresponden a comandos efectivamente ejecutados; las no ejecutadas quedan sin marcar.

**Riesgo si se salta.** Se implementa el generador con un esquema de `payment` que luego hay que rehacer sobre 500 000 documentos.

---

## F1 — Entorno Docker y perfiles de recursos

**Depende de:** F0.

**Trabajo.** `docker-compose.yml` parametrizado por `.env` de perfil; servicios de Mongo y Postgres mutuamente excluyentes; `memory-swap` = `memory` (A7); healthchecks; `capture_env.py` que lee los límites **reales** del cgroup, no los declarados.

**Criterios de aceptación.**
- [x] Para cada perfil, `cpu.max` y `memory.max` leídos dentro del contenedor coinciden con la tabla de playbook.pdf §3 (A: 400000/100000 y 4294967296; B: 200000/100000 y 2147483648; C: 100000/100000 y 1073741824). — En ambos motores: `results/env/f1/PROFILE_*_20261101T1728*Z` y `…T1729*Z.{txt,json}`.
- [x] `memory.swap.max` = 0 en los tres perfiles. — En los seis casos, en los mismos archivos.
- [x] `capture_env.py` emite un JSON con versión del motor, digest de imagen, límites reales y datos del host (R-28). — `scripts/capture_env.py` (esquema `capture_env/1`); su salida va dentro de cada `PROFILE_*_…T1728*Z/T1729*Z.json`. Pruebas: `tests/test_capture_env.py`, 10 de 10.
- [x] Prueba negativa: un contenedor de prueba que pide 2 GB en PROFILE_C muere por OOM y `memory.events` lo registra. — `scripts/probes/oom_profile_c.sh`: exit 137, `oom_kill 1`, `OOMKilled=true`. `results/env/f1/OOM_PROFILE_C_SEVERE_20261101T171903Z.txt`.

**Evidencia.** `results/env/f1/<PROFILE_ID>_<motor>_<fecha>.{txt,json}` + salida del test de OOM.

### Estado de F1 al 2026-11-01: CERRADA

Escrito y validado estáticamente (2026-10-31):

- [x] `docker/docker-compose.yml` parametrizado por perfiles, con `memswap_limit = mem_limit` (A7) y volúmenes nombrados (L6).
- [x] `docker/profiles/{a_baseline,b_medium,c_severe}.env` con los valores de playbook.pdf §3 y los valores esperados del cgroup.
- [x] `scripts/up_profile.sh`, `down_profile.sh`, `verify_limits.sh`.
- [x] `docs/F1_INFRAESTRUCTURA.md` con procedimiento y criterios.
- [x] YAML validado y variables resueltas con `docker compose config`.
- [x] Dos defectos corregidos durante la escritura: dos puntos dentro de un mensaje de error rompían el YAML, y `EXPECT_CPU_MAX` sin comillas rompía al cargar el archivo en Bash.

Ejecutado en la máquina (2026-11-01). Todo con archivo en `results/env/f1/`:

- [x] `docker pull` de ambas imágenes, con exit 0. MongoDB **8.2.12** (`sha256:e0ce8c35…4bd3`) y PostgreSQL **18.6** (`sha256:3a426452…4b81`). — `docker_pull_20261101T164211Z.txt`
- [x] PROFILE_A, PROFILE_B y PROFILE_C verificados en Mongo y en Postgres: límites iguales a los esperados, 5 de 5 archivos de métricas presentes y `memory.swap.max=0`. — `PROFILE_*_{mongodb,postgresql}_*.{txt,json}` y `up_*.txt`
- [x] V8 resuelta con evidencia (ver F0 y SPEC A7). — `V8_mem_swappiness_20261101T171426Z.txt`
- [x] Prueba negativa de OOM. — `OOM_PROFILE_C_SEVERE_20261101T171903Z.txt`
- [x] `capture_env.py` escrito y probado; `verify_limits.sh` ya solo compara. — `PROFILE_*_…T1728*Z/T1729*Z.json`

**Defecto encontrado y corregido en `verify_limits.sh` (2026-11-01).** La versión original generaba el informe dentro de `{ … } | tee`. Ese bloque corre en un subproceso, así que el `FAIL=1` se perdía: **el código de salida siempre era 0 y `"coinciden"` siempre `true`**, aunque hubiera discrepancias. Las líneas `OK`/`FALLA` sí eran correctas. Por eso:

- Las seis verificaciones de las 16:46 y las 17:10–17:11 UTC son válidas por sus líneas `OK`, pero su exit 0 no prueba nada.
- Se corrigió el script y se comprobó con una prueba negativa: un contenedor en PROFILE_A verificado como C da `FALLA`, exit 1 y `coinciden: false`. Esa salida se escribió fuera de `results/`.
- Las seis verificaciones se repitieron con el script corregido (17:28–17:29 UTC) y dieron los mismos valores. **Esas son la evidencia de cierre.**

**Quedó fuera de F1, a propósito:**

- Clasificar el OOM como `status=oom` y medir throttling en PROFILE_C bajo carga: son sondas de F6.
- ~~Fijar las imágenes por digest en `docker/images.env`~~ — **hecho el 2026-11-01**, después del cierre: `mongo@sha256:e0ce8c35…4bd3` y `postgres@sha256:3a426452…4b81`, con la etiqueta de origen como comentario. PROFILE_A se re-verificó en ambos motores con las imágenes fijadas, y los contenedores arrancan con exactamente ese digest. — `results/env/f1/PROFILE_A_BASELINE_{mongodb_20261101T174228Z,postgresql_20261101T174244Z}.{txt,json}` y `up_a_baseline_*_digest.txt`.

**Nota de trazabilidad.** Los archivos se escribieron el 2026-10-31 en un entorno sin demonio Docker, así que solo se validaron estáticamente. Todas las pruebas con contenedores se ejecutaron el 2026-11-01 en la máquina del estudiante (Docker 29.4.1, WSL2), y su salida está en `results/env/f1/`.

---

## F2 — Generador de dataset

**Depende de:** F0. Puede ir en paralelo con F1.

**Trabajo.** `synthetic_data_generator.py` con semilla fija, escritura en streaming (JSONL) para no cargar 500 k documentos en RAM, y modos `--size 1000|10000|500000`.

**Criterios de aceptación.**
- [x] 500 000 registros generados; `wc -l` lo confirma. — `results/f2/F2_3_20261101T181011Z_verificacion.txt` §2
- [x] Validación de esquema (R-10) sobre muestra de 1 000: todos los atributos presentes, 3 niveles de anidamiento verificados programáticamente. — `results/f2/F2_2_20261101T180005Z.txt` §5, leído de disco. Además, los 500 000 se validaron al generarse (`results/dataset_stats.json`: `registros_invalidos: 0`, `anidamiento_niveles: {3: 500000}`).
- [x] Media de ítems por registro en [2.9, 3.1]. — 2.9991 (verificación de F2.3 §3)
- [x] Dos ejecuciones con la misma semilla producen el **mismo hash SHA-256** del archivo. — Con 1 000 (F2.2 §4) y con **500 000** (F2.3 §1): `0cd7fadb…0414` en dos procesos; `cmp` da idénticos.
- [x] `final_total` es tipo número (no string) en el 100 % de la muestra. — 0 no numéricos en 1 000 (F2.2 §5) y en 500 000 (F2.3 §3)
- [x] `results/dataset_stats.json` publica: % `completed`, % con `price>50`, cardinalidad `country`×`category`, rango de timestamps.

**Pruebas.** `tests/test_generator_schema.py` (31) y `tests/test_generator_determinism.py` (16); 58 de 58 en la suite completa.

### Estado de F2 al 2026-11-01: CERRADA

Revisada y aprobada por Alix. Plan, decisiones (F2-a…F2-f, tolerancia ±1 punto) y registro completo en `docs/F2_GENERADOR.md`.

- **Dataset:** `data/orders_500000_seed42.jsonl` (no versionado; se regenera). 500 000 registros, 501 751 458 bytes, SHA-256 `0cd7fadb084627679ab2437921ef1889a012e1fa5b0898d2624760be41060414`, Python 3.14.4, semilla 42.
- **Metas de A8 en 500 000:** `completed` 69.97 %, `timestamp >= 2026` 50.04 %, `price > 50` 44.87 %, 2.9991 ítems por registro, 240 de 240 grupos de Q1.
- **Cruce verificado por Alix:** 69.97 % × 50.04 % = 35.01 %, igual a las 175 049 filas del filtro de Q2. Cuadra porque `status` y `timestamp` se sortean de forma independiente.
- **`order_id`:** 500 000 distintos, todos en forma canónica. La igualdad con el `id` de Postgres se garantiza y comprueba en F3-G1 (`docs/F2_GENERADOR.md`).
- **Prefijo:** los archivos de 1 000 y de 10 000 son el inicio exacto del de 500 000 (`cmp`). Lo validado en G1 y G2 es parte literal de lo que se carga en G3.
- **Q2:** sin empate entre las filas 1000 y 1001 (1351.37 / 1351.29), pero hay 20 valores repetidos *dentro* del Top-1000. El conjunto está determinado y el orden interno no: confirma comparar como conjunto en F4.

---

## F3 — Carga e indexación escalonada

**Depende de:** F1 y F2. **Se carga en tres etapas, nunca directo a 500 k.** Cada compuerta cierra antes de pasar a la siguiente: un error de esquema descubierto con 1 000 registros cuesta segundos; el mismo error descubierto con 500 000 cuesta la tarde.

**Trabajo.** `load_dataset.sh` parametrizado por tamaño, con `mongoimport` y `COPY` desde JSONL; creación de índices (R-02, R-04); `VACUUM ANALYZE` en Postgres para que el planner tenga estadísticas.

### G1 — Compuerta de 1 000 registros (segundos)

- [x] Carga sin errores en ambos motores; conteos iguales a 1000. — `results/f3/g1/load_{mongo,postgres}.json`
- [x] Validación de esquema (R-10) sobre el 100 % de los registros cargados, no sobre muestra. — `results/f3/g1/compare.json` (y `results/f3/g2/`, `results/f3/g3/`)
- [x] `final_total` llega como número, no como string, **leído desde el motor** (no desde el archivo): en Mongo, `typeof` del campo; en Postgres, `jsonb_typeof(data->'payment'->'final_total') = 'number'`. — Mongo `double`, Postgres `number`, en el 100 % (`export_*.json` de G1, G2 y G3)
- [x] `timestamp` es string ISO-8601 en ambos. — `string` en los dos motores; formato estricto validado en todo lo exportado
- [x] Un documento tomado por `order_id` es equivalente entre motores tras normalizar el orden de claves (JSONB reordena y deduplica). — Ampliado (F3-e): **todos** los documentos, en tres direcciones; 1 000/1 000 en `results/f3/g1/compare.json`
- [x] Índices creados; resuelta empíricamente la pregunta de A3.2 (qué variante de índice es creable) con la salida del comando como evidencia. — `results/f3/g1/a32_index_variants.txt`: solo la de texto; `::timestamp` y `::timestamptz` fallan (SPEC A3.2)

### G2 — Compuerta de 10 000 registros (minutos)

- [x] Conteos iguales a 10000. — `results/f3/g2/load_*.json`
- [x] **Equivalencia de resultados Q1 y Q2 entre motores** (es la fase F4, que se ejecuta aquí). — `results/f3/g2/equivalence.json`, contra una referencia exacta calculada en Python
- [x] `EXPLAIN` / `explain` capturados: queda registrado si cada motor usa o no su índice de timestamp, y si los planes son simétricos (ver A3.2). — `results/explains/g2/`: Mongo usa `idx_orders_timestamp` en Q2; Postgres hace `Seq Scan`. **Planes asimétricos** (R14)
- [x] Medición del tiempo de carga a 10 k → extrapolación del tiempo de carga a 500 k. — `results/f3/g2/load_extrapolation.json`; contrastada con lo medido en G3 (`results/f3/g3/load_vs_estimate.json`)

### G3 — Carga definitiva de 500 000 (R-08)

- [x] `db.orders.countDocuments()` = `SELECT count(*) FROM orders` = 500000. — `results/f3/g3/load_*.json`, `export_*.json`
- [x] Equivalencia Q1/Q2 **re-verificada a escala real**: una equivalencia válida en 10 k podría romperse por valores extremos que solo aparecen con 500 k. — `results/f3/g3/equivalence.json`
- [x] Índices listados y capturados en evidencia; **ninguno** sobre `final_total` (R-15). — `results/f3/g3/export_*.json`
- [x] Planes de ejecución re-capturados: la selectividad cambia con el volumen y el planner puede elegir distinto que en G2. — `results/explains/g3/`, `results/f3/g3/plan_summary.json`. A 500 k Postgres paraleliza con 2 workers
- [x] Tiempo de carga y tamaño en disco de cada motor registrados, con sus índices por separado. — Mongo 73.9 s, 216 MiB de datos + 35.5 MiB de índices; Postgres 55.7 s, 700 MiB + 38.4 MiB (`results/f3/g3/load_*.json`, `export_*.json`)
- [x] Espacio libre restante verificado contra la estimación de SPEC §6. — 951 GB libres (`results/f3/g3/espacio_libre.txt`)

### Estado de F3 al 2026-11-01: CERRADA

Revisada y aprobada por Alix compuerta por compuerta (G1, G2 y G3). Plan, decisiones F3-a…F3-e y G2-a…G2-f, y registro completo en `docs/F3_CARGA.md`.

- **Los 500 000 documentos sobreviven a la carga sin cambios** en los dos motores: 500 000/500 000 iguales en tres direcciones (fuente = Mongo = Postgres), esquema al 100 % y `id = order_id` en todas las filas.
- **A3.2 resuelta en la práctica:** solo es creable el índice de texto; `::timestamp` y `::timestamptz` fallan porque `timestamp_in` y `timestamptz_in` son `STABLE` (SPEC A3.2).
- **Volcado a disco:** Q1 vuelca 1.4 GiB en Postgres; Q2 no vuelca en ningún motor (SPEC A12).
- **Estado de los motores:** los volúmenes contienen los 500 000 documentos con sus índices. Es el punto de partida de F5.
- **Corrección registrada:** el resumen de bloques temporales de Postgres sumaba nodos acumulativos (G2: 8 310 → 1 662 reales). Se recalculó desde los planes crudos (`results/f3/g{2,3}/plan_summary.json`).

---

## F4 — Queries y equivalencia de resultados

**Depende de:** F3-G1; se ejecuta como contenido de la compuerta G2 y se repite en G3. **Es la fase que protege la validez del experimento entero.**

**Trabajo.** Archivos de `queries/` copiados literalmente del playbook; ejecutor que los lee de disco (nunca queries embebidas en el código, para que el revisor pueda diffear contra el PDF); comparador de resultados.

**Criterios de aceptación — sobre dataset de 10 000, no sobre 500 k.**
- [x] Q1: el conjunto de grupos `(country, category)` es idéntico entre motores; `count` idéntico exacto; `total_revenue` y `avg_revenue` con diferencia relativa < 1e-6. — 240/240; máx. 1.5e-16 Mongo, 0 Postgres (`results/f3/g2/equivalence.json`; en G3, 1.6e-16 y 0)
- [x] Q2: los 1 000 `order_id` devueltos coinciden como conjunto entre motores. — En las cuatro variantes, en G2 y en G3
- [x] Q2: el vector ordenado de `final_total` coincide con tolerancia < 1e-6. — Máx. 1.1e-16 (G2) y 8.1e-17 (G3) en Mongo; 0 en Postgres
- [x] Documentado el tratamiento de empates: ninguna de las dos queries del manual tiene desempate, así que con `final_total` repetidos el orden **no es determinista** en ninguno de los dos motores. Se compara como conjunto, no posición a posición, y se deja escrito. — Medido: sin empate en la frontera del Top-1000 (567.24/567.20 en G2; 1351.37/1351.29 en G3), con 7 y 20 valores repetidos dentro (`docs/F3_CARGA.md`)

**Si esta fase falla, no se sigue.** Un fallo aquí casi siempre significa que `final_total` se guardó como string (A1) o que el timestamp se guardó como `Date` en Mongo (SPEC §2).

**Pruebas.** `tests/test_equivalence.py`.

### Estado de F4 al 2026-11-01: CERRADA

Ejecutada dentro de F3-G2 (10 000) y re-verificada en F3-G3 (500 000), según el diseño de esta fase. Aprobada por Alix.

- **Queries literales:** `queries/` se recorta del PDF con `scripts/extract_queries.py` (`pdftotext -layout`); cruzada carácter a carácter con un segundo método de extracción; SHA-256 en `queries/README.md`. Se comprueba al inicio de cada compuerta (`--check`).
- **Ejecutor:** `scripts/check_equivalence.py` lee las queries de disco y las ejecuta con las variantes de §5.2.
- **Referencia exacta:** calculada en Python con `Decimal` desde el archivo fuente. Los dos motores se comparan contra ella, no solo entre sí.
- **Variantes:** `allowDiskUse` true/false y `work_mem` 4MB/64MB devuelven el mismo resultado en ambas escalas.
- **Pruebas:** `tests/test_equivalence.py`, con comparadores probados con defectos puestos a propósito.

---

## F5 — Runner de benchmark

**Depende de:** F4.

**Trabajo.** Bucle cerrado sin think time: N procesos ejecutan la query en loop; fases warmup 60 s / medición 300 s / cooldown 60 s; las latencias de warmup y cooldown se descartan; escritura de una fila CSV por repetición.

**Criterios de aceptación.**
- [x] `tests/test_percentiles.py`: con una distribución conocida, P50/P95/P99 dan el valor esperado; el método de interpolación está documentado. — `statistics.quantiles(method="inclusive")`, declarado en `percentiles.METHOD` (`test_uno_a_diez`, `test_coincide_con_la_formula_lineal`, `test_metodo_declarado`; `results/f5/tests_cierre_20261102T004918Z.txt`)
- [x] `tests/test_csv_schema.py`: el encabezado generado coincide **byte a byte** con el de playbook.pdf §8.2; cualquier columna extra o renombrada hace fallar la prueba (R-26). — Comparado con `pdftotext` sobre el PDF (`test_igual_al_pdf_sin_espacios`); `test_columna_extra_hace_fallar`, `test_columna_renombrada_hace_fallar`
- [x] `tests/test_status_domain.py`: `status` solo acepta `ok|spill|oom|error`; la combinación `status=ok` con `disk_spill=true` es rechazada. — `test_dominio_cerrado`, `test_ok_con_spill_esta_prohibido`
- [ ] El modo `--smoke` (warmup 5 s / medición 20 s / cooldown 5 s) corre una celda completa en menos de un minuto. — **Declarado INCUMPLIDO** (decisión de Alix): Postgres 48 s; **Mongo 95 s**, por la consulta en frío de 27 s, la gracia y la captura del plan (`results/smoke_anterior_20261101T215814Z/f55_20261101T213019Z.txt`). No se acortó el humo para forzarlo
- [x] Las latencias crudas se guardan en `results/raw/` para poder recalcular percentiles después. — Cada crudo guarda `muestras` = `[inicio_ns, fin_ns, ok, worker]`. Comprobado en humo (`results/smoke*/raw/*.json`), que escribe en `results/smoke/raw/`; las corridas reales usan el mismo código con `results/raw/`, que aún no existe porque no hay corridas reales

### Estado de F5 al 2026-11-01: CERRADA

Cerrada por Alix con la opción (b), después de revisar las corridas de humo. Plan, decisiones F5-a…F5-i y registro completo en `docs/F5_RUNNER.md`.

- **Runner:** `benchmark_runner/` (bucle cerrado, ventanas, censura A4, cgroup leído desde el host, detección de suspensión, flush con efecto medido, límites verificados antes de cada repetición, motor en CPUs 0–7 y runner en 8–11). CSV de humo `VÁLIDO` en todas las tandas.
- **Modo por defecto: 10 procesos × 5 hilos para c=50**, cada hilo con su conexión. La decisión se sostiene en p50, throughput, concurrencia vista por el motor, conexiones (153 en ambos modos) y memoria del runner (~460 MiB frente a ~1 990 MiB). **No en el p95.**
- **p95 de la comparación A-B-A: INCUMPLIDO, con su causa.** Todas las consultas de más de 28 s son la primera de cada worker (en frío, de +27 a +35 s), y el calentamiento de humo termina a +30.3 s. La discrepancia **se invirtió entre tandas** (en una el lento fue B, en la otra A1), y un efecto del modo no se invierte.
- **Criterio de concurrencia:** v2 (≥ 48 en los bordes) incumplido en Mongo (47); la sonda v3 con fotos cronometradas no se fijó antes de correr, y sus resultados (mediana 50 en las 3) se citan como evidencia.
- **Pruebas:** 213/213 (`results/f5/tests_cierre_20261102T004918Z.txt`).
- **Al reporte:** el plan de c=1 no es el de c=50 (se agotan los workers paralelos de Postgres); el throttling se acumula por CPU; `max_rss_mb` (anon) no cuenta la memoria compartida de Postgres.

---

## F6 — Telemetría, spill y OOM

**Depende de:** F5.

**Trabajo.** Lectura de cgroup v2 antes/después de la ventana; muestreo de RSS a 1 s; `prometheus.yml` con `scrape_interval: 1s`; detectores de spill por motor (A6).

**Distinción que gobierna toda esta fase.** Hay que separar dos cosas que es fácil confundir y cuya confusión sería fabricar evidencia:

- **Capacidad de detección del instrumento:** ¿sabría el runner reconocer un spill o un OOM si ocurriera? Se demuestra con **queries sonda** diseñadas para forzar el fenómeno. Viven en `scripts/probes/`, nunca en `queries/`, y **no generan filas del CSV**.
- **Resultado real del benchmark:** ¿ocurre spill u OOM al correr Q1 y Q2 del manual? Es una pregunta abierta cuya respuesta puede ser que no. Ver SPEC A12: el top-K sort de ambos motores puede evitar el volcado por completo con `LIMIT 1000`.

**Criterios de aceptación — capacidad de detección (sondas).**
- [x] `up == 1` para cAdvisor y node_exporter en Prometheus. — `results/f6/f6_1/check_monitoring_reposo_20261102T032714Z.json`; tras la corrección de node_exporter, `results/f6/f6_3/check_monitoring_cadvisor_2cpu_*.json`; bajo carga, `results/f6/f6_4/humo_f64/check_f64.json` (`up` mínimo 1)
- [x] **Sonda de throttling:** en PROFILE_C, `cpu_throttled_seconds` > 0 con una carga de CPU sostenida. Esta sí debe ocurrir necesariamente: con `cpu.max` fijado y trabajo que excede la cuota, el CFS throttling es mecánico. Si sale 0, el límite no se está aplicando y todo el experimento es inválido. — `results/f6/probes/throttling_profile_c_{postgresql,mongodb}_*.json` (143 s y 222 s en 120 s)
- [x] **Sonda de spill en Postgres:** una consulta de ordenamiento **sin `LIMIT`** sobre el conjunto filtrado, con `work_mem='4MB'`, incrementa `pg_stat_database.temp_bytes` y muestra ordenamiento externo en el `EXPLAIN ANALYZE`. Demuestra que el detector funciona. — `results/f6/probes/spill_postgres_c_severe_20261102T044223Z.json` (+32.7 MB, `external merge`; el control con Q2 tal cual no vuelca)
- [x] **Sonda de spill en MongoDB:** un `$sort` sin `$limit` con `allowDiskUse:true` incrementa los contadores de spill y marca `usedDisk` en el `explain`. — `results/f6/probes/spill_mongo_c_severe_20261102T044309Z.json` (+212 MB, `usedDisk: true`; sin `$limit` ni `$project`, porque con el `$project` no llega a 100 MB; control sin volcado)
- [x] **Sonda de OOM:** un contenedor o una carga deliberada que exceda `memory.max` en PROFILE_C produce `oom_kill > 0` en `memory.events`, y el runner lo clasifica como `status=oom`. — `results/f6/probes/oom_engine_{postgresql,mongodb}_*.json` (dentro del contenedor del motor, por el clasificador del runner)
- [x] El `cpu_throttled_seconds` leído del cgroup y el derivado de Prometheus difieren menos de 5 % (control cruzado de las dos fuentes). — sondas: 0.14 % y 0.20 %; F6.2: 0.11 % y 0.03 %; humo de F6.4: 0.04–0.58 %

**Criterios de aceptación — medición real.**
- [ ] El runner registra `disk_spill` y `status` por lo que **observa**, sin valores por defecto optimistas ni pesimistas.
- [ ] Queda explícitamente aceptado que `disk_spill=false` en todas las celdas es un resultado válido, y que en ese caso M2 se responde con esa evidencia en vez de forzar el escenario esperado.
- [ ] Si ninguna celda produce spill, se registra además la vía alternativa de presión de memoria (concurrencia 50 × `work_mem` en Postgres, dimensionamiento del caché de WiredTiger en Mongo) para la sección 6 del reporte.

**Nota.** Las sondas demuestran que el experimento **puede** observar los fenómenos que afirma medir. Lo que observe después en la matriz es el hallazgo, y va tal cual.


### Estado de F6 al 2026-11-02: CERRADA

Cierre aprobado por Alix tal como se propuso en `docs/F6_TELEMETRIA.md` ("Cierre de F6"), donde están las decisiones F6-a…F6-h, las ambigüedades F6-A1…A4 y el registro completo.

- **Monitoreo:** Prometheus v3.15.1, cAdvisor v0.60.6 (ghcr.io) y node_exporter v1.12.1, fijados por digest, en un proyecto de compose aparte (`benchmon`), en las CPUs 8–11. Adaptado a Docker Desktop/WSL2: cAdvisor lee los cgroups crudos `/docker/<id>` (sin etiqueta `name`), `jitter_factor=0` para tener 1 s real, y node_exporter solo con los colectores usados (el de `filesystem` causó un OOM real en F6.3).
- **Definiciones (F6.2):** `container_memory_rss` = `anon`, comprobado con el contenedor congelado; throttling cgroup/Prometheus al 0.03–0.11 % con carga.
- **Runner:** comprobación previa y recuperación (F6-A4); exportación de las series crudas por repetición a `telemetry/<run_id>.json`; `serie_cgroup_1s` en el crudo; un cgroup ilegible → `RunAborted`; un fallo de telemetría no detiene la matriz (F6-A1).
- **Humo de F6.4 (Alix):** 4 repeticiones, telemetría completa y sin huecos, la serie de 1 s igual a `max_rss_mb`, throttling columna/Prometheus al 0.04–0.58 %.
- **Pruebas:** 248/248 (`results/f6/f6_5/tests_cierre_20261102T105619Z.txt`).
- **Medición real:** las tres casillas quedan para F8.
- **Al reporte:** el throttling se acumula por CPU; `max_rss_mb` frente a `working_set` (M3, SPEC A11); el throttling de Mongo en reposo (C ≈ 27 s y B ≈ 3.6 s por cada 300 s); `OOMKilled=True` no significa que el motor cayó.

---

## F7 — Celda piloto y validación del CSV

**Depende de:** F6. Exigido explícitamente por diapo 13/13.

**Trabajo.** Correr una celda real completa: MongoDB × PROFILE_C × Q2_MEM_LOW × concurrencia 1, con tiempos reales (420 s) y 3 repeticiones. Luego la misma celda en Postgres.

**Criterios de aceptación.**
- [x] 3 filas en el CSV con `run_number` 1, 2, 3. — 6 filas (3 por motor) en `results/f7/measurements.csv`
- [x] `validate_csv.py` pasa: encabezado exacto, tipos correctos, dominios cerrados, sin celdas vacías salvo las permitidas. — `VÁLIDO` en `results/f7/pilot_20261102T111824Z.txt`
- [x] Coeficiente de variación del throughput entre las 3 repeticiones **< 15 %**. Si es mayor, el entorno tiene ruido (otros procesos del host, térmico) y hay que estabilizarlo antes de gastar 19 h en la matriz. — **4.2 % (Mongo) y 3.8 % (Postgres)**, `results/f7/check_pilot.json`
- [x] **Sin tendencia monótona entre las 3 repeticiones** (pedido por Alix al cerrar F6). Además del CV, revisar si throughput y latencias suben o bajan en orden (r1 < r2 < r3 o r1 > r2 > r3). El CV no detecta una degradación progresiva: 100-110-120 da un CV del 9 % y pasa. Origen: en F6.3, la sonda de spill de Mongo se degradó de 31 a 62 y a 161 s en tres corridas seguidas. Si hay tendencia, se busca la causa (caché, memoria de la VM, térmico) antes de F8, aunque el CV pase. — Mongo no es monótono; Postgres sí (creciente en throughput, decreciente en p50) pero con **+7.9 % de r1 a r3**, por debajo del umbral del 10 %. Queda anotado para vigilarlo en F8
- [x] Planes de ejecución capturados para esa celda (R-31). — `results/f7/explains/` (uno por celda, en la repetición 1, como diseñó F5)
- [x] Tiempo real medido de una celda → estimación fundamentada del costo total de F8. — **448.5 s por repetición** → 13.5 h la tanda 1 (108 corridas) y **20.2 h** la matriz completa (162). El PLAN estimaba ~19 h contando solo las ventanas
- [x] **Primera consulta en frío frente al calentamiento** (pedido por Alix al cerrar F5; **ampliado a los tres perfiles** el 2026-11-01, al aprobar F6): medir cuánto tarda la primera consulta en frío en **PROFILE_A, PROFILE_B y PROFILE_C** y compararla con los 60 s de calentamiento del manual. Motivo de la ampliación: en el humo de F5.5 la primera tanda de Q1 de Mongo con c=50 tardó ~74 s ya en PROFILE_A, el perfil con más recursos. Si no cabe, las celdas de ese perfil salen con P95 y P99 contaminados por la consulta en frío. Es una **limitación del protocolo que se declara en el reporte**, no un error del runner. Origen: F5.5b, donde el calentamiento de humo (30.3 s) quedó al filo de la primera consulta (27–35 s) y partió el p95 en dos. — **Medido en F7.3** (`results/f7_frio/check_cold.json`, 18 celdas con c=50): **no cabe en 14 de 18**. Solo cabe en PROFILE_A con Q2 (39–52 s); en Postgres B son 69–75 s, en Postgres C 109–110 s, en Mongo A con Q1 102 s, y en 8 celdas **ninguna consulta terminó en 110 s**. Con c=1 (el piloto) sí cabe: Mongo 27–33 s y Postgres 3–4 s. **Contaminación medida:** hasta el **91 %** de la ventana son primeras consultas (Postgres C Q2_MEM_HIGH) y el p95 baja hasta un **61 %** al quitarlas. Se declara como limitación del protocolo y se muestran las dos vistas, también en la figura (F7-e, R-30.1).

**Esta es la última puerta antes del gasto grande.**


### Estado de F7 al 2026-11-02: CERRADA

Cierre aprobado por Alix. Plan, decisiones F7-a…F7-e y registro completo en `docs/F7_PILOTO.md`.

- **Piloto real** (Mongo y Postgres × PROFILE_C × Q2_MEM_LOW × c=1, ventanas 60/300/60, 3 repeticiones): CSV válido y los 8 criterios del analizador cumplidos. **CV 4.2 % y 3.8 %**, sin tendencia.
- **El entorno es estable: se puede ir a F8.** Costo medido: 448.5 s por repetición → 13.5 h la tanda 1 y 20.2 h la matriz completa.
- **El calentamiento de 60 s del manual no alcanza con c=50** en B y C (F7.3). Limitación del protocolo declarada, con las dos vistas en el texto y en la figura (R-30.1).
- **Q1 con c=50 es casi inmedible en este hardware:** 92 % de timeouts en A, OOM en C, ninguna consulta terminada en B. Son resultados, no fallos.
- **Primera evidencia de OOM y de spill en queries del manual** (no en sondas): Postgres × C × Q1 × c=50 → OOM (`oom_kill +3`); Postgres × A × Q1 × c=50 → `temp_bytes` +37.2 GB. Responden M2 con datos.
- **Memoria (F7.4):** aguanta con 3.2 GiB libres en el peor caso y sin swap, pero la VM pasó 120 de 300 s en espera por memoria. El monitoreo cuesta < 0.09 núcleos.
- **Cambios aprobados y aplicados:** pausa de 1 s tras un fallo (F8-a; 455 504 reintentos en 110 s eran CPU del runner compitiendo con el motor), recuento del dataset tras cada OOM con parada si no son 500 000 filas (R-08), y la regla de sudoers de V7 instalada (`docs/V7_SUDOERS.md`, reversible con un script).
- **`scripts/run_benchmarks.sh`** (R-25) listo y probado en humo con motores reales: reanudable desde el CSV, parametrizable para 36 o 54 celdas, por bloques, y con la comprobación de sudo antes de cada celda.
- **Pruebas:** 285/285 (`results/f7/tests_f8a_v7_20261102T144532Z.txt`).

---

## F8 — Matriz completa

**Depende de:** F7 y de la respuesta a A2.

**Trabajo.** `run_benchmarks.sh` recorre la matriz; reanudable (si se corta, continúa donde quedó, consultando el CSV existente); captura de planes por celda durante el cooldown.

**Criterios de aceptación.**
- [ ] Número de filas = celdas × 3, con el conteo acordado en A2 (108 o 162).
- [ ] Ninguna combinación falta ni está duplicada (verificación por clave compuesta).
- [ ] Todas las filas pasan `validate_csv.py`.
- [ ] Las celdas con `status=error` tienen su log correlacionado en `results/logs/`.
- [ ] Evidencia de que el flush de caché se ejecutó en cada repetición.

**Recomendación operativa.** Correr por bloques (un motor y un perfil por sesión), no 19 h seguidas, y no usar la máquina para nada más mientras corre.

---

## F9 — Reporte de métricas

**Depende de:** F8.

**Trabajo.** Las 7 secciones de playbook.pdf §8.3, las 3 figuras obligatorias y la trazabilidad a las 6 preguntas del revisor (diapo 11/13).

**Criterios de aceptación.**
- [ ] Las 7 secciones existen y ninguna está vacía.
- [ ] Figuras: P99 vs concurrencia, throttling vs QPS, curva RSS.
- [ ] Cada una de las 6 preguntas del revisor tiene una tabla o figura que la responde, referenciada en el CHECKLIST.
- [ ] Cada número del reporte es trazable a una fila del CSV o a un archivo de `results/`. **Ningún valor escrito a mano.**
- [ ] M1, M2 y M3 respondidas explícitamente con datos.
- [ ] Las decisiones de SPEC §5 aparecen declaradas en la sección 2 (método), no escondidas.

---

## Registro de riesgos

| # | Riesgo | Prob. | Impacto | Mitigación |
|---|--------|-------|---------|------------|
| R1 | 19–30 h de ejecución no caben en el calendario | Alta | Crítico | Resolver A2 en F0; ejecutar por bloques; runner reanudable desde F5 |
| R2 | PROFILE_A no es baseline real por falta de núcleos en el host | Media | Alto | Verificar en F0; si no alcanza, declararlo en el reporte en vez de fingirlo |
| R3 | Pocas queries completadas en celdas severas → percentiles sin sentido | Alta | Alto | Política A4 definida en F0; marcar baja densidad muestral |
| R4 | `final_total` como string rompe el orden en Mongo | Media | Crítico | Prueba de equivalencia en F4 antes de cargar 500 k |
| R5 | El índice de expresión en Postgres no se crea, o se crea y el planner no lo usa por baja selectividad | Alta | Medio | Resuelto empíricamente en F3-G1; opción (1) de SPEC A3.2 como ruta segura |
| R13 | La premisa de estrés de buffer no se materializa: el top-K evita spill y OOM, y las dos variantes de Q2 dan lo mismo | **Alta** | Medio | SPEC A12; separar sondas de resultados en F6; reportar la ausencia de spill como hallazgo, no como fallo |
| R14 | Mongo usa su índice de timestamp y Postgres no: la diferencia de latencia mide planes distintos, no motores | Media | Alto | Capturar ambos planes en F3-G2 y G3; declararlo en la sección 5 del reporte |
| R15 | **Confirmado:** Docker corre sobre WSL2. `drop_caches` no alcanza el caché de Windows sobre el `.vhdx` y cAdvisor observa la VM, no el equipo | **Cierta** | Alto | Declarado en SPEC §6 (L1–L7) y en la sección 1 del reporte. Lo alcanzable es un estado repetible, no un caché frío perfecto |
| R16 | Solo 7.159 GiB para la VM: PROFILE_A deja ~2.2 GiB para runner, telemetría y caché de páginas | Alta | Alto | D-WSL1 decidida: se conserva la VM tal cual y PROFILE_A se declara baseline con holgura limitada. Se revisa si el CV de la celda piloto supera 15 % |
| R17 | 4.0 CPUs de PROFILE_A pueden caer en hilos hermanos del mismo núcleo físico (SMT) y rendir menos que 4 núcleos reales | Alta | Medio | Declarar L2; considerar `cpuset` sobre lógicas no hermanas si el ruido lo justifica |
| R18 | El proyecto o los volúmenes terminan en `/mnt/c/` y el I/O se degrada por la capa de traducción | Media | **Crítico** | Verificación V3 antes de F1; comprobar también la ruta de los volúmenes de Docker |
| R19 | El runner compite con el motor por las mismas CPUs de la VM: no hay aislamiento real | Cierta | Alto | `cpuset` separado; registrar `loadavg` por corrida; declarar L5 |
| R6 | El límite de CPU no se aplica (cgroups v1, Docker Desktop, VM) | Baja | Crítico | Prueba positiva de throttling en F6 |
| R7 | El swap enmascara el OOM | Media | Alto | `memory-swap = memory`, verificado en F1 |
| R8 | El runner le roba CPU al motor y contamina las métricas | Media | Alto | `cpuset` separado; documentar en sección 1 del reporte |
| R9 | Ruido del host (navegador, actualizaciones) entre repeticiones | Alta | Medio | Umbral de CV < 15 % en F7; registrar `loadavg` por corrida |
| R10 | `drop_caches` sin sudo falla en silencio | Media | Medio | Verificar código de salida y abortar la corrida si falla |
| R11 | Pérdida de resultados por corte de ejecución | Media | Alto | Escribir CSV por repetición, no al final |
| R12 | Agregar una columna al CSV "por comodidad" | Media | Alto | Prueba automatizada que falla ante cualquier cambio de encabezado |

---

## Estrategia de pruebas piloto

Escalada en cuatro niveles. Cada uno es barato comparado con el siguiente y atrapa una clase distinta de error.

**P0 — 1 000 registros, sin Docker (segundos).**
Pruebas unitarias puras: esquema del generador, determinismo con semilla, cálculo de percentiles, encabezado del CSV, dominios de `status`. Atrapa errores de contrato.

**P0.5 — 1 000 registros cargados en ambos motores (segundos).**
Compuerta G1 de F3. Valida que el esquema sobrevive al viaje de ida y vuelta por cada motor: tipos conservados, anidamiento intacto, `final_total` numérico leído desde el motor y no desde el archivo. Atrapa errores de carga e importación.

**P1 — 10 000 registros, ambos motores sin límites (minutos).**
Equivalencia de resultados Q1 y Q2 (F4). Atrapa los errores que invalidan la comparación: tipos mal elegidos, orden lexicográfico, `final_total` en el lugar equivocado, queries alteradas sin querer. **Es la prueba más valiosa del proyecto**: ejecutarla contra 10 k cuesta minutos; descubrir el mismo error tras cargar 500 k y correr 12 h cuesta el proyecto.

**P2 — 500 000 registros, celda en modo `--smoke` (minutos).**
Tiempos reducidos (5/20/5 s), una celda por motor en PROFILE_C. Verifica que el pipeline completo funciona a escala real: carga, límites, telemetría, detección de spill, escritura del CSV. No produce números publicables y se marca como descartable.

**P3 — Celda piloto formal (≈21 min por motor).**
La de F7, con tiempos reales y 3 repeticiones. Verifica estabilidad (CV < 15 %) y da la estimación de costo de la matriz. Sus filas **sí** entran al CSV final.

**Sondas de capacidad de detección** (obligatorias; son lo que demuestra que el instrumento mide, y **no** son resultados del benchmark):
1. Forzar throttling en PROFILE_C y verlo distinto de cero.
2. Forzar spill en Postgres con un sort sin `LIMIT` y detectarlo.
3. Forzar spill en Mongo con un `$sort` sin `$limit` y detectarlo.
4. Forzar OOM contra `memory.max` y clasificarlo como `status=oom`.
5. Meter una columna extra al CSV a propósito y comprobar que el validador falla.

Las sondas 2, 3 y 4 usan consultas que **no** son Q1 ni Q2 y que viven fuera de `queries/`. Confundirlas con resultados sería inventar evidencia; en el reporte van en la sección 2 (método), etiquetadas como verificación de instrumento.

**Equivalencia en el tiempo.** La comparación de resultados de P1 se re-ejecuta sobre el dataset de 500 k una sola vez (compuerta G3, fuera de ventana medida), porque una equivalencia verificada solo en 10 k podría romperse por valores extremos que únicamente aparecen a escala.
