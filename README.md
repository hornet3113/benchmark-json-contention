# Benchmark MongoDB vs PostgreSQL JSONB bajo contención de CPU y memoria

Materia: Bases de Datos en la Nube · IT2iD · Universidad Politécnica de Chiapas · 2026

## 1. Qué es el proyecto

Se comparan **MongoDB 8.2.12** (motor wiredTiger) y **PostgreSQL 18.6** (columna
`jsonb`) ejecutando las dos agregaciones del manual sobre JSON anidado: **Q1**,
que despliega el arreglo de artículos de cada pedido y agrupa por país y
categoría, y **Q2**, que filtra por fecha, ordena por importe y se queda con el
Top-1000. Las dos corren sobre el **mismo dataset de 500 000 pedidos sintéticos**
(semilla 42), cargado en los dos motores y verificado idéntico a la fuente.
Cada motor se encierra en un contenedor con límites reales de cgroups v2 en
**tres perfiles** —A: 4 CPU y 4 GiB · B: 2 CPU y 2 GiB · C: 1 CPU y 1 GiB— y se
ataca con **tres concurrencias** (1, 10 y 50 clientes). Cada combinación se
repite **3 veces**, y cada repetición limpia la caché del sistema, calienta 60 s,
mide 300 s y enfría 60 s. Son **36 celdas y 108 corridas**, una fila de CSV por
corrida, más **18 corridas de anexo** para la segunda variante de memoria de Q2.

## 2. Entregables

Cada exigencia del manual con el archivo que la cumple.

| Exigencia del manual | Dónde está | Cobertura |
|---|---|---|
| §8.1 `docker-compose.yml` parametrizado por perfiles | [docker/docker-compose.yml](docker/docker-compose.yml), con los límites en [docker/profiles/a_baseline.env](docker/profiles/a_baseline.env), [b_medium.env](docker/profiles/b_medium.env) y [c_severe.env](docker/profiles/c_severe.env), e imágenes fijadas por digest en [docker/images.env](docker/images.env) | Completa |
| §8.1 `synthetic_data_generator.py` | [generator/synthetic_data_generator.py](generator/synthetic_data_generator.py), con [generator/schema.py](generator/schema.py) y [generator/distributions.py](generator/distributions.py) | Completa |
| §8.1 Benchmark runner | [benchmark_runner/](benchmark_runner/) — Python multiproceso, de las dos opciones que admite el manual | Completa |
| §8.1 `queries/` con las consultas copiadas literalmente del manual | 4 archivos, Q1 y Q2 en cada motor: [queries/mongo/q1_unwind_group.json](queries/mongo/q1_unwind_group.json), [queries/postgres/q1_unwind_group.sql](queries/postgres/q1_unwind_group.sql), [queries/mongo/q2_sort_topk.json](queries/mongo/q2_sort_topk.json), [queries/postgres/q2_sort_topk.sql](queries/postgres/q2_sort_topk.sql). No se teclearon: los recorta del PDF [scripts/extract_queries.py](scripts/extract_queries.py), y sus SHA-256 están en [queries/README.md](queries/README.md) | Completa |
| §8.1 `run_benchmarks.sh` | [scripts/run_benchmarks.sh](scripts/run_benchmarks.sh) — recorre la matriz y es reanudable desde el CSV | Completa |
| §8.2 CSV de 14 columnas | [results/measurements.csv](results/measurements.csv) — **14 columnas y 108 filas**, encabezado comprobado byte a byte por [scripts/validate_csv.py](scripts/validate_csv.py) | Completa |
| §8.3 Reporte de métricas con sus 7 secciones | [report/reporte.pdf](report/reporte.pdf) (18 páginas); fuente en [report/reporte.tex](report/reporte.tex) y una sección por archivo en [report/secciones/](report/secciones/) | Completa |
| R-30 Las tres figuras | [report/figuras/p99-concurrencia.tex](report/figuras/p99-concurrencia.tex) (P99 vs concurrencia), [throttling-qps.tex](report/figuras/throttling-qps.tex) (throttling vs throughput) y [curva-rss.tex](report/figuras/curva-rss.tex) (curva de memoria). Las dibuja LaTeX leyendo [report/datos/](report/datos/), así que cada punto es rastreable; hay un cuarto archivo, [p99-concurrencia-q1.tex](report/figuras/p99-concurrencia-q1.tex), que es el panel de Q1 de la primera figura | Completa |
| R-31 Los 12 planes de ejecución | [results/explains/](results/explains/) — 12 archivos JSON, uno por motor × perfil × query, tomados en las celdas de concurrencia 1 | Completa |
| R-32 Logs de spill y OOM | [results/logs/](results/logs/) — un archivo por repetición afectada (**30 de las 108 filas**), cada uno correlacionado con su fila del CSV; índice en [results/logs/README.md](results/logs/README.md) | Completa |

