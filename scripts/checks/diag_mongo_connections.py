#!/usr/bin/env python3
"""diag_mongo_connections.py — ¿por qué Mongo "ve" 152 conexiones y ~104 consultas con 50 workers? (F5.5)

Uso (Mongo arriba con PROFILE_A; no necesita sudo porque no limpia caché):
    scripts/up_profile.sh a_baseline mongo
    .venv/bin/python scripts/checks/diag_mongo_connections.py

Lanza la celda Q2_MEM_LOW · c=50 (10 procesos × 5 hilos) con ventanas cortas y,
en los bordes de la ventana, guarda los DOCUMENTOS de currentOp (no solo su
conteo) y serverStatus().connections, para saber qué es cada conexión y cada
operación. Es un diagnóstico, no una medición: no escribe en ningún CSV.
Salida: results/f5/f5_5/diag_mongo_connections.json
"""

from __future__ import annotations

import collections
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))


def main() -> int:
    from pymongo import MongoClient
    from benchmark_runner import matrix
    from benchmark_runner.config import Windows
    from benchmark_runner.workload import run_load

    cell = next(c for c in matrix.cells(54) if c.engine == "mongodb" and c.query_id == "Q2_MEM_LOW"
                and c.profile == "PROFILE_A_BASELINE" and c.concurrency == 50)
    probe = MongoClient("mongodb://127.0.0.1:27017", maxPoolSize=1)
    snaps = []

    def snap(tag):
        ss = probe.admin.command("serverStatus")["connections"]
        ops = probe.admin.command("currentOp", {"active": True, "ns": "bench.orders"})["inprog"]
        allops = probe.admin.command("currentOp", {"$all": True})["inprog"]
        by_client = collections.Counter(o.get("client") for o in ops)
        s = {
            "momento": tag,
            "serverStatus.connections": {k: ss.get(k) for k in ("current", "active", "available", "totalCreated")},
            "ops_activas_en_bench.orders": len(ops),
            "por_tipo_op_comando": dict(collections.Counter(
                f"type={o.get('type')} op={o.get('op')} cmd={next(iter(o.get('command') or {'-': 0}))}" for o in ops)),
            "clientes_distintos_en_esas_ops": len(by_client),
            "ops_por_cliente": dict(collections.Counter(by_client.values())),
            "todas_las_conexiones_por_comando": dict(collections.Counter(
                f"active={o.get('active')} cmd={next(iter(o.get('command') or {'-': 0}))}" for o in allops
                if o.get("type") == "op")),
            "ejemplos": [{k: o.get(k) for k in ("type", "op", "ns", "desc", "client", "active", "planSummary",
                                                "connectionId", "threaded")} for o in ops[:3]],
        }
        snaps.append(s)
        return s

    r = run_load(cell, Windows(20, 10, 2), ("real", {}), concurrency=50, timeout_s=300,
                 on_window_start=lambda: snap("inicio"), on_window_end=lambda: snap("fin"),
                 grace_s=60, processes=10)
    out = {"descripcion": "diagnóstico del conteo de conexiones y operaciones de Mongo con 50 workers (10×5), PROFILE_A",
           "procesos_x_hilos": [r.processes, r.threads_per_process], "consultas": r.kinds, "snapshots": snaps}
    dest = ROOT / "results" / "f5" / "f5_5" / "diag_mongo_connections.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(out, indent=1, ensure_ascii=False, default=str) + "\n")
    print(json.dumps(out, indent=1, ensure_ascii=False, default=str))
    probe.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
