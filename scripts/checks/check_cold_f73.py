#!/usr/bin/env python3
"""check_cold_f73.py — la primera consulta en frío frente al calentamiento de 60 s (F7.3, PLAN F7).

Uso:  .venv/bin/python scripts/checks/check_cold_f73.py     (después de scripts/run_cold_f73.sh)

La pregunta de PLAN F7: ¿caben las primeras consultas (en frío, justo después del
flush) dentro de los 60 s de calentamiento del manual? Si no caben, algunas
entran en la ventana de medición y **contaminan P95 y P99** de ese perfil. Es una
limitación del protocolo que se declara en el reporte, no un error del runner.

Por celda, de cada crudo de results/f7_frio/raw/:
  - duración de la primera consulta de cada worker (mediana, máximo);
  - cuántas de esas primeras consultas TERMINAN ya dentro de la ventana: esas son
    las que contaminan los percentiles;
  - qué fracción de las consultas completadas en la ventana son primeras
    consultas, que es lo que mide de verdad cuánto se desplazan P95 y P99;
  - p95 y p99 de la fila, y los mismos percentiles recalculados SIN las primeras
    consultas, para ver cuánto cambia.

Es una verificación, no una medición: no escribe en ningún CSV.
Salida: results/f7_frio/check_cold.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from benchmark_runner.metrics import percentiles, window  # noqa: E402

FRIO = ROOT / "results" / "f7_frio"
WARMUP_MANUAL_S = 60       # playbook.pdf §6


def analyse(raw: dict) -> dict:
    row = raw["fila_csv"]
    w0, w1 = raw["ventana_ns"]["inicio"], raw["ventana_ns"]["fin"]
    warm = raw["ventanas_s"]["warmup_s"]

    first: dict[int, tuple[int, int, int]] = {}
    for start, end, ok, wid in raw["muestras"]:
        if wid not in first or start < first[wid][0]:
            first[wid] = (start, end, ok)
    durations = sorted(round((e - s) / 1e9, 3) for s, e, _ in first.values())   # ns → s

    # Las que terminan dentro de la ventana: son las que entran en los percentiles.
    cold_in_window = {wid for wid, (s, e, _) in first.items() if w0 <= e <= w1}
    samples = [window.Sample(s, e, bool(ok), "ok" if ok else "error", wid)
               for s, e, ok, wid in raw["muestras"]]
    in_window = [x for x in samples if x.ok and w0 <= x.end_ns <= w1]
    without_cold = [x for x in in_window if not (x.wid in first and x.start_ns == first[x.wid][0])]

    p_all = percentiles.compute([x.latency_ms for x in in_window])
    p_warm = percentiles.compute([x.latency_ms for x in without_cold])
    sin_terminar = sorted(set(raw["consultas"].get("workers_sin_terminar", [])) - set(first))
    return {
        "celda": raw["run_id"], "engine": row["engine"], "profile": row["profile"], "query_id": row["query_id"],
        "concurrency": row["concurrency"], "status": row["status"],
        "calentamiento_s": warm, "calentamiento_del_manual_s": WARMUP_MANUAL_S,
        "workers_con_primera_consulta": len(first),
        "workers_sin_ninguna_consulta_terminada": sin_terminar,
        "primera_consulta_s": {"min": durations[0] if durations else None,
                               "mediana": durations[len(durations) // 2] if durations else None,
                               "max": durations[-1] if durations else None},
        "primeras_que_pasan_del_calentamiento": sum(1 for d in durations if d > warm),
        "cabe_en_el_calentamiento": bool(durations) and durations[-1] <= warm and not sin_terminar,
        "primeras_que_terminan_en_la_ventana": len(cold_in_window),
        "completadas_en_la_ventana": len(in_window),
        "fraccion_de_la_ventana_que_es_primera_consulta": (round(len(cold_in_window) / len(in_window), 4)
                                                           if in_window else None),
        "percentiles_de_la_fila": {"p50": row["latency_p50_ms"], "p95": row["latency_p95_ms"],
                                   "p99": row["latency_p99_ms"]},
        "percentiles_sin_las_primeras": {"n": p_warm.n, "p50": p_warm.p50, "p95": p_warm.p95, "p99": p_warm.p99},
        "percentiles_recalculados_con_todas": {"n": p_all.n, "p50": p_all.p50, "p95": p_all.p95, "p99": p_all.p99},
    }


def main() -> int:
    files = sorted((FRIO / "raw").glob("*.json"))
    if not files:
        sys.exit(f"no hay crudos en {(FRIO / 'raw').relative_to(ROOT)}: ¿corriste scripts/run_cold_f73.sh?")
    rows = [analyse(json.loads(f.read_text())) for f in files]
    out = {"descripcion": "primera consulta en frío frente al calentamiento (F7.3); verificación, no medición",
           "celdas": rows,
           "perfiles_donde_no_cabe": sorted({f"{r['profile']}/{r['engine']}" for r in rows
                                             if not r["cabe_en_el_calentamiento"]}),
           "todas_caben": all(r["cabe_en_el_calentamiento"] for r in rows)}
    (FRIO / "check_cold.json").write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n")
    print(f"{'celda':<58} {'1ª máx':>8} {'mediana':>8} {'>cal':>5} {'en vent':>8} {'% vent':>7} "
          f"{'p95 fila':>9} {'p95 sin 1ª':>11}")
    for r in rows:
        d = r["primera_consulta_s"]
        pct = r["fraccion_de_la_ventana_que_es_primera_consulta"]
        p95, p95b = r["percentiles_de_la_fila"]["p95"], r["percentiles_sin_las_primeras"]["p95"]
        print(f"{r['celda'][:58]:<58} {d['max'] or 0:>8.1f} {d['mediana'] or 0:>8.1f} "
              f"{r['primeras_que_pasan_del_calentamiento']:>5} {r['primeras_que_terminan_en_la_ventana']:>8} "
              f"{(pct * 100 if pct is not None else 0):>6.1f}% {p95 or 0:>9.0f} {p95b or 0:>11.0f}"
              f"{'' if r['cabe_en_el_calentamiento'] else '   NO CABE'}")
    print(f"\nPerfiles donde NO cabe: {out['perfiles_donde_no_cabe'] or 'ninguno'}")
    print(f"-> {FRIO / 'check_cold.json'}")
    # Informativo: que no quepa es un hallazgo que se declara, no un fallo de ejecución.
    return 0


if __name__ == "__main__":
    sys.exit(main())