### Cobertura parcial, dicha sin rodeos

**1. Las dos variantes de memoria de Q2 (R-16 a R-18) — parcial, y a propósito.**
El manual pide ejecutar Q2 con dos configuraciones de memoria (`work_mem` 4 MB y
64 MB en PostgreSQL; `allowDiskUse` falso y verdadero en MongoDB), pero el
esquema de CSV que el mismo manual fija **no tiene ninguna columna donde
distinguir la variante**, y añadir columnas está prohibido explícitamente. Las
dos exigencias no caben juntas. El CSV de las 36 celdas lleva la variante
**restrictiva**, y la permisiva se midió **en anexo**, solo en el perfil C, el de
menos memoria: 6 celdas y 18 repeticiones en
[results/f8_anexo/measurements.csv](results/f8_anexo/measurements.csv), validado
con el mismo esquema de 14 columnas. **No se midió en los perfiles A ni B.** El
razonamiento y el resultado están en
[report/secciones/A1-anexo-variantes.tex](report/secciones/A1-anexo-variantes.tex).

**2. El índice de Q2 en PostgreSQL existe pero el planner no lo usa (R-04) — no
se cumple.** El índice B-Tree sobre el `timestamp` extraído está creado
([docker/postgres/indexes.sql](docker/postgres/indexes.sql)), pero el `EXPLAIN`
de Q2 muestra `Seq Scan`: con la selectividad de ese filtro, el planner prefiere
recorrer la tabla. Cumplirlo exigiría modificar el texto de Q2, que se copia
literal del manual. Se reporta como está, con el plan a la vista en
[results/explains/](results/explains/) y la asimetría frente a MongoDB —que sí
usa su índice— analizada en la sección 5 del reporte.

**3. El calentamiento de 60 s del manual no alcanza con 50 clientes.** Se midió
una por una la primera consulta de cada cliente: con c=50 **no cabe en los 60 s
en 14 de las 18 combinaciones**, y el P95 baja hasta un 61 % al quitarla. No se
cambió el protocolo del manual; se declara, y la figura de P99 lleva **dos
vistas** —con y sin la primera consulta— en vez de una nota al pie. Evidencia en
[results/f7_frio/](results/f7_frio/).

**4. Doce de las 108 filas no traen métricas completas**, porque el motor no
terminó la ventana: 7 con `status` `error` (consultas censuradas por timeout) y
5 con `oom`. Son **resultados**, no fallos del instrumento, y responden la
pregunta del manual sobre límites de memoria. Las columnas que no se midieron
van **vacías**, nunca con un 0 inventado, y cada una tiene su log en
[results/logs/](results/logs/).

**5. La evidencia de la validación inicial del entorno es una transcripción de
pantalla**, no salida capturada de los comandos
([results/env/f0/F0_salidas_observadas.md](results/env/f0/F0_salidas_observadas.md)).
Todo lo que vino después sí se capturó a archivo. Y la ruta de respaldo para
limpiar la caché (un contenedor privilegiado) está documentada pero **no se
ejecutó**, porque no hizo falta.

