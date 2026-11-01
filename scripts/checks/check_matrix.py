#!/usr/bin/env python3
"""check_matrix.py — estado de la matriz: CV, tendencias y avisos por celda (F8).

Uso:
    .venv/bin/python scripts/checks/check_matrix.py                 # results/measurements.csv
    .venv/bin/python scripts/checks/check_matrix.py --salida f8_humo
    .venv/bin/python scripts/checks/check_matrix.py --matriz 36 --q2-variante MEM_LOW

Se corre después de cada bloque, no solo al final: si el entorno se degrada a
mitad de las 13 h, se ve en el bloque siguiente y no cuando ya no hay remedio.

Por celda con sus 3 repeticiones:
  - CV del throughput y del p50, con el criterio de F7 (< 15 %);
  - **tendencia** con el criterio F7-b: monótona Y más del 10 % de r1 a r3. El CV
    no ve una degradación progresiva (100-110-120 da 9 % y pasa);
  - `status` de cada repetición, muestras completadas (A4) y throttling, con la
    línea base en reposo al lado (F6.3);
  - avisos: baja densidad muestral, percentiles invalidados por censura,
    suspensión de la VM, fallos de telemetría y workers cortados.

Y del conjunto: cuántas corridas faltan, filas descartadas (R-27.1) y planes.

Es una verificación, no una medición: no escribe en ningún CSV.
Salida: results/<salida>/check_matrix.json
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "checks"))

from benchmark_runner import schedule  # noqa: E402
from benchmark_runner.config import LOW_DENSITY_SAMPLES  # noqa: E402
from check_pilot_f7 import CV_MAX, baseline_throttling, cv, trend  # noqa: E402

KEY = ("engine", "profile", "query_id", "concurrency")


def num(x):
    return None if x in (None, "") else float(x)


def load_raw(base: Path, run_id: str) -> dict:
    f = base / "raw" / f"{run_id}.json"
    return json.loads(f.read_text()) if f.exists() else {}


def cell_report(base: Path, rows: list[dict], baseline: dict) -> dict:
    rows = sorted(rows, key=lambda r: int(r["run_number"]))
    qps = [num(r["throughput_qps"]) for r in rows]
    p50 = [num(r["latency_p50_ms"]) for r in rows if num(r["latency_p50_ms"]) is not None]
    out: dict = {
        "repeticiones": len(rows),
        "status": [r["status"] for r in rows],
        "throughput_qps": qps,
        "p50_ms": [num(r["latency_p50_ms"]) for r in rows],
        "p95_ms": [num(r["latency_p95_ms"]) for r in rows],
        "p99_ms": [num(r["latency_p99_ms"]) for r in rows],
        "cpu_throttled_seconds": [num(r["cpu_throttled_seconds"]) for r in rows],
        "max_rss_mb": [num(r["max_rss_mb"]) for r in rows],
        "disk_spill": [r["disk_spill"] for r in rows],
    }
    base_thr = baseline.get((rows[0]["engine"], rows[0]["profile"]))
    out["throttling_en_reposo_estimado_s"] = base_thr["estimado_en_la_ventana_s"] if base_thr else None

    completas = len(rows) == 3 and all(x is not None for x in qps)
    out["cv_throughput"] = round(c, 4) if completas and (c := cv(qps)) is not None else None
    out["cv_p50"] = round(c2, 4) if len(p50) == 3 and (c2 := cv(p50)) is not None else None
    out["tendencia_throughput"] = trend(qps) if completas else None
    out["tendencia_p50"] = trend(p50) if len(p50) == 3 else None

    avisos, cortados = [], 0
    for r in rows:
        raw = load_raw(base, f"{r['engine']}_{r['profile']}_{r['query_id']}_c{r['concurrency']}_r{r['run_number']}")
        if not raw:
            avisos.append(f"r{r['run_number']}: no se encontró el crudo")
            continue
        cens = raw.get("censura", {})
        if (cens.get("completadas_en_ventana") or 0) < LOW_DENSITY_SAMPLES:
            avisos.append(f"r{r['run_number']}: baja densidad muestral "
                          f"({cens.get('completadas_en_ventana')} < {LOW_DENSITY_SAMPLES}; A4)")
        invalidos = [k for k, v in (cens.get("percentil_valido") or {}).items() if not v]
        if invalidos:
            avisos.append(f"r{r['run_number']}: percentiles invalidados por censura ({', '.join(invalidos)}; A4): "
                          f"{(cens.get('fraccion_timeouts') or 0):.0%} de timeouts")
        for motivo in raw.get("motivos", []):
            if "suspend" in motivo.lower() or "congel" in motivo.lower():
                avisos.append(f"r{r['run_number']}: {motivo} → DESCARTAR Y REPETIR (F8-b)")
        tele = raw.get("telemetria") or {}
        if tele.get("fallo"):
            avisos.append(f"r{r['run_number']}: fallo de telemetría: {tele.get('motivos')}")
        ds = raw.get("dataset")
        if ds and not ds.get("intacto"):
            avisos.append(f"r{r['run_number']}: DATASET NO INTACTO tras el OOM ({ds.get('filas')} filas)")
        cortados += raw.get("consultas", {}).get("workers_terminados_al_final", 0)
    out["workers_cortados_al_final"] = cortados
    out["avisos"] = avisos

    out["checks"] = {
        "3_repeticiones": len(rows) == 3,
        "cv_throughput_<15%": out["cv_throughput"] is not None and out["cv_throughput"] < CV_MAX,
        "sin_tendencia_throughput": not (out["tendencia_throughput"] or {}).get("hay_tendencia", False),
        "sin_tendencia_p50": not (out["tendencia_p50"] or {}).get("hay_tendencia", False),
    }
    # Con filas error/oom el CV no significa nada: se informa, no se exige (A4, F7.3).
    out["medible"] = all(s in ("ok", "spill") for s in out["status"]) and completas
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--salida", default="", metavar="DIR")
    ap.add_argument("--matriz", type=int, default=54, choices=(54, 36))
    ap.add_argument("--q2-variante", choices=("MEM_LOW", "MEM_HIGH"))
    args = ap.parse_args()

    base = ROOT / "results" / args.salida if args.salida else ROOT / "results"
    csv_path = base / "measurements.csv"
    if not csv_path.exists():
        sys.exit(f"no existe {csv_path}")
    with csv_path.open(newline="") as f:
        rows = list(csv.DictReader(f))

    by_cell: dict[tuple, list[dict]] = {}
    for r in rows:
        by_cell.setdefault(tuple(r[c] for c in KEY), []).append(r)
    baseline = baseline_throttling()

    cells = {}
    for k in sorted(by_cell, key=lambda k: (k[0], k[1], k[2], int(k[3]))):
        cells["_".join(k)] = cell_report(base, by_cell[k], baseline)

    desc_path = base / "descartadas.csv"
    descartadas = []
    if desc_path.exists():
        with desc_path.open(newline="") as f:
            descartadas = [{k: r[k] for k in ("run_id", "descartada_utc", "status", "motivo")}
                           for r in csv.DictReader(f)]

    out = {"descripcion": "estado de la matriz (F8): CV, tendencias y avisos por celda; verificación, no medición",
           "csv": str(csv_path.relative_to(ROOT)), "filas": len(rows),
           "resumen_matriz": {k: v for k, v in schedule.summary(csv_path, args.matriz, args.q2_variante).items()
                              if k != "ajenas_a_esta_matriz"},
           "ajenas_a_esta_matriz": schedule.summary(csv_path, args.matriz, args.q2_variante)["ajenas_a_esta_matriz"],
           "descartadas": descartadas, "planes": sorted(p.name for p in (base / "explains").glob("*.json")),
           "celdas": cells}

    medibles = [c for c in cells.values() if c["medible"]]
    fallan = {n: [k for k, v in c["checks"].items() if not v] for n, c in cells.items()
              if c["medible"] and not all(c["checks"].values())}
    out["celdas_medibles"] = len(medibles)
    out["celdas_con_criterio_incumplido"] = fallan
    (base / "check_matrix.json").write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n")

    r = out["resumen_matriz"]
    print(f"== {out['csv']}: {out['filas']} filas · hechas {r['hechas']}/{r['corridas_de_la_matriz']} · "
          f"faltan {r['faltan']} · descartadas {len(descartadas)} · planes {len(out['planes'])}")
    print(f"{'celda':<54} {'status':<14} {'CV qps':>7} {'CV p50':>7} {'tend.':>22} {'throttle (reposo)':>22}")
    for name, c in cells.items():
        t = c["tendencia_throughput"] or {}
        tend = f"{t.get('monotona') or '-'} {(t.get('cambio_rel') or 0) * 100:+.1f}%" if t else "-"
        thr = c["cpu_throttled_seconds"]
        thr_s = f"{(sum(x for x in thr if x) / max(1, len([x for x in thr if x]))):.0f}" if any(thr) else "-"
        print(f"{name[:54]:<54} {','.join(s[:4] for s in c['status']):<14} "
              f"{(c['cv_throughput'] or 0) * 100:>6.1f}% {(c['cv_p50'] or 0) * 100:>6.1f}% {tend:>22} "
              f"{thr_s:>12} ({c['throttling_en_reposo_estimado_s'] or 0:.1f})")
        for a in c["avisos"]:
            print(f"      AVISO {a}")
    if fallan:
        print("\nCeldas medibles que NO cumplen algún criterio:")
        for n, ks in fallan.items():
            print(f"   {n}: {', '.join(ks)}")
    else:
        print(f"\nTodas las celdas medibles ({len(medibles)}) cumplen CV < 15 % y sin tendencia.")
    print(f"-> {(base / 'check_matrix.json').relative_to(ROOT)}")
    return 1 if fallan else 0


if __name__ == "__main__":
    sys.exit(main())
