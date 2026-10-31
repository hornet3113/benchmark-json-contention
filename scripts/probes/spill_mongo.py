#!/usr/bin/env python3
"""spill_mongo.py — sonda: ¿detecta el runner un volcado a disco de MongoDB? (F6.3, PLAN F6)

Uso (sin sudo; levanta Mongo con el perfil, baja cualquier otro motor):
    .venv/bin/python scripts/probes/spill_mongo.py --perfil c_severe

ESTO ES UNA SONDA, NO UN RESULTADO DEL BENCHMARK: no produce filas del CSV.

El pipeline sonda es Q2 leído de queries/mongo/q2_sort_topk.json con el
`$limit` y el `$project` quitados (se comprueba que están antes de quitarlos),
con allowDiskUse: true:
  - sin `$limit`, el `$sort` no es top-k: tiene que ordenar las ~175 000
    filas filtradas;
  - sin `$project`: con él, Mongo solo arrastra los 3 campos proyectados
    (~17 MB en total) y nunca llega a su límite de 100 MB de ordenamiento en
    memoria; sin él ordena documentos completos (~1 KB cada uno, ~175 MB).
No vive en queries/ y no cambia Q2.

Dos ventanas, cada una con los mismos detectores que el runner (EngineProbe.read
→ todos los contadores de serverStatus cuyo nombre contiene "spill", A6):
  1. control negativo: Q2 tal cual (con allowDiskUse: true), 3 veces → sin volcado;
  2. sonda: el pipeline sonda, 3 veces → con volcado.
Después, fuera de las ventanas, explain executionStats de cada una para
confirmar por otra vía (usedDisk / spills en la etapa de ordenamiento).

Pasa si: algún contador de spill sube en la sonda y ninguno en el control; el
explain de la sonda marca disco y el del control no; status = spill en la sonda
y ok en el control.
Salida: results/f6/probes/spill_mongo_<perfil>_<sello>.json
"""

from __future__ import annotations

import argparse
import json
import sys
import time

import probe_common as pc
from benchmark_runner.env import load_env
from benchmark_runner.metrics import spill
from benchmark_runner.metrics.cgroup import AnonSampler
from benchmark_runner.runner import EngineProbe

Q2_FILE = pc.ROOT / "queries" / "mongo" / "q2_sort_topk.json"
REPS = 3


def disk_marks(doc, path: str = "") -> list[dict]:
    """Toda clave del explain que hable de disco o spill, con su ruta (los nombres cambian entre versiones)."""
    out = []
    if isinstance(doc, dict):
        for k, v in doc.items():
            p = f"{path}.{k}" if path else k
            kl = k.lower()
            if ("useddisk" in kl or "spill" in kl) and not isinstance(v, (dict, list)):
                out.append({"ruta": p, "valor": v})
            out.extend(disk_marks(v, p))
    elif isinstance(doc, list):
        for i, v in enumerate(doc):
            out.extend(disk_marks(v, f"{path}[{i}]"))
    return out


def used_disk(marks: list[dict]) -> bool:
    return any(m["valor"] is True or (isinstance(m["valor"], (int, float)) and not isinstance(m["valor"], bool)
                                      and m["valor"] > 0) for m in marks)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--perfil", default="c_severe", choices=list(pc.PROFILE_ID))
    args = ap.parse_args()

    from bson.son import SON
    from pymongo import MongoClient
    q2 = json.loads(Q2_FILE.read_text())
    stages = [next(iter(s)) for s in q2]
    if stages != ["$match", "$sort", "$limit", "$project"]:
        sys.exit(f"{Q2_FILE} ya no es $match/$sort/$limit/$project ({stages}): revisar la sonda")
    probe_pipeline = [s for s in q2 if next(iter(s)) not in ("$limit", "$project")]

    st = pc.stamp()
    cg = pc.engine_up(args.perfil, "mongodb")
    env = load_env()
    probe = EngineProbe("mongodb", env)
    client = MongoClient("mongodb://127.0.0.1:27017", maxPoolSize=1)
    db = client[env["MONGO_DB"]]

    def run_window(label: str, pipeline: list) -> dict:
        start = pc.edge(cg, probe.read)
        sampler = AnonSampler(cg, 1.0)
        sampler.start()
        counts = []
        samples = [pc.timed(lambda: counts.append(sum(1 for _ in db.orders.aggregate(pipeline, allowDiskUse=True))))
                   for _ in range(REPS)]
        time.sleep(1)
        sampler.stop()
        end = pc.edge(cg, probe.read)
        d = spill.counter_delta(start["spill"], end["spill"])
        row, reasons, state = pc.classify("mongodb", args.perfil, label, start, end, samples, sampler, bool(d))
        return {"documentos_devueltos": counts, "latencias_ms": [round(s.latency_ms, 1) for s in samples],
                "contadores_spill_vistos": sorted(start["spill"]), "spill_delta": d,
                "fila_del_clasificador_NO_ES_DEL_CSV": row, "motivos": reasons, "estado_contenedor": state}

    control = run_window("SPILL_CONTROL_Q2", q2)
    probe_w = run_window("SPILL_Q2_SIN_LIMIT_NI_PROJECT", probe_pipeline)

    def explain(pipeline: list) -> dict:
        cmd = SON([("aggregate", "orders"), ("pipeline", pipeline), ("cursor", {}), ("allowDiskUse", True)])
        plan = db.command("explain", cmd, verbosity="executionStats")
        marks = disk_marks(plan)
        return {"marcas_de_disco": marks, "usa_disco": used_disk(marks), "plan_completo": plan}

    control["explain"], probe_w["explain"] = explain(q2), explain(probe_pipeline)
    client.close()
    probe.close()

    checks = {
        "sonda_contador_spill_>0": bool(probe_w["spill_delta"]),
        "control_sin_volcado": not control["spill_delta"],
        "sonda_explain_usa_disco": probe_w["explain"]["usa_disco"],
        "control_explain_sin_disco": not control["explain"]["usa_disco"],
        "sonda_status_spill": probe_w["fila_del_clasificador_NO_ES_DEL_CSV"]["status"] == "spill",
        "sonda_disk_spill_true": probe_w["fila_del_clasificador_NO_ES_DEL_CSV"]["disk_spill"] is True,
        "control_status_ok": control["fila_del_clasificador_NO_ES_DEL_CSV"]["status"] == "ok",
    }
    out = {"descripcion": "sonda de spill en MongoDB (F6.3); NO es una medición ni una fila del CSV",
           "perfil": pc.PROFILE_ID[args.perfil], "sello": st, "repeticiones": REPS, "allowDiskUse": True,
           "pipeline_control": q2, "pipeline_sonda": probe_pipeline,
           "limites_cgroup": {n: cg.read(n).strip() for n in ("cpu.max", "memory.max")},
           "control": control, "sonda": probe_w, "comprobaciones": checks}
    dest = pc.save(f"spill_mongo_{args.perfil}_{st}", out)
    for name, w in (("control", control), ("sonda", probe_w)):
        r = w["fila_del_clasificador_NO_ES_DEL_CSV"]
        print(f"== {name}: docs={w['documentos_devueltos']} latencias={w['latencias_ms']} ms  spill_delta={w['spill_delta']}"
              f"  explain disco={w['explain']['usa_disco']} {w['explain']['marcas_de_disco'][:6]}"
              f"  → status={r['status']} disk_spill={r['disk_spill']}")
    print(checks)
    print(f"-> {dest.relative_to(pc.ROOT)}")
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
