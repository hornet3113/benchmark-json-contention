#!/usr/bin/env python3
"""check_adapters.py — verifica los adaptadores de F5.3 contra la evidencia de F3-G3.

Uso (con el motor arriba, datos de G3 cargados, entorno .venv):
    .venv/bin/python scripts/checks/check_adapters.py --engine mongodb|postgresql

1. Ejecuta Q1, Q2_MEM_LOW y Q2_MEM_HIGH POR LOS ADAPTADORES (drivers del runner)
   y compara el resultado con results/f3/g3/queries_<motor>.json, producido por
   check_equivalence.py (CLI) y ya validado allí contra la referencia exacta.
   Q2 se compara como conjunto: hay final_total repetidos dentro del Top-1000.
2. Límite de tiempo (F5-f): con timeout de 1 ms, Q1 debe lanzar QueryTimeout,
   y la conexión debe seguir sirviendo después (el worker continúa con ella).

Las latencias que imprime son de UNA ejecución, informativas: no son medición.
Salida: results/f5/f5_3/adapters_<motor>.json. Exit 0 si todo coincide.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from benchmark_runner.engines.base import QueryTimeout, make_engine  # noqa: E402
from benchmark_runner.matrix import cells  # noqa: E402

CLI_NAME = {"mongodb": "mongo", "postgresql": "postgres"}
# query_id del runner → nombre de la ejecución en check_equivalence.py
CLI_RUN = {
    "mongodb": {"Q1": "q1_default", "Q2_MEM_LOW": "q2_allowDiskUse_false", "Q2_MEM_HIGH": "q2_allowDiskUse_true"},
    "postgresql": {"Q1": "q1_default", "Q2_MEM_LOW": "q2_work_mem_4MB", "Q2_MEM_HIGH": "q2_work_mem_64MB"},
}


def as_decimal(v):
    return Decimal(v) if isinstance(v, str) else v


def same_q1(a: dict, b: dict) -> bool:
    norm = lambda d: {k: (as_decimal(v["total"]), as_decimal(v["avg"]), int(v["count"])) for k, v in d.items()}  # noqa: E731
    return norm(a) == norm(b)


def same_q2(a: list, b: list) -> tuple[bool, bool]:
    """(mismo conjunto de filas, mismo vector ordenado de final_total)."""
    rows = lambda x: sorted((r[0], r[1], as_decimal(r[2])) for r in x)  # noqa: E731
    vec = lambda x: sorted((as_decimal(r[2]) for r in x), reverse=True)  # noqa: E731
    return rows(a) == rows(b), vec(a) == vec(b)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--engine", required=True, choices=("mongodb", "postgresql"))
    args = parser.parse_args(argv)
    engine = args.engine

    cli = json.loads((ROOT / "results" / "f3" / "g3" / f"queries_{CLI_NAME[engine]}.json").read_text())["queries"]
    targets = {c.query_id: c for c in cells(54) if c.engine == engine
               and c.profile == "PROFILE_A_BASELINE" and c.concurrency == 1}
    out = {"engine": engine, "fecha_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
           "referencia": f"results/f3/g3/queries_{CLI_NAME[engine]}.json", "queries": {}, "timeout": {}}
    ok = True

    for qid, cell in targets.items():
        with make_engine(cell) as e:
            t0 = time.monotonic()
            got = e.fetch()
            t1 = time.monotonic()
            n = e.execute()                      # segunda ejecución, como en el bucle del runner
            t2 = time.monotonic()
            ref = cli[CLI_RUN[engine][qid]]["resultado"]
            if cell.query == "Q1":
                match = {"igual_a_G3": same_q1(got, ref)}
            else:
                s, v = same_q2(got, ref)
                match = {"mismo_conjunto_que_G3": s, "mismo_vector_final_total": v}
            row_ok = all(match.values()) and n == len(ref)
            ok &= row_ok
            out["queries"][qid] = {"archivo_query": str(e.query_path().relative_to(ROOT)),
                                   "sesion": e.session_info(), "filas": n, "filas_G3": len(ref), **match,
                                   "latencia_1a_ms": round((t1 - t0) * 1000, 1),
                                   "latencia_2a_ms": round((t2 - t1) * 1000, 1), "ok": row_ok}
            print(f"   {'OK   ' if row_ok else 'FALLA'} {qid:<12} filas={n}/{len(ref)} {match}  sesión={e.session_info()}"
                  f"  ({out['queries'][qid]['latencia_1a_ms']} ms, luego {out['queries'][qid]['latencia_2a_ms']} ms)")

    q1 = targets["Q1"]
    with make_engine(q1, timeout_s=0.001) as e:
        try:
            e.execute()
            raised, msg = False, "no lanzó QueryTimeout"
        except QueryTimeout as exc:
            raised, msg = True, str(exc)[:200]
        # ¿Sigue viva la conexión tras el timeout?
        if engine == "mongodb":
            alive = e.coll.estimated_document_count() > 0
        else:
            alive = e.conn.execute("SELECT 1").fetchone()[0] == 1
        out["timeout"] = {"timeout_s": 0.001, "sesion": e.session_info(), "lanzo_QueryTimeout": raised,
                          "mensaje": msg, "conexion_sigue_viva": alive}
    ok &= raised and alive
    print(f"   {'OK   ' if raised and alive else 'FALLA'} timeout 1 ms en Q1: QueryTimeout={raised}, conexión viva={alive} — {msg[:110]}")

    out["ok"] = ok
    dest = ROOT / "results" / "f5" / "f5_3" / f"adapters_{engine}.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(out, ensure_ascii=False, indent=2, default=str) + "\n")
    print(f"   {'RESULTADO: OK' if ok else 'RESULTADO: FALLA'} -> {dest.relative_to(ROOT)}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
