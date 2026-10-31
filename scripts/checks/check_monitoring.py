#!/usr/bin/env python3
"""check_monitoring.py — ¿responde el monitoreo, mide de verdad cada 1 s y cuánto cuesta? (F6.1)

Uso (monitoreo arriba con scripts/up_monitoring.sh; un motor arriba es opcional):
    .venv/bin/python scripts/checks/check_monitoring.py --segundos 60 --etiqueta reposo

Qué comprueba, durante `--segundos`:
  1. up==1 de los tres jobs (prometheus, cadvisor, node) y la duración de cada scrape.
  2. Resolución real: para cada contenedor bench_*/benchmon_*, cuántas muestras
     DISTINTAS guardó Prometheus de container_cpu_usage_seconds_total y
     container_memory_rss, y cada cuánto. Si cAdvisor repitiera lecturas (F6-d),
     habría muchas menos muestras que segundos, o valores repetidos.
  3. Consumo del propio monitoreo, leído del cgroup DESDE FUERA (igual que el
     runner, benchmark_runner/metrics/cgroup.py), no de Prometheus: núcleos
     medios (Δ usage_usec ÷ tiempo) y memoria máxima (anon y memory.current),
     más MemAvailable de la VM al inicio y al final.
  4. Que existan las series que usa el experimento (R-24 y playbook §7).

Es una verificación, no una medición: no escribe en ningún CSV.
Salida: results/f6/f6_1/check_monitoring_<etiqueta>_<sello>.json
"""

from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from benchmark_runner.metrics.cgroup import Cgroup  # noqa: E402

PROM = "http://127.0.0.1:9090"
JOBS = ("prometheus", "cadvisor", "node")
# Series que el experimento necesita (R-24: throttling y rss; playbook §7: I/O, disco, swap del host).
REQUIRED = {
    "cadvisor": ["container_cpu_cfs_throttled_seconds_total", "container_cpu_cfs_throttled_periods_total",
                 "container_cpu_usage_seconds_total", "container_memory_rss", "container_memory_working_set_bytes"],
    "node": ["node_memory_MemAvailable_bytes", "node_memory_SwapFree_bytes", "node_disk_read_bytes_total",
             "node_disk_written_bytes_total", "node_vmstat_pswpin", "node_vmstat_pswpout",
             "node_pressure_memory_waiting_seconds_total"],
}


def prom(path: str, **params) -> dict:
    url = f"{PROM}{path}?{urllib.parse.urlencode(params)}"
    with urllib.request.urlopen(url, timeout=10) as r:
        body = json.load(r)
    if body.get("status") != "success":
        raise RuntimeError(f"Prometheus respondió {body.get('status')}: {body.get('error')}")
    return body["data"]


def containers() -> dict[str, str]:
    """nombre → id completo de los contenedores del experimento que están corriendo."""
    out = subprocess.run(["docker", "ps", "--no-trunc", "--format", "{{.Names}} {{.ID}}"],
                         capture_output=True, text=True, check=True).stdout
    pairs = (line.split() for line in out.splitlines() if line.strip())
    return {n: i for n, i in pairs if n.startswith(("bench_", "benchmon_"))}


def mem_available_kib() -> int:
    for line in Path("/proc/meminfo").read_text().splitlines():
        if line.startswith("MemAvailable:"):
            return int(line.split()[1])
    raise RuntimeError("sin MemAvailable en /proc/meminfo")


def targets() -> dict:
    data = prom("/api/v1/targets", state="active")
    return {t["labels"]["job"]: {"health": t["health"], "lastError": t["lastError"],
                                 "lastScrapeDuration_s": round(t["lastScrapeDuration"], 4),
                                 "scrapeInterval": t.get("scrapeInterval")}
            for t in data["activeTargets"]}


