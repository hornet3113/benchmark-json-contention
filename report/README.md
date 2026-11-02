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

## Dos trampas de LaTeX que ya están resueltas (no reintroducirlas)

1. **`\ldots` pegado a una letra.** `\ldots{}d07a` es correcto; `\ldots d07a` sin
   llaves hace que LaTeX lea `\ldotsd` como un comando inexistente y la
   compilación **no produce PDF**. Pasó con los digests de la sección 1. Las
   llaves vacías cierran el comando venga detrás letra o dígito.
2. **Los comentarios de los `.dat` van con `%`, no con `#`.** pgfplots lee esos
   archivos con TeX, donde el carácter de comentario es `%`. Una línea que empiece
   por `#` intentaría leerse como datos. Lo genera así
   `scripts/build_report_data.py`.
3. **Nada de `\newcommand` con parámetros dentro de una figura.** pgfplots
   reinterpreta el cuerpo de la figura con su analizador de claves, y los `#` de
   los parámetros del macro lo rompen: *«Illegal parameter number in definition
   of \pgfkeys@...»*, y de nuevo sin PDF. Los paneles de las figuras están
   escritos uno a uno a propósito: es más largo, pero no depende de cómo pgfkeys
   reinterprete el cuerpo.
4. **Cada figura nombra sus datos con la ruta completa** (`datos/xxx.dat`) en vez
   de apoyarse en la clave `table/search path`. Una dependencia menos.
5. **`\input` dentro de un `tabular` no admite `\bottomrule` después.** Da
   *«Misplaced \noalign»* (comprobado en aislado con pdflatex). Por eso el cuerpo
   generado de la tabla de OOM **cierra él mismo con `\bottomrule`** y la sección
   solo hace `\input`. En la tabla grande no hace falta, porque en un `longtable`
   el `\bottomrule` va dentro de `\endfoot`, antes del cuerpo.
6. **Dentro de `\IfFileExists` los `#` se duplican.** LaTeX guarda las dos ramas
   en una definición, así que el respaldo de `\num` se escribe `{##1}`.

## Paquetes necesarios

```sh
sudo apt install texlive-lang-spanish texlive-science   # babel español y siunitx
```

Sin ellos el documento **compila igual** —el preámbulo lo detecta y avisa— pero
sale con «Abstract» y «Contents» en inglés, sin guionado español y con los miles
sin separador.
