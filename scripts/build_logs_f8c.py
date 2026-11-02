#!/usr/bin/env python3
"""build_logs_f8c.py — logs de spill y OOM correlacionados con su fila del CSV (F8-c, R-32).

Uso:
    .venv/bin/python scripts/build_logs_f8c.py                 # results/
    .venv/bin/python scripts/build_logs_f8c.py --salida f7     # otra carpeta

R-32 pide "capturas o logs de spill/OOM como evidencia" en `results/logs/`,
referenciados desde el reporte, y PLAN F8 pide que **cada fila `error` tenga su
log correlacionado**. Los datos ya están todos en los crudos: lo que faltaba era
poder ir de una fila del CSV a su explicación sin abrir un JSON de miles de líneas.

Este script **no mide nada y no inventa nada**: lee el CSV y los crudos y escribe
un archivo por repetición afectada, con punteros a la evidencia original. Si se
borra `results/logs/` se puede regenerar igual, porque no es una fuente de datos.

Entran las repeticiones con `status` `error` u `oom`, **y** las que tienen
`disk_spill=true` aunque su status sea otro (en `spill` la precedencia es
`oom` > `error` > `spill`, así que un volcado puede quedar tapado por un OOM).

Salida: `results/logs/<run_id>.md` y `results/logs/README.md` con la tabla índice.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from benchmark_runner.config import LOW_DENSITY_SAMPLES  # noqa: E402


def run_id(row: dict) -> str:
    return (f"{row['engine']}_{row['profile']}_{row['query_id']}"
            f"_c{row['concurrency']}_r{row['run_number']}")


def afectada(row: dict) -> bool:
    return row["status"] in ("error", "oom") or row["disk_spill"] == "true"


def mib(x) -> str:
    return "—" if x in (None, "") else f"{float(x):.1f} MiB"


def tabla(pares: list[tuple[str, object]]) -> str:
    return "\n".join(f"| {k} | {v} |" for k, v in pares)


def ficha(row: dict, raw: dict, base: Path) -> str:
    rid = run_id(row)
    cens = raw.get("censura", {})
    cons = raw.get("consultas", {})
    cg_i, cg_f = raw.get("cgroup", {}).get("inicio", {}), raw.get("cgroup", {}).get("fin", {})
    spill = raw.get("spill", {}).get("delta", {})
    estado = raw.get("estado_contenedor_final", {})
    flush = raw.get("preparacion", {}).get("flush", {})
    tele = raw.get("telemetria") or {}
    ds = raw.get("dataset")
    serie = raw.get("serie_cgroup_1s") or {}
    cols, filas = serie.get("columnas", []), serie.get("filas", [])

    partes = [f"# {rid}", "",
              f"`status={row['status']}` · `disk_spill={row['disk_spill']}` · "
              f"{raw.get('inicio_utc', '?')} · ventanas {raw.get('ventanas_s')}", "",
              "## La fila del CSV", "", "| Columna | Valor |", "|---|---|",
              tabla([(k, row[k]) for k in row]), "",
              "## Por qué salió así", ""]
    for m in raw.get("motivos", []) or ["(sin motivos registrados)"]:
        partes.append(f"- {m}")

    partes += ["", "## Consultas en la ventana (A4)", "", "| Dato | Valor |", "|---|---|",
               tabla([("Completadas en la ventana", cens.get("completadas_en_ventana")),
                      ("Timeouts en la ventana", cens.get("timeouts_en_ventana")),
                      ("Errores en la ventana", cens.get("errores_en_ventana")),
                      ("Fracción de timeouts", cens.get("fraccion_timeouts")),
                      ("Límite por consulta", f"{cens.get('limite_s')} s"),
                      ("Percentiles válidos", cens.get("percentil_valido")),
                      ("Por tipo, toda la repetición", cons.get("por_tipo")),
                      ("Workers cortados al final", cons.get("workers_terminados_al_final")),
                      ("Baja densidad muestral", "sí" if (cens.get("completadas_en_ventana") or 0)
                       < LOW_DENSITY_SAMPLES else "no")]), ""]

    if row["status"] == "oom" or (cg_f.get("oom_kill") or 0) > (cg_i.get("oom_kill") or 0):
        partes += ["## OOM", "", "| Dato | Valor |", "|---|---|",
                   tabla([("`oom_kill` del cgroup (inicio → fin)",
                           f"{cg_i.get('oom_kill')} → {cg_f.get('oom_kill')}"),
                          ("`oom` del cgroup (inicio → fin)", f"{cg_i.get('oom')} → {cg_f.get('oom')}"),
                          ("`OOMKilled` de Docker", estado.get("OOMKilled")),
                          ("¿El contenedor seguía corriendo?", estado.get("Running")),
                          ("Recuento del dataset tras el OOM (R-08)",
                           "no se hizo" if ds is None else
                           f"{ds.get('filas')} de {ds.get('esperadas')} filas en {ds.get('segundos')} s, "
                           f"{'intacto' if ds.get('intacto') else 'NO INTACTO'}"
                           f"{' (intentos: ' + str(ds.get('intentos')) + ')' if ds.get('intentos') else ''}"),
                          ("`max_rss_mb` (anon)", mib(row["max_rss_mb"]))]),
                   "",
                   "`OOMKilled=true` con `Running=true` significa que el kernel mató **algún** proceso "
                   "del cgroup del motor, no necesariamente el motor entero (F6.3).", ""]
        # Dos lecturas que es fácil equivocar, y que cambian cómo se cita la fila en el reporte.
        delta_kill = (cg_f.get("oom_kill") or 0) - (cg_i.get("oom_kill") or 0)
        if delta_kill == 0 and estado.get("OOMKilled"):
            partes += ["**El OOM ocurrió ANTES de la ventana de medición**, no dentro: el contador "
                       f"`oom_kill` del cgroup no se movió durante la ventana ({cg_i.get('oom_kill')} → "
                       f"{cg_f.get('oom_kill')}). Como el contenedor se recrea en cada repetición, la marca "
                       "`OOMKilled` de Docker es de esta misma repetición: el motor se quedó sin memoria "
                       "durante el calentamiento.", ""]
        if not cens.get("completadas_en_ventana"):
            partes += ["**Cómo leer las columnas de recursos de esta fila:** con 0 consultas completadas, "
                       f"`cpu_throttled_seconds` ({row['cpu_throttled_seconds']}) y `max_rss_mb` "
                       f"({row['max_rss_mb']}) describen un motor **ya colapsado**, no el costo de atender "
                       "la carga. No se pueden citar como \"lo que consumió el motor\": lo que dicen es que "
                       "durante la ventana el motor no estaba trabajando. Los errores registrados son "
                       "conexiones rechazadas, no consultas ejecutadas.", ""]

    if spill:
        partes += ["## Volcado a disco (A6)", "", "| Contador | Δ en la ventana |", "|---|---|",
                   tabla([(k, f"{v:,.0f}".replace(",", " ")) for k, v in sorted(spill.items())]), ""]
        if "temp_bytes" in spill:
            partes.append(f"Son **{spill['temp_bytes'] / 1e9:.1f} GB** en "
                          f"{int(spill.get('temp_files', 0))} archivos temporales; con "
                          f"{cens.get('completadas_en_ventana')} consultas completadas, "
                          f"~{spill['temp_bytes'] / 1e9 / max(1, cens.get('completadas_en_ventana') or 1):.2f} GB "
                          "por consulta.")
            partes.append("")

    thr = row["cpu_throttled_seconds"]
    partes += ["## Recursos y entorno", "", "| Dato | Valor |", "|---|---|",
               tabla([("Throttling de CPU", "—" if thr in (None, "") else f"{float(thr):.1f} s"),
                      ("`max_rss_mb` (anon)", mib(row["max_rss_mb"])),
                      ("Muestras de la serie de 1 s", len(filas)),
                      ("`working_set` máximo (M3, SPEC A11)",
                       mib(max(f[cols.index("memory_current")] - f[cols.index("inactive_file")]
                               for f in filas) / 2**20) if filas and "inactive_file" in cols else "—"),
                      ("`shmem` máximo (F6-A3)",
                       mib(max(f[cols.index("shmem")] for f in filas) / 2**20) if filas and "shmem" in cols else "—"),
                      ("Flush de caché", f"liberó {flush.get('liberado_kb')} kB por la vía "
                                         f"`{flush.get('via', '?')}`, ok={flush.get('ok')}"),
                      ("Telemetría", f"{tele.get('estado_exportacion')}"
                                     f"{' — FALLO' if tele.get('fallo') else ''}"),
                      ("Límites reales del cgroup", raw.get("preparacion", {}).get("limites")),
                      ("Versión del motor", raw.get("preparacion", {}).get("engine_version"))]), ""]

    ejemplos = cons.get("ejemplos_de_error") or []
    if ejemplos:
        partes += ["## Ejemplos de error del motor", "", "```"]
        partes += [str(e)[:300] for e in ejemplos[:5]]
        partes += ["```", ""]

    rel = lambda p: str(p.relative_to(ROOT)) if p.exists() else f"{p.relative_to(ROOT)} (no existe)"  # noqa: E731
    partes += ["## Evidencia original", "",
               f"- Crudo completo: `{rel(base / 'raw' / (rid + '.json'))}`",
               f"- Telemetría de la ventana: `{rel(base / 'telemetry' / (rid + '.json'))}`",
               f"- Plan de ejecución (R-31, solo en c=1): "
               f"`{raw.get('plan') or 'no se captura en esta celda'}`",
               f"- Serie de 1 s del cgroup: dentro del crudo, en `serie_cgroup_1s`",
               ""]
    return "\n".join(partes) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--salida", default="", metavar="DIR")
    args = ap.parse_args()
    base = ROOT / "results" / args.salida if args.salida else ROOT / "results"
    csv_path = base / "measurements.csv"
    if not csv_path.exists():
        sys.exit(f"no existe {csv_path}")
    with csv_path.open(newline="") as f:
        rows = list(csv.DictReader(f))

    logs = base / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    indice, faltan = [], []
    for row in rows:
        if not afectada(row):
            continue
        rid = run_id(row)
        raw_file = base / "raw" / f"{rid}.json"
        if not raw_file.exists():
            faltan.append(rid)
            continue
        raw = json.loads(raw_file.read_text())
        (logs / f"{rid}.md").write_text(ficha(row, raw, base))
        spill = raw.get("spill", {}).get("delta", {})
        indice.append({
            "run_id": rid, "status": row["status"], "spill": row["disk_spill"],
            "completadas": raw.get("censura", {}).get("completadas_en_ventana"),
            "temp_gb": round(spill["temp_bytes"] / 1e9, 1) if "temp_bytes" in spill else None,
            "oom_kill": (raw.get("cgroup", {}).get("fin", {}).get("oom_kill") or 0)
                        - (raw.get("cgroup", {}).get("inicio", {}).get("oom_kill") or 0),
            "motivos": len(raw.get("motivos", [])),
        })

    cab = ("# Logs de spill y OOM (R-32, F8-c)\n\n"
           "Un archivo por repetición con `status` `error` u `oom`, **o** con `disk_spill=true`.\n"
           "Cada uno correlaciona su fila del CSV con los motivos, la censura (A4), los contadores\n"
           "del cgroup, los contadores de volcado, el estado del contenedor y la telemetría, y\n"
           "apunta a la evidencia original.\n\n"
           "**Generado por `scripts/build_logs_f8c.py` a partir de `measurements.csv` y de\n"
           "`results/raw/`: no es una fuente de datos y se puede regenerar.**\n\n"
           f"Repeticiones afectadas: **{len(indice)}** de {len(rows)} filas del CSV.\n\n"
           "| Repetición | status | spill | Completadas | Temporales | Δ `oom_kill` |\n"
           "|---|---|---|---|---|---|\n")
    cuerpo = "".join(
        f"| [{r['run_id']}]({r['run_id']}.md) | `{r['status']}` | {r['spill']} | {r['completadas']} | "
        f"{'—' if r['temp_gb'] is None else str(r['temp_gb']) + ' GB'} | {r['oom_kill']} |\n"
        for r in indice)
    pie = ""
    if faltan:
        pie = "\n**Sin crudo, no se pudo generar:** " + ", ".join(faltan) + "\n"
    (logs / "README.md").write_text(cab + cuerpo + pie)

    print(f"{len(indice)} ficha(s) en {logs.relative_to(ROOT)}/ (de {len(rows)} filas)")
    for r in indice:
        print(f"   {r['run_id']:<52} {r['status']:<6} spill={r['spill']:<5} "
              f"compl={r['completadas']} temp={r['temp_gb']} oom_kill=+{r['oom_kill']}")
    if faltan:
        print(f"AVISO: sin crudo: {faltan}")
    print(f"-> {(logs / 'README.md').relative_to(ROOT)}")
    return 1 if faltan else 0


if __name__ == "__main__":
    sys.exit(main())
