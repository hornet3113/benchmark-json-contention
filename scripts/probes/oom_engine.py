#!/usr/bin/env python3
"""oom_engine.py — sonda: ¿clasifica el runner como `oom` un OOM dentro del contenedor del motor? (F6.3)

Uso (sin sudo; levanta el motor con PROFILE_C, baja cualquier otro):
    .venv/bin/python scripts/probes/oom_engine.py --motor postgresql

ESTO ES UNA SONDA, NO UN RESULTADO DEL BENCHMARK: no produce filas del CSV.

Diferencia con scripts/probes/oom_profile_c.sh (F1): aquella usa un contenedor
desechable y solo demuestra que el kernel aplica memory.max. Esta lo hace DENTRO
del contenedor del motor y pasa las lecturas por el clasificador del runner
(assemble_row), que es lo que pide PLAN F6: "el runner lo clasifica como
status=oom".

Cómo: entre dos bordes (reloj + cgroup, como el runner), unas consultas
triviales al motor y luego `docker exec <motor> sh -c "head -c 2G /dev/zero | tail"`.
/dev/zero no tiene saltos de línea, así que `tail` acumula la "línea" en
memoria hasta pasar de memory.max (1 GiB, sin swap) y el kernel mata al
proceso más grande del cgroup, que es `tail` (el motor en reposo ocupa mucho
menos). Si el elegido fuera el propio motor, el contenedor muere y queda
OOMKilled=true: también es `oom` para el clasificador, y se registra cuál pasó.

Pasa si: Δ oom_kill ≥ 1 en memory.events y status = oom.
Salida: results/f6/probes/oom_engine_<motor>_<sello>.json
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time

import probe_common as pc
from benchmark_runner.env import load_env
from benchmark_runner.lifecycle import CONTAINER
from benchmark_runner.metrics.cgroup import AnonSampler

ALLOC = "2G"


def trivial_query(engine: str, env: dict):
    if engine == "postgresql":
        import psycopg
        conn = psycopg.connect(host="127.0.0.1", port=5432, dbname=env["POSTGRES_DB"], user=env["POSTGRES_USER"],
                               password=env["POSTGRES_PASSWORD"], autocommit=True, connect_timeout=10)
        return (lambda: conn.execute("SELECT count(*) FROM orders WHERE false").fetchone()), conn.close
    from pymongo import MongoClient
    client = MongoClient("mongodb://127.0.0.1:27017", maxPoolSize=1, serverSelectionTimeoutMS=10000)
    return (lambda: client[env["MONGO_DB"]].command("ping")), client.close


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--motor", required=True, choices=["postgresql", "mongodb"])
    args = ap.parse_args()

    st = pc.stamp()
    cg = pc.engine_up("c_severe", args.motor)
    limits = {n: cg.read(n).strip() for n in ("memory.max", "memory.swap.max")}
    query, close = trivial_query(args.motor, load_env())
    start = pc.edge(cg)
    events_start = cg.read("memory.events")
    sampler = AnonSampler(cg, 1.0)
    sampler.start()
    samples = [pc.timed(query) for _ in range(3)]
    t0 = time.monotonic()
    hog = subprocess.run(["docker", "exec", CONTAINER[args.motor], "sh", "-c", f"head -c {ALLOC} /dev/zero | tail"],
                         capture_output=True, text=True, timeout=300)
    hog_s = time.monotonic() - t0
    time.sleep(2)
    samples += [pc.timed(query) for _ in range(3)]   # ¿sigue respondiendo el motor?
    sampler.stop()
    try:
        end = pc.edge(cg)
        events_end = cg.read("memory.events")
    except OSError as exc:      # el contenedor murió: el cgroup desapareció
        end = {"clock": pc.window.snapshot(), "cgroup": {}}
        events_end = f"(sin lectura: {exc})"
    try:
        close()
    except Exception:  # noqa: BLE001
        pass
    row, reasons, state = pc.classify(args.motor, "c_severe", "OOM", start, end, samples, sampler, False)

    oom_delta = (end["cgroup"].get("oom_kill") or 0) - (start["cgroup"].get("oom_kill") or 0)
    checks = {"oom_kill_delta_>=1": oom_delta >= 1 or bool(state.get("OOMKilled")),
              "status_oom": row["status"] == "oom"}
    out = {"descripcion": "sonda de OOM dentro del contenedor del motor (F6.3); NO es una medición ni una fila del CSV",
           "motor": args.motor, "perfil": "PROFILE_C_SEVERE", "sello": st, "limites_cgroup": limits,
           "carga": f"docker exec {CONTAINER[args.motor]} sh -c 'head -c {ALLOC} /dev/zero | tail'",
           "carga_exit_code": hog.returncode, "carga_segundos": round(hog_s, 2), "carga_stderr": hog.stderr[-300:],
           "memory_events_inicio": events_start, "memory_events_fin": events_end, "oom_kill_delta": oom_delta,
           "anon_max_mib": sampler.max_mib, "consultas": [s.kind for s in samples],
           "estado_contenedor": state, "fila_del_clasificador_NO_ES_DEL_CSV": row, "motivos": reasons,
           "comprobaciones": checks}
    dest = pc.save(f"oom_engine_{args.motor}_{st}", out)
    print(f"== carga exit={hog.returncode} en {hog_s:.1f} s · oom_kill +{oom_delta} · estado={state} · "
          f"consultas={out['consultas']}")
    print(f"== fila: status={row['status']} cpu_throttled_seconds={row['cpu_throttled_seconds']} "
          f"max_rss_mb={row['max_rss_mb']} · motivos={reasons}")
    print(checks)
    print(f"-> {dest.relative_to(pc.ROOT)}")
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
