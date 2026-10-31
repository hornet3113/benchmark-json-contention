# F2 — Generador de dataset (CERRADA el 2026-11-01)

**Estado: cerrada.** F2.1, F2.2 y F2.3 se hicieron el 2026-11-01, y todos los
criterios de abajo tienen evidencia en `results/` o en `tests/`. Alix revisó
los resultados (incluido el cruce 69.97 % × 50.04 % = 35.01 % = filas del
filtro de Q2) y aprobó el cierre. PLAN.md, CLAUDE.md y CHECKLIST.md ya están
actualizados. Esta fase no
se declara completa hasta que cada criterio de abajo tenga una prueba o un
archivo en `results/` detrás.

Qué cubre F2: generar los registros sintéticos que piden playbook.pdf §4 y las
queries de §5, de forma determinista. No incluye cargarlos en los motores:
eso es F3.

---

## Lo que exige el manual (playbook.pdf §4, pp.1–2)

> 500 000 registros · formato JSON · 3 niveles de anidamiento · promedio 3 ítems por registro.
>
> `order_id` (UUID), `timestamp` (ISO-8601) · `customer` (objeto: id, tier,
> segment, geo[country, state, city, zip, coordinates]) · `items` (arreglo de
> objetos: sku, category, brand, qty, price, tax_pct, discounts) · `payment`
> (objeto: method, status, transaction_id, gateway_latency_ms, totals) ·
> `metadata` (objeto: channel, user_agent, session_id, flags)

Y el dataset tiene que servir para que Q1 y Q2 (§5) corran **tal como están
escritas**.

Nota de trazabilidad: el texto del PDF se extrajo con un script de biblioteca
estándar (no hay `pdftotext` ni `pypdf` instalados). El texto es legible,
aunque sin espacios.

---

## Decisiones aprobadas (2026-11-01)

| # | Ambigüedad | Decisión |
|---|---|---|
| F2-a | ¿Qué cuenta como "3 niveles"? | Raíz = nivel 0. `customer`(1) → `geo`(2) → `coordinates`(3), e `items`(1) → ítem(2) → `discounts`(3). **Profundidad máxima = 3**, comprobada por programa en cada registro |
| F2-b | Forma de `discounts` y `flags` | `discounts`: lista de 0–2 porcentajes (números). Si fueran objetos, la profundidad pasaría a 4. `flags`: lista de textos |
| F2-c | `geo[…]` con corchetes en el manual | **Objeto**: Q1 usa `$customer.geo.country` y `->'geo'->>'country'`, que solo funcionan con un objeto |
| F2-d | Cómo se calcula `final_total` | `subtotal = Σ qty·price`; `discount = Σ qty·price·Σdiscounts/100`; `tax` sobre el importe ya descontado; `final_total = subtotal + tax − discount`. Hermano de `totals` (A1), número JSON, 2 decimales |
| F2-e | Distribución de `price` | Uniforme en centavos entre 1.00 y 90.00 → P(price>50) = 4000/8901 ≈ 44.94 % (meta A8: ≈45 %) |
| F2-f | Ítems "promedio 3" | 1–6 ítems con pesos de media exacta 3.00 |
| Tolerancia | Metas de A8 sobre 500 000 | ±1 punto porcentual |

Ya decidido en SPEC A8: timestamps uniformes entre 2025-01-01 y 2026-12-31
(≈50 % en 2026 o después), 70 % `completed`, 12 países × 20 categorías,
semilla 42.

### Adición de Alix: `order_id` = `id` de PostgreSQL (SPEC §2)

| Quién | Qué garantiza | Cómo se comprueba |
|---|---|---|
| Generador (F2) | `order_id` en forma **canónica** (minúsculas, `8-4-4-4-12`), igual a como Postgres convierte un `uuid` a texto, y **único** en el dataset | `str(UUID(x)) == x` en las pruebas; conteo de duplicados en las estadísticas |
| Carga (F3) | `id = (data->>'order_id')::uuid`: el `id` sale del propio documento, no se genera aparte | G1: `SELECT count(*) FROM orders WHERE id::text <> data->>'order_id'` = 0 |

Por qué importa la forma canónica: con mayúsculas, Postgres aceptaría el UUID,
pero `id::text` saldría en minúsculas y no coincidiría con `order_id`. El cruce
documento a documento de F4 fallaría en silencio.

---

## Trampas que el manual no menciona

