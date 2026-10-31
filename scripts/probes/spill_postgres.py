#!/usr/bin/env python3
"""spill_postgres.py — sonda: ¿detecta el runner un volcado a disco de Postgres? (F6.3, PLAN F6)

Uso (sin sudo; levanta Postgres con el perfil, baja cualquier otro motor):
    .venv/bin/python scripts/probes/spill_postgres.py --perfil c_severe

ESTO ES UNA SONDA, NO UN RESULTADO DEL BENCHMARK: no produce filas del CSV.

La consulta sonda es Q2 leída de queries/postgres/q2_sort_topk.sql con el
`LIMIT 1000` quitado (se comprueba que está antes de quitarlo): ordena las
~175 000 filas filtradas en vez de quedarse con las 1 000 primeras, con
work_mem = 4MB (variante MEM_LOW). No vive en queries/ y no cambia Q2.

Dos ventanas, cada una con los mismos detectores que el runner
(EngineProbe.read → pg_stat_database.temp_files/temp_bytes, A6):
  1. control negativo: Q2 tal cual, 3 veces → NO debe haber volcado (F4: Q2 no vuelca);
  2. sonda: Q2 sin LIMIT, 3 veces → DEBE haber volcado.
Después, fuera de las ventanas, EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) de cada
una, para confirmar el volcado por otra vía ("Sort Method": "external merge").
El clasificador del runner (assemble_row) da la fila que produciría cada ventana.

Pasa si: temp_bytes > 0 en la sonda, = 0 en el control; el EXPLAIN de la sonda
muestra ordenamiento externo y el del control no; status = spill en la sonda y
ok en el control.
Salida: results/f6/probes/spill_postgres_<perfil>_<sello>.json
"""

from __future__ import annotations

import argparse
import re
import sys
import time

import probe_common as pc
from benchmark_runner.env import load_env
from benchmark_runner.metrics import spill
from benchmark_runner.metrics.cgroup import AnonSampler
from benchmark_runner.runner import EngineProbe

Q2_FILE = pc.ROOT / "queries" / "postgres" / "q2_sort_topk.sql"
REPS = 3
STATS_FLUSH_S = 2   # pg_stat_database se actualiza al terminar la transacción; margen antes de leer


def sort_nodes(plan: dict) -> list[dict]:
    out = []
    if "Sort Method" in plan:
        out.append({k: plan.get(k) for k in ("Node Type", "Sort Method", "Sort Space Used", "Sort Space Type",
                                              "Workers")})
    for child in plan.get("Plans", []):
        out.extend(sort_nodes(child))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--perfil", default="c_severe", choices=list(pc.PROFILE_ID))
    args = ap.parse_args()

    import psycopg
    q2 = Q2_FILE.read_text()
    if not re.search(r"\bLIMIT\s+1000\s*;\s*$", q2):
        sys.exit(f"{Q2_FILE} ya no termina en 'LIMIT 1000;': revisar la sonda")
    probe_sql = re.sub(r"\s*\bLIMIT\s+1000\s*;\s*$", ";", q2)

    st = pc.stamp()
    cg = pc.engine_up(args.perfil, "postgresql")
    env = load_env()
    probe = EngineProbe("postgresql", env)
    conn = psycopg.connect(host="127.0.0.1", port=5432, dbname=env["POSTGRES_DB"], user=env["POSTGRES_USER"],
                           password=env["POSTGRES_PASSWORD"], autocommit=True)
    conn.execute("SET work_mem = '4MB'")
    work_mem = conn.execute("SHOW work_mem").fetchone()[0]

    def run_window(label: str, sql: str) -> dict:
        start = pc.edge(cg, probe.read)
        sampler = AnonSampler(cg, 1.0)
        sampler.start()
        rows = []
        samples = [pc.timed(lambda: rows.append(len(conn.execute(sql).fetchall()))) for _ in range(REPS)]
        time.sleep(STATS_FLUSH_S)
        sampler.stop()
        end = pc.edge(cg, probe.read)
        d = spill.counter_delta(start["spill"], end["spill"])
        row, reasons, state = pc.classify("postgresql", args.perfil, label, start, end, samples, sampler, bool(d))
        return {"filas_devueltas": rows, "latencias_ms": [round(s.latency_ms, 1) for s in samples],
                "spill_inicio": start["spill"], "spill_fin": end["spill"], "spill_delta": d,
                "fila_del_clasificador_NO_ES_DEL_CSV": row, "motivos": reasons, "estado_contenedor": state}

    control = run_window("SPILL_CONTROL_Q2", q2)
    probe_w = run_window("SPILL_Q2_SIN_LIMIT", probe_sql)

    def explain(sql: str) -> dict:
        plan = conn.execute("EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + sql.rstrip().rstrip(";")).fetchone()[0][0]
        top = plan["Plan"]
        return {"ordenamientos": sort_nodes(top), "temp_written_blocks_raiz": top.get("Temp Written Blocks"),
                "plan_completo": plan}

    control["explain"], probe_w["explain"] = explain(q2), explain(probe_sql)
    conn.close()
    probe.close()

    ext = lambda w: any("external" in (n["Sort Method"] or "") for n in w["explain"]["ordenamientos"])  # noqa: E731
    checks = {
        "sonda_temp_bytes_>0": probe_w["spill_delta"].get("temp_bytes", 0) > 0,
        "control_sin_volcado": not control["spill_delta"],
        "sonda_explain_ordenamiento_externo": ext(probe_w),
        "control_explain_sin_ordenamiento_externo": not ext(control),
        "sonda_status_spill": probe_w["fila_del_clasificador_NO_ES_DEL_CSV"]["status"] == "spill",
        "sonda_disk_spill_true": probe_w["fila_del_clasificador_NO_ES_DEL_CSV"]["disk_spill"] is True,
        "control_status_ok": control["fila_del_clasificador_NO_ES_DEL_CSV"]["status"] == "ok",
    }
    out = {"descripcion": "sonda de spill en Postgres (F6.3); NO es una medición ni una fila del CSV",
           "perfil": pc.PROFILE_ID[args.perfil], "sello": st, "work_mem": work_mem, "repeticiones": REPS,
           "consulta_control": q2, "consulta_sonda": probe_sql,
           "limites_cgroup": {n: cg.read(n).strip() for n in ("cpu.max", "memory.max")},
           "control": control, "sonda": probe_w, "comprobaciones": checks}
    dest = pc.save(f"spill_postgres_{args.perfil}_{st}", out)
    for name, w in (("control", control), ("sonda", probe_w)):
        r = w["fila_del_clasificador_NO_ES_DEL_CSV"]
        print(f"== {name}: filas={w['filas_devueltas']} latencias={w['latencias_ms']} ms  spill_delta={w['spill_delta']}"
              f"  explain={w['explain']['ordenamientos']}  → status={r['status']} disk_spill={r['disk_spill']}")
    print(checks)
    print(f"-> {dest.relative_to(pc.ROOT)}")
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
