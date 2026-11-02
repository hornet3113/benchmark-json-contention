# report/ — el reporte en LaTeX (F9)

**Se compila con pdfLaTeX.** En Overleaf: subir esta carpeta completa y compilar
`reporte.tex`. En local: `latexmk -pdf reporte.tex` (necesita `pgfplots` y
`siunitx`, los dos en TeX Live).

## Ningún número está escrito a mano

Es un criterio de aceptación de PLAN F9: *cada número del reporte es trazable a
una fila del CSV o a un archivo de `results/`*. Por eso el texto no contiene
cifras: las toma de tres carpetas que **genera un script**.

```
scripts/build_report_data.py        lee results/measurements.csv y results/raw/
  └── report/datos/*.dat            series que pgfplots dibuja
  └── report/tablas/*.tex           cuerpos de tabla, para \input
  └── report/cifras/cifras.tex      macros: \cifraFilasCsv, \cifraFilasOom, …
```

Si cambian los datos, se vuelve a correr el script y el reporte queda al día.
**No editar nada de esas tres carpetas a mano.**

## Por qué las figuras son pgfplots y no imágenes

Las tres figuras obligatorias (R-30) las dibuja LaTeX leyendo los `.dat`. Así el
revisor abre el archivo de datos y ve de dónde sale cada punto, que es
exactamente lo que pide el criterio de trazabilidad. Un PNG sería opaco.

| Archivo | Figura |
|---|---|
| `figuras/p99-concurrencia.tex` | P99 contra concurrencia, **en dos vistas** (R-30.1) |
| `figuras/throttling-qps.tex` | Throttling contra throughput, con la línea base en reposo |
| `figuras/curva-rss.tex` | Curva de memoria, con `anon` frente a `working_set` (F6-A3) |

## Decisiones que el reporte tiene que respetar

- **R-30.1**: la figura de P99 muestra las dos vistas (con y sin la primera
  consulta en frío), no una nota al pie.
- **R-29.1**: los OOM se cuentan distinguiendo los que ocurrieron **en la
  ventana** de los que ocurrieron **en el calentamiento**.
- **R-29.2**: `postgresql · C · Q1 · c=50` lleva **nota al pie en toda tabla**
  donde aparezca (macro `\tnotaColapsada`).
- **A11 / F6-A3**: M3 se calcula con `working_set`, no con `max_rss_mb`.
- **R-27.1**: el reporte incluye la tabla de repeticiones descartadas; si fueron
  cero, lo dice.