def resolution(metric: str, cid: str, seconds: int) -> dict:
    """Muestras guardadas en los últimos `seconds` s para el cgroup /docker/<cid>."""
    res = prom("/api/v1/query", query=f'{metric}{{id="/docker/{cid}"}}[{seconds}s]')["result"]
    if not res:
        return {"series": 0}
    # Con varias series (p. ej. por CPU) basta la primera: todas salen del mismo housekeeping.
    vals = res[0]["values"]
    ts = [float(t) for t, _ in vals]
    gaps = [b - a for a, b in zip(ts, ts[1:])]
    return {"series": len(res), "muestras": len(vals), "valores_distintos": len({v for _, v in vals}),
            "paso_mediano_s": round(statistics.median(gaps), 3) if gaps else None,
            "paso_max_s": round(max(gaps), 3) if gaps else None}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--segundos", type=int, default=60)
    ap.add_argument("--etiqueta", default="reposo")
    ap.add_argument("--fase", default="f6_1", help="subcarpeta de results/f6/ donde queda la evidencia")
    args = ap.parse_args()

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    names = containers()
    cgs = {n: Cgroup(i) for n, i in names.items()}
    out: dict = {"descripcion": "verificación del monitoreo (F6.1); no es una medición del benchmark",
                 "etiqueta": args.etiqueta, "sello": stamp, "segundos": args.segundos,
                 "contenedores": names, "targets_inicio": targets(),
                 "mem_available_vm_mib_inicio": round(mem_available_kib() / 1024, 1)}

    start = {n: cg.snapshot() for n, cg in cgs.items()}
    peak = {n: {"anon": 0, "memory_current": 0} for n in cgs}
    t0 = time.monotonic()
    while time.monotonic() - t0 < args.segundos:
        for n, cg in cgs.items():
            peak[n]["anon"] = max(peak[n]["anon"], cg.anon_bytes())
            peak[n]["memory_current"] = max(peak[n]["memory_current"], int(cg.read("memory.current")))
        time.sleep(1)
    elapsed = time.monotonic() - t0
    end = {n: cg.snapshot() for n, cg in cgs.items()}

    out["mem_available_vm_mib_fin"] = round(mem_available_kib() / 1024, 1)
    out["targets_fin"] = targets()
    out["consumo_cgroup"] = {
        n: {"nucleos_medios": round((end[n]["usage_usec"] - start[n]["usage_usec"]) / 1e6 / elapsed, 4),
            "anon_max_mib": round(peak[n]["anon"] / 2**20, 1),
            "memory_current_max_mib": round(peak[n]["memory_current"] / 2**20, 1),
            "throttled_s": round((end[n]["throttled_usec"] - start[n]["throttled_usec"]) / 1e6, 3)}
        for n in cgs}
    mon = [v for n, v in out["consumo_cgroup"].items() if n.startswith("benchmon_")]
    out["monitoreo_total"] = {"nucleos_medios": round(sum(v["nucleos_medios"] for v in mon), 4),
                              "memory_current_max_mib": round(sum(v["memory_current_max_mib"] for v in mon), 1)}
    window = max(10, args.segundos - 2)
    out["resolucion"] = {n: {m: resolution(m, i, window)
                             for m in ("container_cpu_usage_seconds_total", "container_memory_rss")}
                         for n, i in names.items()}
    out["series_requeridas"] = {job: {m: len(prom("/api/v1/query", query=m)["result"]) for m in ms}
                                for job, ms in REQUIRED.items()}

    up_ok = all(out[k].get(j, {}).get("health") == "up" for k in ("targets_inicio", "targets_fin") for j in JOBS)
    res_ok = all(r["container_cpu_usage_seconds_total"].get("muestras", 0) >= window - 2
                 and (r["container_cpu_usage_seconds_total"].get("paso_max_s") or 99) <= 2.5
                 for r in out["resolucion"].values())
    series_ok = all(c > 0 for ms in out["series_requeridas"].values() for c in ms.values())
    # `up` sigue en 1 aunque falle un colector de node_exporter (F6.3: "filesystem" falló en
    # todos los scrapes y acabó en OOM sin que up lo delatara). Se exige que no falle ninguno.
    failed = prom("/api/v1/query", query=f"min_over_time(node_scrape_collector_success[{window}s]) == 0")["result"]
    out["colectores_node_con_fallos"] = sorted(r["metric"]["collector"] for r in failed)
    out["scrape_max_s"] = {r["metric"]["job"]: round(float(r["value"][1]), 4) for r in
                           prom("/api/v1/query", query=f"max_over_time(scrape_duration_seconds[{window}s])")["result"]}
    out["comprobaciones"] = {"up_3_de_3_inicio_y_fin": up_ok, "resolucion_1s": res_ok, "series_presentes": series_ok,
                             "colectores_node_sin_fallos": not failed}

    dest = ROOT / "results" / "f6" / args.fase / f"check_monitoring_{args.etiqueta}_{stamp}.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n")
    print(json.dumps({k: out[k] for k in ("comprobaciones", "colectores_node_con_fallos", "scrape_max_s", "monitoreo_total", "consumo_cgroup", "resolucion",
                                          "series_requeridas", "mem_available_vm_mib_inicio",
                                          "mem_available_vm_mib_fin")}, indent=1, ensure_ascii=False))
    print(f"-> {dest.relative_to(ROOT)}")
    return 0 if all(out["comprobaciones"].values()) else 1


if __name__ == "__main__":
    sys.exit(main())