1. **Formato de `timestamp`.** Mongo compara `{"$gte": "2026-01-01T00:00:00Z"}`
   como **texto**; Postgres lo convierte a `timestamptz`. Solo coinciden si el
   orden alfabético es igual al cronológico. Por eso el formato es fijo:
   `YYYY-MM-DDTHH:MM:SSZ`, UTC con `Z` y **sin fracciones de segundo**.
   Contraejemplo: `"…00:00:00.5Z"` es posterior a `"…00:00:00Z"` pero va antes
   alfabéticamente (`.` < `Z`).
2. **Empate en la posición 1000 de Q2.** Si el registro 1000 y el 1001 tienen
   el mismo `final_total`, cada motor puede devolver uno distinto y la
   comparación como conjunto de F4 falla sin que haya error. El generador lo
   **detecta y lo informa** en las estadísticas; no lo oculta.
3. **UUID con semilla.** `uuid4()` usa azar del sistema y rompería el
   determinismo. Se usa `UUID(int=rng.getrandbits(128), version=4)`.
4. **Textos seguros para `COPY`.** Ningún texto lleva `\`, tabuladores, saltos
   de línea ni caracteres de control. Los catálogos son ASCII.
5. **Importes en centavos enteros.** Los cálculos se hacen con enteros y solo
   al final se dividen entre 100. Así `final_total` es exactamente
   `subtotal + tax − discount`, sin errores de redondeo de punto flotante.

---

## Reproducibilidad

- Un solo generador pseudoaleatorio (`random.Random(42)`), recorrido en orden.
  Consecuencia: **el archivo de 1 000 registros es exactamente el inicio del
  de 500 000**, así que lo validado en G1/G2 es parte literal de lo cargado en G3.
- Orden de claves, separadores y formato numérico fijos al serializar, para
  que la misma semilla dé el mismo SHA-256.
- El hash es reproducible con la misma versión de Python. Aquí: 3.14.4; se
  anota en las estadísticas.

---

## Fases

| Paso | Qué se hace | Cómo se verifica |
|---|---|---|
| **F2.1** | `generator/schema.py` (contrato y validador), `generator/distributions.py` (catálogos, pesos, semilla) y `make_record()` en `generator/synthetic_data_generator.py` | Pruebas unitarias: atributos, tipos, profundidad = 3, formato de `timestamp`, `order_id` canónico, `final_total` numérico y consistente; el validador rechaza los casos malos |
| **F2.2** | CLI `--size 1000\|10000\|500000`, escritura JSONL en streaming y estadísticas | Esquema al 100 % en 1 000; misma semilla → mismo hash; el archivo de 1 000 es el inicio del de 10 000 |
| **F2.3** | Generar 10 000 y 500 000 | `wc -l`, hash, tiempo y tamaño **medidos**; metas A8 dentro de ±1 punto; empate en el Top-1000 informado; `order_id` sin duplicados |

**Salidas:** `data/orders_<tamaño>_seed42.jsonl` (no se versiona: `*.jsonl`
está en `.gitignore`); `results/dataset_stats.json` para 500 000 (PLAN F2);
estadísticas de 1 000 y 10 000 en `results/f2/`.

Solo biblioteca estándar: F2 no requiere instalar nada.

---

## Criterios para dar F2 por completada

PLAN F2:

- [x] 500 000 registros generados; `wc -l` lo confirma — `results/f2/F2_3_20261101T181011Z_verificacion.txt` §2
- [x] Esquema (R-10) validado en una muestra de 1 000, con 3 niveles verificados por programa — `results/f2/F2_2_20261101T180005Z.txt` §5, leído de disco
- [x] Media de ítems por registro en [2.9, 3.1] — 2.9991 en 500 000 (verificación §3)
- [x] Dos ejecuciones con la misma semilla → mismo SHA-256 — dos procesos con `--size 1000` dan `fd0b00da…b64c` según `sha256sum` (mismo log, §4)
- [x] `final_total` es número en el 100 % de la muestra — 0 de 1 000 no numéricos (mismo log, §5)
- [x] `results/dataset_stats.json` con % `completed`, % `price>50`, cardinalidad país × categoría y rango de timestamps

Añadidos en este plan:

- [x] `timestamp` con formato estricto en el 100 % — 0 fuera de formato de 500 000
- [x] `order_id` canónico en el 100 % y sin duplicados — 500 000 distintos, 0 no canónicos
- [x] El archivo de 1 000 es el inicio exacto del de 500 000 — `cmp` contra `head -n 1000` (y lo mismo con 10 000)
- [x] Ningún carácter que rompa `COPY` — 0 líneas
- [x] Metas de A8 dentro de ±1 punto en 500 000 — las tres
- [x] Empate en la frontera del Top-1000 de Q2 informado (sí/no) — **no**: 1351.37 frente a 1351.29

Además, a escala real: **dos generaciones completas de 500 000 en procesos
distintos dan el mismo SHA-256**, y `cmp` las da por idénticas.

---

## Registro de ejecución

### 2026-11-01 — F2.1: contrato, parámetros y `make_record()`

Archivos: `generator/__init__.py`, `generator/distributions.py`,
`generator/schema.py`, `generator/synthetic_data_generator.py` (solo
`make_record()`; el CLI llega en F2.2) y `tests/test_generator_schema.py`.

Pruebas: `python3 -m unittest discover -s tests -v` → **42 de 42**. Son 31
nuevas más las 11 de `capture_env`. Cubren:

- 2 000 registros que cumplen el contrato, todos con profundidad exactamente 3;
- `order_id` canónico y único;
- `timestamp` estricto, con el orden alfabético igual al cronológico;
- `final_total` numérico y consistente con sus partes;
- determinismo: misma semilla, mismos registros;
- **11 casos malos que el validador rechaza**: `final_total` como string o
  dentro de `totals`, `timestamp` con fracción o con desfase horario, UUID en
  mayúsculas, `discounts` como objetos (4 niveles), clave faltante o de más,
  `\` en un texto y `qty` booleano.

Medido sobre 20 000 registros con semilla 42. **No** es la aceptación formal,
que se hace sobre 500 000 en F2.3:

| Métrica | Medido | Meta |
|---|---|---|
| Ítems por registro (media) | 3.0011 | [2.9, 3.1] |
| `completed` | 70.31 % | 70 ± 1 |
| `timestamp >= 2026` | 49.99 % | 50 ± 1 |
| Ítems con `price > 50` | 44.85 % | 44.94 ± 1 |
| Filas que pasan el filtro de Q2 | 35.37 % | ≈35 % (≈175 000 de 500 000) |
| Profundidad | siempre 3 | 3 |
| Tamaño medio (JSON compacto) | 1 003 bytes | — |

Extrapolación, **no medición**: 500 000 × ~1 KB ≈ 500 MB. El tamaño real se
mide en F2.3.

Comprobación manual del registro 0: 1 × 33.57 = 33.57; descuento 20 % = 6.71;
impuesto 16 % sobre 26.86 = 4.30; 33.57 − 6.71 + 4.30 = 31.16 = `final_total` ✔

### 2026-11-01 — F2.2: CLI, escritura en streaming y estadísticas

En `synthetic_data_generator.py` se agregaron `serialize()`, `Stats`,
`generate()`, `default_paths()` y `main()`. La escritura es atómica (`.tmp` y
luego renombrar). Se valida **cada** registro y se calcula el SHA-256 mientras
se escribe. Las estadísticas incluyen el SHA-256 de cada fuente del generador.
También se agregó `*.jsonl.tmp` a `.gitignore`.

Pruebas: `tests/test_generator_determinism.py`, con 16 pruebas nuevas
(**58 de 58** en total). Los detectores se prueban con datos fabricados:

- un empate puesto a propósito en la frontera del Top-k;
- un `order_id` repetido;
- un registro inválido, que se cuenta sin romper la ejecución;
- el límite exacto de `2026-01-01T00:00:00Z`, que sí entra en el filtro de Q2.

Un fallo durante el desarrollo, corregido: la prueba de formato buscaba `", "`
en toda la línea, y el `user_agent` contiene `(KHTML, like Gecko)`. El error
estaba en la prueba, no en el generador; ahora la prueba ignora el contenido
de los textos.

Corrida real: `results/f2/F2_2_20261101T180005Z.txt`, con comprobaciones de
`sha256sum`, `wc -l` y `cmp`, independientes del generador.

| | `--size 1000` | `--size 10000` |
|---|---|---|
| Líneas (`wc -l`) | 1 000 | 10 000 |
| SHA-256 | `fd0b00da…b64c` | `66ca4f7b…4111` |
| Bytes · segundos | 1 013 389 · 0.35 s | 10 043 066 · 3.48 s |
| Contrato | OK: 0 inválidos, 0 `order_id` repetidos | OK: 0 inválidos, 0 repetidos |
| Ítems por registro | 3.075 | 3.0038 |
| `completed` · `ts >= 2026` · `price > 50` | 75.2 % · 48.3 % · 46.63 % | 70.07 % · 49.6 % · 44.7 % |
| Grupos país × categoría | — | 240 de 240 (95–164 ítems por grupo) |
| Filas del filtro Q2 | 363 | 3 506 (35.06 %) |
| Empate en la fila 1000 de Q2 | no aplica (363 < 1000) | **no**: 567.24 frente a 567.20 |

- **Determinismo:** dos procesos distintos con `--size 1000` dan el mismo
  `sha256sum`, y `cmp` dice que son idénticos.
- **Prefijo:** `cmp` del archivo de 1 000 contra `head -n 1000` del de
  10 000: idénticos.
- **Revalidación desde disco** del archivo de 1 000: 0 inválidos, 0
  `final_total` no numéricos y profundidad 3 en todos.

**Ojo al leer la columna de 1 000:** `completed` = 75.2 % está fuera de
70 ± 1. Es variación de muestra pequeña: la tolerancia aprobada aplica a
500 000, no a 1 000. Con 10 000 ya da 70.07 %.

Extrapolación lineal, **no medición**: 500 000 registros ≈ 175 s y ≈ 502 MB.
Se mide en F2.3.

### 2026-11-01 — F2.3: dataset de 500 000

Evidencia:

- `results/f2/F2_3_20261101T181011Z_generacion.txt`: la corrida, con
  `/usr/bin/time -v`.
- `results/f2/F2_3_20261101T181011Z_verificacion.txt`: la verificación.
- `results/dataset_stats.json`: las estadísticas que pide PLAN F2.

El archivo de datos, `data/orders_500000_seed42.jsonl`, no se versiona; se
regenera con el mismo comando y debe dar el mismo SHA-256.

**Generación** (`python3 generator/synthetic_data_generator.py --size 500000`):

| | Valor medido |
|---|---|
| Registros (`wc -l`) | 500 000 |
| Tamaño | 501 751 458 bytes (≈ 478.5 MiB) |
| SHA-256 | `0cd7fadb084627679ab2437921ef1889a012e1fa5b0898d2624760be41060414` |
| Tiempo | 172.35 s (2:52.57 de reloj). La segunda corrida tardó 206.58 s: el tiempo varía, el hash no |
| Memoria máxima del proceso | 78 952 kB (≈ 77 MiB): confirma la escritura en streaming |
| Contrato | 0 inválidos, 0 `order_id` repetidos; profundidad 3 en los 500 000 |

**Verificación independiente.** No usa la clase `Stats` del generador ni
`validate_record`; es código aparte que lee el archivo de disco:

| Métrica | Medido | Meta | |
|---|---|---|---|
| Ítems por registro | 2.9991 | [2.9, 3.1] | ✔ |
| `completed` | 69.9714 % | 70 ± 1 | ✔ |
| `timestamp >= 2026` | 50.0414 % | 50 ± 1 | ✔ |
| Ítems con `price > 50` | 44.8679 % | 44.94 ± 1 | ✔ |
| Grupos país × categoría (Q1) | 240 de 240, entre 6 038 y 6 464 ítems cada uno | 240 | ✔ |
| Filas del filtro de Q2 | 175 049 (35.01 %) | ≈ 175 000 | ✔ |
| `order_id` | 500 000 distintos y 0 no canónicos | — | ✔ |
| `timestamp` fuera de formato · `final_total` no numérico · que no cuadra | 0 · 0 · 0 | 0 | ✔ |
| Líneas que romperían `COPY` | 0 | 0 | ✔ |
| Q2: filas 1000 y 1001 | 1351.37 / 1351.29: **sin empate en la frontera** | informar | ✔ |

Rangos: `timestamp` de `2025-01-01T00:02:42Z` a `2026-12-31T23:57:23Z` ·
`final_total` de 0.85 a 2318.39.

**Hallazgo para F4: hay 20 valores repetidos *dentro* del Top-1000 de Q2.**
Como la frontera no empata, el **conjunto** de los 1 000 `order_id` está
determinado y debe coincidir entre motores. Pero el **orden** dentro del
conjunto no es determinista: Q2 no tiene desempate, así que dos filas con el
mismo `final_total` pueden salir en cualquier orden. Esto confirma la
decisión de PLAN F4: comparar como conjunto, no posición a posición.