## 3. Cómo reproducirlo

Los tiempos son los que se midieron en este equipo.

**0. Prerrequisitos.** Windows 11 con WSL2 (distribución Ubuntu) y Docker
Desktop con la integración de WSL2 activada; Python 3.14 con `venv`;
`poppler-utils` (para recortar las consultas del PDF); y, solo si se quiere
compilar el reporte, TeX Live con `pgfplots` y `siunitx`. Hace falta **`sudo`**
en un paso: limpiar la caché de páginas entre repeticiones.

**1. Clonar dentro de WSL2** — *segundos.* Tiene que quedar en el sistema de
archivos de Linux, por ejemplo `~/benchmark-json-contention`, **nunca bajo
`/mnt/c/`** (el motivo está en la sección 4).

```bash
cd ~ && git clone <url-del-repo> benchmark-json-contention
cd ~/benchmark-json-contention && chmod +x scripts/*.sh
```

**2. Entorno de Python y drivers** — *~1 min.* Las versiones son exactas a
propósito.

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
```

**3. Descargar las imágenes, fijadas por digest** — *unos minutos, según la red.*

```bash
(set -a; source docker/images.env; docker pull "$MONGO_IMAGE" && docker pull "$PG_IMAGE")
```

**4. Comprobar que los límites se aplican de verdad** — *~1 min por perfil.* Lee
el cgroup desde dentro del contenedor y lo compara con lo que pide el manual.

```bash
scripts/up_profile.sh a_baseline mongo
scripts/verify_limits.sh a_baseline mongo
scripts/down_profile.sh
```

**5. Generar el dataset** — *3 min 22 s.* Escribe 500 000 pedidos (479 MiB) y
sus estadísticas, incluido el SHA-256.

```bash
.venv/bin/python generator/synthetic_data_generator.py --size 500000
```

**6. Cargar en los dos motores y verificar la equivalencia** — *~15 min.* Levanta
un motor a la vez, carga por entrada estándar, crea los índices, compara los
datos en tres direcciones y comprueba que Q1 y Q2 dan el mismo resultado que una
referencia exacta calculada en Python.

```bash
scripts/run_gate.sh g3
```

La carga en sí: MongoDB 68.9 s más 5.0 s de índices; PostgreSQL 42.2 s más 7.4 s
de índices y 6.1 s de `VACUUM ANALYZE`. **Este paso es destructivo**: recrea la
colección y la tabla.

En la corrida registrada el reloj de pared marcó 68 min, no 15: el equipo se
suspendió durante la comparación de datos. Ese paso solo lee archivos ya
exportados y no mide nada, así que no afectó a ningún resultado, pero da la
medida de por qué el equipo no debe suspenderse en el paso 8, que sí mide.

**7. Levantar el monitoreo** — *~30 s.* Prometheus, cAdvisor y node_exporter en
un proyecto de Compose aparte, atados a las CPUs 8–11 para no competir con el
motor. Cuesta menos de 0.1 núcleos bajo carga.

```bash
scripts/up_monitoring.sh
```

**8. Correr la matriz** — *13.4 h*, a 448 s por repetición. Conviene hacerlo por
bloques y con el equipo conectado a la corriente y sin suspensión: si la máquina
se suspende a mitad de una ventana, esa repetición queda inservible.

```bash
scripts/run_benchmarks.sh --listar --matriz 36 --q2-variante MEM_LOW   # qué falta, sin correr nada
scripts/run_benchmarks.sh --humo                                       # prueba de 2 celdas, ventanas cortas
sudo -v
scripts/run_benchmarks.sh --matriz 36 --q2-variante MEM_LOW            # las 108 corridas
scripts/run_benchmarks.sh --matriz 36 --q2-variante MEM_LOW --concurrencia 1   # o un bloque a la vez
```

Es **reanudable**: antes de cada celda mira qué repeticiones ya tienen fila en el
CSV y corre solo las que faltan. Si se corta la sesión, se vuelve a lanzar el
mismo comando. **Esto hay que esperarlo y no confundirlo con un fallo:** Q1 con
50 clientes da timeouts, y en el perfil C hay OOM; salen como filas `error` y
`oom`.

**9. El anexo de la segunda variante de Q2** — *~2 h 15 min*, 18 corridas.

```bash
scripts/run_benchmarks.sh --todo --query Q2_MEM_HIGH --perfil PROFILE_C_SEVERE --salida f8_anexo
```

**10. Validar el CSV, armar los logs y el reporte** — *~3 min.*

```bash
.venv/bin/python scripts/validate_csv.py results/measurements.csv --matrix 36 --expect-rows 108
.venv/bin/python scripts/build_logs_f8c.py        # escribe results/logs/
.venv/bin/python scripts/build_report_data.py     # escribe report/datos/, tablas/ y cifras/
cd report && latexmk -pdf reporte.tex
```

Ningún número del reporte está escrito a mano: el texto de LaTeX no contiene
cifras, las lee de los archivos que genera `build_report_data.py` a partir del
CSV y de `results/raw/`.

**La batería de pruebas** se corre en cualquier momento y no toca los motores:

```bash
.venv/bin/python -m unittest discover -s tests -v    # 302 pruebas
```

## 4. Entorno y limitaciones

Todo se midió sobre **Windows 11 + WSL2 (Ubuntu) + Docker Desktop**, en un
**AMD Ryzen 5 PRO 5675U** de 6 núcleos físicos y 12 lógicos con 14.8 GiB de RAM.
La VM de WSL2 ve 12 CPUs y 7.159 GiB. El motor medido corre fijado a las CPUs
0–7; el runner y el monitoreo, a las 8–11, para que el generador de carga no le
robe tiempo al motor que está midiendo.

**Los valores absolutos dependen del equipo y de la capa de virtualización.**
Otro equipo, y sobre todo Linux nativo sin la VM de WSL2 en medio, dará números
distintos: otra latencia, otro throughput, otros segundos de throttling. **Lo
reproducible aquí es el procedimiento, el esquema del CSV y qué celdas quedan
marcadas** con `spill`, `error` u `oom`, no las cifras. Las comparaciones que el
reporte sostiene son entre motores y entre perfiles **dentro de esta misma
máquina**, que es donde la comparación es válida.

**El repositorio tiene que vivir dentro del sistema de archivos de WSL2** (por
ejemplo `~/benchmark-json-contention`) y **nunca bajo `/mnt/c/`**. Esa ruta no es
un disco de Linux: es el disco de Windows visto a través de un protocolo de red
(9p), con una capa de traducción en cada operación de archivo. Un dataset de
479 MiB y las lecturas del motor pasarían por ahí, y lo que se mediría ya no
sería el motor sino el puente entre los dos sistemas de archivos. En este mismo
proyecto esa capa dio problemas reales: el colector de sistemas de archivos del
monitoreo terminó muerto por falta de memoria al recorrer los montajes 9p.

Otras limitaciones del entorno virtualizado están en la sección 1 del reporte y
en [SPEC.md](SPEC.md) §6; no están escondidas en notas al pie. Las principales:
el perfil A es un baseline con holgura limitada, porque la VM tiene 7.159 GiB y
el contenedor de ese perfil ya pide 4; la caché de páginas de Windows sobre el
disco virtual queda fuera de alcance, así que lo alcanzable es un estado
repetible entre repeticiones, no una caché fría absoluta; y `cpu_throttled_seconds`
puede superar la duración de la ventana, porque el kernel suma el throttling de
cada CPU por separado.

## 5. Dónde está la evidencia

| Carpeta | Qué contiene y qué se puede comprobar con ella |
|---|---|
| [results/measurements.csv](results/measurements.csv) | El entregable: 108 filas, 14 columnas. Es la fuente de todo número del reporte |
| [results/raw/](results/raw/) | 108 archivos, uno por repetición: **cada latencia individual** con el cliente que la produjo, la serie del cgroup muestreada cada segundo, la fracción de timeouts y qué percentiles son válidos. Permite **recalcular los percentiles** sin volver a medir |
| [results/telemetry/](results/telemetry/) | 108 archivos con las curvas de Prometheus de cada repetición, en muestras crudas |
| [results/logs/](results/logs/) | Los 30 casos de spill, error y OOM explicados uno a uno, cada uno apuntando a su fila del CSV y a su crudo (R-32) |
| [results/explains/](results/explains/) | Los 12 planes de ejecución (R-31), más los de las compuertas de carga en `g2/` y `g3/` |
| [results/env/](results/env/) | Límites leídos del cgroup, versiones y digests de las imágenes y datos del host, capturados por corrida. Aquí se comprueba que los límites del manual se aplicaron de verdad |
| [results/dataset_stats.json](results/dataset_stats.json) | SHA-256 del dataset y sus distribuciones reales, contra las que se pueden verificar las metas del manual |
| [results/f2/](results/f2/), [f3/](results/f3/) | Determinismo del generador, y la carga con la comparación en tres direcciones y la equivalencia de Q1 y Q2 |
| [results/f5/](results/f5/), [smoke/](results/smoke/) | Pruebas de humo del runner y la decisión de cómo se reparten 50 clientes en procesos e hilos |
| [results/f6/](results/f6/) | Verificación del instrumento: qué mide cada contador, y las cuatro sondas que provocan throttling, spill y OOM a propósito para comprobar que los detectores los ven. **No producen filas del CSV**: mezclarlas con los resultados sería fabricar evidencia |
| [results/f7/](results/f7/), [f7_frio/](results/f7_frio/), [f7_memoria/](results/f7_memoria/) | La celda piloto que mostró que el entorno es estable (variación del throughput del 4 %), la medición de la primera consulta en frío y la de memoria disponible |
| [results/f8/](results/f8/), [f8_anexo/](results/f8_anexo/), [f8_humo/](results/f8_humo/) | Registros de las pruebas por bloque de la matriz, y el anexo de la segunda variante de Q2 |

**El dataset de 500 000 documentos no se versiona**, porque son 479 MiB. Se
regenera **byte a byte** con la semilla 42 y el comando del paso 5, y su
**SHA-256 es `0cd7fadb084627679ab2437921ef1889a012e1fa5b0898d2624760be41060414`**,
registrado en [results/dataset_stats.json](results/dataset_stats.json) junto con
el tamaño exacto (501 751 458 bytes). El cargador comprueba ese hash antes de
cargar: si el archivo no es el mismo, se detiene.

## 6. Estructura del repositorio

```
.
├── docker/              compose, imágenes por digest, perfiles de recursos, init e índices
├── generator/           generador del dataset y el contrato del registro
├── queries/             las 4 consultas, recortadas del PDF del manual
├── benchmark_runner/    el runner: matriz, carga, métricas, telemetría, escritura del CSV
├── scripts/             carga, compuertas, verificaciones, la matriz y las utilidades
│   ├── checks/          comprobaciones del entorno y del monitoreo
│   └── probes/          sondas que fuerzan spill y OOM (no producen filas del CSV)
├── monitoring/          Prometheus, cAdvisor y node_exporter, proyecto de Compose aparte
├── tests/              302 pruebas automatizadas
├── results/             toda la evidencia (ver sección 5)
├── report/              el reporte en LaTeX y su PDF
├── docs/                el manual del proyecto y el registro de cada fase
├── data/                el dataset generado (no versionado)
├── SPEC.md              requisitos del manual con página, arquitectura, ambigüedades y decisiones
├── PLAN.md              fases, criterios de aceptación y registro de ejecución
└── CHECKLIST.md         verificación de entrega
```
