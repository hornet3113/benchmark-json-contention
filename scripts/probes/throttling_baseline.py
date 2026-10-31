#!/usr/bin/env python3
"""throttling_baseline.py — throttling del motor EN REPOSO, por perfil y motor (F6.3, pedido de Alix).

Uso (monitoreo opcional; sin sudo; levanta y baja cada motor, solo uno a la vez):
    .venv/bin/python scripts/probes/throttling_baseline.py
    .venv/bin/python scripts/probes/throttling_baseline.py --perfiles c_severe --motores mongo

ESTO ES UNA SONDA, NO UN RESULTADO DEL BENCHMARK: no corre Q1 ni Q2 y no produce
filas del CSV. Sirve para declarar qué parte de `cpu_throttled_seconds` NO la
causa el benchmark: en F6.2, Mongo en PROFILE_C acumuló ~4 s de throttling por
minuto sin ninguna consulta (docs/F6_TELEMETRIA.md).

Imita la secuencia de una repetición real, sin consultas: up_profile.sh →
healthy → "calentamiento" de `--calentamiento` s → ventana de `--ventana` s
(300 s, como la de medición, para que el número se compare directo con la
columna). Diferencia declarada: no hay flush de caché (necesitaría sudo); en
reposo el motor no lee datos, así que no debería importar.

Mide, desde fuera del contenedor (benchmark_runner/metrics/cgroup.py, igual que
el runner): Δ throttled_usec, Δ nr_throttled, Δ nr_periods y Δ usage_usec en el
calentamiento y en la ventana, más la serie de 1 s de la ventana (para ver si el
throttling viene en ráfagas periódicas, p. ej. checkpoints). Registra loadavg y
MemAvailable de la VM antes y después: ruido del host.

Salida: results/f6/f6_3/baseline/<motor>_<perfil>_<sello>.json y resumen_<sello>.json
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from benchmark_runner.metrics.cgroup import SAMPLE_COLUMNS, AnonSampler, Cgroup  # noqa: E402

CONTAINER = {"postgres": "bench_postgres", "mongo": "bench_mongo"}
PROFILE_ID = {"a_baseline": "PROFILE_A_BASELINE", "b_medium": "PROFILE_B_MEDIUM", "c_severe": "PROFILE_C_SEVERE"}


def host() -> dict:
    mem = {l.split(":")[0]: int(l.split()[1]) for l in Path("/proc/meminfo").read_text().splitlines()
           if l.startswith(("MemAvailable:", "SwapFree:", "SwapTotal:"))}
    return {"loadavg": Path("/proc/loadavg").read_text().split()[:3],
            "mem_available_mib": round(mem["MemAvailable"] / 1024, 1),
            "swap_usada_mib": round((mem["SwapTotal"] - mem["SwapFree"]) / 1024, 1)}


def diff(a: dict, b: dict, seconds: float) -> dict:
    d = {k: b[k] - a[k] for k in ("throttled_usec", "nr_throttled", "nr_periods", "usage_usec")}
    return {"segundos": round(seconds, 3), "throttled_s": round(d["throttled_usec"] / 1e6, 6),
            "throttled_s_por_minuto": round(d["throttled_usec"] / 1e6 / seconds * 60, 4),
            "nr_throttled": d["nr_throttled"], "nr_periods": d["nr_periods"],
            "periodos_con_throttling_pct": round(100 * d["nr_throttled"] / d["nr_periods"], 2) if d["nr_periods"] else None,
            "nucleos_medios": round(d["usage_usec"] / 1e6 / seconds, 4)}


def one(profile: str, engine: str, warmup: int, window: int, stamp: str) -> dict:
    up = subprocess.run([str(ROOT / "scripts" / "up_profile.sh"), profile, engine], capture_output=True, text=True)
    if up.returncode != 0:
        return {"perfil": PROFILE_ID[profile], "motor": engine, "error": (up.stdout + up.stderr)[-800:]}
    t_healthy = time.monotonic()
    cid = subprocess.run(["docker", "inspect", "-f", "{{.Id}}", CONTAINER[engine]],
                         capture_output=True, text=True, check=True).stdout.strip()
    cg = Cgroup(cid)
    limits = {n: cg.read(n).strip() for n in ("cpu.max", "memory.max", "memory.swap.max", "cpuset.cpus")}
    h0 = host()
    s0 = cg.snapshot()
    time.sleep(warmup)
    s1, t1 = cg.snapshot(), time.monotonic()
    sampler = AnonSampler(cg, 1.0)
    sampler.start()
    time.sleep(window)
    sampler.stop()
    s2, t2 = cg.snapshot(), time.monotonic()
    out = {"perfil": PROFILE_ID[profile], "motor": engine, "sello": stamp, "container_id": cid,
           "limites_cgroup": limits, "host_inicio": h0, "host_fin": host(),
           "calentamiento": diff(s0, s1, t1 - t_healthy), "ventana": diff(s1, s2, t2 - t1),
           "oom_kill_delta": s2["oom_kill"] - s0["oom_kill"],
           "serie_cgroup_1s": {"columnas": list(SAMPLE_COLUMNS), "filas": [list(r) for r in sampler.samples]}}
    i = SAMPLE_COLUMNS.index("throttled_usec")
    per_s = [(b[i] - a[i]) / 1e6 for a, b in zip(sampler.samples, sampler.samples[1:])]
    out["ventana"]["segundos_con_throttling"] = sum(1 for x in per_s if x > 0)
    out["ventana"]["max_throttled_s_en_1s"] = round(max(per_s), 4) if per_s else None
    dest = ROOT / "results" / "f6" / "f6_3" / "baseline" / f"{engine}_{profile}_{stamp}.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(out, ensure_ascii=False) + "\n")
    print(f"   {engine:<8} {PROFILE_ID[profile]:<19} ventana: {out['ventana']['throttled_s']:>8.3f} s throttling "
          f"({out['ventana']['throttled_s_por_minuto']} s/min, {out['ventana']['segundos_con_throttling']} s con throttling, "
          f"{out['ventana']['nucleos_medios']} núcleos)  calentamiento: {out['calentamiento']['throttled_s']:.3f} s", flush=True)
    return {k: out[k] for k in ("perfil", "motor", "limites_cgroup", "calentamiento", "ventana", "oom_kill_delta",
                                "host_inicio", "host_fin")} | {"archivo": str(dest.relative_to(ROOT))}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--perfiles", nargs="+", default=list(PROFILE_ID), choices=list(PROFILE_ID))
    ap.add_argument("--motores", nargs="+", default=["postgres", "mongo"], choices=list(CONTAINER))
    ap.add_argument("--calentamiento", type=int, default=60)
    ap.add_argument("--ventana", type=int, default=300)
    args = ap.parse_args()

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    print(f"== línea base de throttling en reposo — {stamp} — calentamiento {args.calentamiento} s, ventana {args.ventana} s",
          flush=True)
    rows = []
    try:
        for profile in args.perfiles:
            for engine in args.motores:
                rows.append(one(profile, engine, args.calentamiento, args.ventana, stamp))
    finally:
        subprocess.run([str(ROOT / "scripts" / "down_profile.sh")], capture_output=True)
    summary = {"descripcion": "línea base de throttling en reposo (F6.3); sonda, no medición del benchmark",
               "sello": stamp, "calentamiento_s": args.calentamiento, "ventana_s": args.ventana,
               "sin_flush": True, "combinaciones": rows}
    dest = ROOT / "results" / "f6" / "f6_3" / "baseline" / f"resumen_{stamp}.json"
    dest.write_text(json.dumps(summary, ensure_ascii=False, indent=1) + "\n")
    print(f"-> {dest.relative_to(ROOT)}")
    return 0 if all("error" not in r for r in rows) else 1


if __name__ == "__main__":
    sys.exit(main())
