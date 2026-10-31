# queries/ — Q1 y Q2 copiadas literalmente del manual

Estos cuatro archivos son **copia literal** de `docs/manual/playbook.pdf`,
§5.1 (Q1, p.2) y §5.2 (Q2, pp.2–3). No se escribieron a mano: los recorta del
PDF `scripts/extract_queries.py`, para que ningún espacio ni carácter dependa
de teclear (CLAUDE.md, R-11 a R-14).

| Archivo | Sección | SHA-256 |
|---|---|---|
| `mongo/q1_unwind_group.json` | §5.1, MongoDB (pipeline) | `4e205fff06510a82199bcbcad08cb4f4d757e2398b2f116c27a9f7f8b9b1bfdb` |
| `postgres/q1_unwind_group.sql` | §5.1, PostgreSQL | `083022bb98151305999693ecfa4e5103f44a9255b3f80105de79b9ab6ef59606` |
| `mongo/q2_sort_topk.json` | §5.2, MongoDB (pipeline) | `0b64f88fa336a805e7ed038019894a25d75098a862d6281f724fcbee4c00fc10` |
| `postgres/q2_sort_topk.sql` | §5.2, PostgreSQL | `930906f5aa9b8f94911445bf90377f4bd4a02df818140ca726d5717f30eecbbd` |

## Cómo se obtuvieron (2026-11-01)

```bash
python3 scripts/extract_queries.py           # escribe los cuatro archivos
python3 scripts/extract_queries.py --check   # compara sin escribir; exit 1 si difieren
```

- Extracción: `pdftotext -layout` (poppler-utils 26.01.0), que conserva los espacios.
- Lo único que se quita es lo que el PDF mete en medio y no es query: líneas
  en blanco, el número de página y la cabecera de la página siguiente. El
  pipeline de Q2 en Mongo cruza el salto entre las páginas 2 y 3. También se
  recortan los espacios al final de línea.
- La sangría es la que da `-layout` según la posición visual en el PDF. En
  JSON y en SQL la sangría no cambia el significado.

**Verificación cruzada.** Con todos los espacios eliminados, cada archivo es
idéntico carácter por carácter al texto que da un segundo método de extracción
independiente (lectura directa de los streams del PDF, con los escapes `\050` y
`\051` decodificados a paréntesis). Los cuatro coinciden.

## Lo que NO está en estos archivos, a propósito

Las **variantes de estrés de memoria** de Q2 (§5.2) no forman parte del texto
de la query, sino de cómo se ejecuta:

- MongoDB: opción `allowDiskUse: false` / `true` de `aggregate()`.
- PostgreSQL: `SET work_mem = '4MB'` / `'64MB'` en la sesión, antes de la query.

Los planes de ejecución (R-31) se obtienen anteponiendo `EXPLAIN (ANALYZE,
BUFFERS, FORMAT JSON)` al texto leído de aquí, o con `explain("executionStats")`
en Mongo. Los archivos no se modifican.

Las consultas que fuerzan spill u OOM **no** viven aquí: van en `scripts/probes/` (SPEC A12).
