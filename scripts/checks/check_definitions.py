#!/usr/bin/env python3
"""check_definitions.py — ¿miden cAdvisor/Prometheus lo mismo que el cgroup que lee el runner? (F6.2)

Uso (monitoreo arriba y UN motor arriba, sin sudo):
    scripts/up_profile.sh c_severe postgres
    .venv/bin/python scripts/checks/check_definitions.py --contenedor bench_postgres

Por qué: el CSV sale del cgroup (benchmark_runner/metrics/cgroup.py) y las curvas
del reporte saldrán de Prometheus. Si las dos fuentes no significan lo mismo, las
curvas no ilustrarían las columnas. Según el código de cAdvisor v0.60.6
(lib/container/libcontainer/handler.go:832 y :785), en cgroups v2:
    container_memory_rss                       = memory.stat anon       (lo que usa max_rss_mb)
    container_cpu_cfs_throttled_seconds_total  = cpu.stat throttled_usec / 1e6
Este script lo comprueba con datos, no con el código.

Fases: `--reposo` s sin carga y `--carga` s con carga sintética DENTRO del
contenedor (docker exec): 2 bucles de CPU (contra 1 CPU de cuota en PROFILE_C,
throttling seguro) y una escalera de memoria con dd (200 MB y luego 300 MB,
retenidos ~25 s cada uno). La carga es sintética a propósito: aquí se comparan
dos instrumentos que leen el MISMO cgroup; quién genera la carga no cambia la
definición. Con carga real se ve en el humo de F6.4.

Comparaciones:
  - rss frente a anon, muestra a muestra: para cada muestra de Prometheus (con
    la marca de tiempo de cAdvisor), las dos lecturas propias que la encierran
    (muestreo cada 0.2 s). Si las dos son iguales (anon estable en ese
    intervalo), la comparación es exacta; si no, se informa aparte.
  - working_set frente a memory.current − inactive_file, igual.
  - Throttling, periodos y uso de CPU en la fase de carga (≥ 60 s, F6-h):
    (a) definición: Δ de Prometheus entre su primera y su última muestra frente
        al Δ del cgroup interpolado en esas mismas marcas de tiempo;
    (b) control cruzado del 5 % (PLAN F6): Δ del cgroup entre los bordes de la
        fase, como lo calcula el runner, frente al Δ de Prometheus entre las
        muestras más cercanas a esos bordes.
  - Consumo del monitoreo durante la carga (cgroup, F6-c).

Es una verificación, no una medición: no escribe en ningún CSV.
Salida: results/f6/f6_2/check_definitions_<contenedor>_<sello>.json
"""

from __future__ import annotations

import argparse
import bisect
import json
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from benchmark_runner.metrics.cgroup import Cgroup  # noqa: E402

PROM = "http://127.0.0.1:9090"
SAMPLE_S = 0.2
MAX_REL = 0.05          # PLAN F6: cgroup y Prometheus difieren < 5 %

# Escalera de memoria: (empieza a los s, MB, retiene s). Cabe de sobra en 1 GiB (PROFILE_C).
MEM_STEPS = ((10, 200, 25), (45, 300, 25))


def prom_raw(metric: str, cid: str, t_from: float, t_to: float) -> list[tuple[float, float]]:
    """Muestras crudas (marca de cAdvisor, valor) de la primera serie del cgroup /docker/<cid>."""
    span = int(t_to - t_from) + 1
    q = f'{metric}{{id="/docker/{cid}"}}[{span}s]'
    url = f"{PROM}/api/v1/query?{urllib.parse.urlencode({'query': q, 'time': f'{t_to:.3f}'})}"
    with urllib.request.urlopen(url, timeout=10) as r:
        res = json.load(r)["data"]["result"]
    if not res:
        return []
    return [(float(t), float(v)) for t, v in res[0]["values"] if t_from <= float(t) <= t_to]


class Sampler(threading.Thread):
    """Lecturas propias del cgroup cada SAMPLE_S s, con reloj de pared (el de las marcas de cAdvisor)."""

    def __init__(self, cg: Cgroup):
        super().__init__(daemon=True)
        self.cg, self.rows, self._stop = cg, [], threading.Event()

    def run(self) -> None:
        while not self._stop.is_set():
            t = time.time()
            mem, cpu = self.cg.flat("memory.stat"), self.cg.flat("cpu.stat")
            self.rows.append({"t": t, "anon": mem["anon"], "inactive_file": mem["inactive_file"],
                              "memory_current": int(self.cg.read("memory.current")),
                              "throttled_usec": cpu["throttled_usec"], "nr_throttled": cpu["nr_throttled"],
                              "usage_usec": cpu["usage_usec"]})
            self._stop.wait(SAMPLE_S)

    def stop(self) -> None:
        self._stop.set()
        self.join(timeout=5)


def bracket(rows: list[dict], times: list[float], t: float) -> tuple[dict, dict] | None:
    i = bisect.bisect_left(times, t)
    if i == 0 or i == len(rows):
        return None
    return rows[i - 1], rows[i]


def compare_gauge(prom: list[tuple[float, float]], rows: list[dict], own) -> dict:
    """Muestra a muestra. `own(row)` es el valor propio equivalente."""
    times = [r["t"] for r in rows]
    exact = equal = 0
    max_diff_stable = 0
    unstable = []
    for t, v in prom:
        b = bracket(rows, times, t)
        if b is None:
            continue
        lo, hi = own(b[0]), own(b[1])
        if lo == hi:
            exact += 1
            equal += int(v == lo)
            max_diff_stable = max(max_diff_stable, abs(v - lo))
        else:
            # El valor cambió dentro del intervalo: basta con que caiga entre las dos lecturas.
            unstable.append(min(lo, hi) <= v <= max(lo, hi))
    return {"muestras_prometheus": len(prom), "comparables_exactas": exact, "iguales": equal,
            "max_dif_bytes_en_estables": max_diff_stable,
            "en_transicion": len(unstable), "en_transicion_dentro_del_intervalo": sum(unstable)}


def interp(rows: list[dict], times: list[float], t: float, key: str) -> float | None:
    b = bracket(rows, times, t)
    if b is None:
        return None
    a, c = b
    return a[key] + (c[key] - a[key]) * (t - a["t"]) / (c["t"] - a["t"])


def compare_counter(prom: list[tuple[float, float]], rows: list[dict], key: str, scale: float,
                    t_a: float, t_b: float) -> dict:
    """(a) definición en las marcas de Prometheus; (b) control cruzado en los bordes de la fase."""
    if len(prom) < 2:
        return {"error": "menos de 2 muestras de Prometheus"}
    times = [r["t"] for r in rows]
    (p0t, p0), (p1t, p1) = prom[0], prom[-1]
    own0, own1 = interp(rows, times, p0t, key), interp(rows, times, p1t, key)
    d_prom = p1 - p0
    d_own_same = None if own0 is None or own1 is None else (own1 - own0) / scale
    # (b): como el runner, cgroup en los bordes; Prometheus en sus muestras más cercanas a los bordes.
    ra = min(rows, key=lambda r: abs(r["t"] - t_a))
    rb = min(rows, key=lambda r: abs(r["t"] - t_b))
    pa = min(prom, key=lambda p: abs(p[0] - t_a))
    pb = min(prom, key=lambda p: abs(p[0] - t_b))
    d_runner = (rb[key] - ra[key]) / scale
    d_prom_edges = pb[1] - pa[1]
    rel = lambda x, ref: None if not ref else round(abs(x - ref) / abs(ref), 5)  # noqa: E731
    return {
        "a_definicion": {"delta_prometheus": round(d_prom, 6),
                         "delta_cgroup_mismas_marcas": None if d_own_same is None else round(d_own_same, 6),
                         "dif_relativa": None if d_own_same is None else rel(d_prom, d_own_same),
                         "segundos": round(p1t - p0t, 3)},
        "b_control_cruzado": {"delta_cgroup_bordes": round(d_runner, 6), "delta_prometheus_bordes": round(d_prom_edges, 6),
                              "dif_relativa": rel(d_prom_edges, d_runner),
                              "desfase_bordes_s": [round(pa[0] - ra["t"], 3), round(pb[0] - rb["t"], 3)]},
    }


def monitoring_ids() -> dict[str, str]:
    out = subprocess.run(["docker", "ps", "--no-trunc", "--filter", "name=benchmon_", "--format", "{{.Names}} {{.ID}}"],
                         capture_output=True, text=True, check=True).stdout
    return dict(line.split() for line in out.splitlines() if line.strip())


def exec_bg(container: str, script: str) -> None:
    subprocess.run(["docker", "exec", "-d", container, "sh", "-c", script], check=True)


def phase(name: str, cid: str, rows: list[dict], t_a: float, t_b: float) -> dict:
    rows = [r for r in rows if t_a - 1 <= r["t"] <= t_b + 1]
    g = lambda m: prom_raw(m, cid, t_a, t_b)  # noqa: E731
    out = {"fase": name, "inicio": t_a, "fin": t_b, "segundos": round(t_b - t_a, 3), "lecturas_propias": len(rows),
           "rss_vs_anon": compare_gauge(g("container_memory_rss"), rows, lambda r: r["anon"]),
           "working_set_vs_current_menos_inactive_file": compare_gauge(
               g("container_memory_working_set_bytes"), rows,
               lambda r: max(0, r["memory_current"] - r["inactive_file"])),
           "throttled_seconds": compare_counter(g("container_cpu_cfs_throttled_seconds_total"), rows,
                                                "throttled_usec", 1e6, t_a, t_b),
           "throttled_periods": compare_counter(g("container_cpu_cfs_throttled_periods_total"), rows,
                                                "nr_throttled", 1, t_a, t_b),
           "cpu_usage_seconds": compare_counter(g("container_cpu_usage_seconds_total"), rows, "usage_usec", 1e6, t_a, t_b)}
    cpu = g("container_cpu_usage_seconds_total")
    out["cpu_usage_valores_distintos"] = [len({v for _, v in cpu}), len(cpu)]
    out["anon_max_mib"] = round(max(r["anon"] for r in rows) / 2**20, 1)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--contenedor", required=True, choices=["bench_postgres", "bench_mongo"])
    ap.add_argument("--reposo", type=int, default=60)
    ap.add_argument("--carga", type=int, default=90)
    args = ap.parse_args()
    if args.carga < 60:
        ap.error("--carga debe ser ≥ 60 s (F6-h: con menos, el desfase de los bordes puede pasar del 5 %)")

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    cid = subprocess.run(["docker", "inspect", "-f", "{{.Id}}", args.contenedor],
                         capture_output=True, text=True, check=True).stdout.strip()
    limits = {n: Cgroup(cid).read(n).strip() for n in ("cpu.max", "memory.max", "cpuset.cpus")}
    mons = {n: Cgroup(i) for n, i in monitoring_ids().items()}
    sampler = Sampler(Cgroup(cid))
    sampler.start()

    print(f"== reposo {args.reposo} s")
    r_a = time.time()
    time.sleep(args.reposo)
    r_b = time.time()

    print(f"== carga {args.carga} s: 2 bucles de CPU + escalera de memoria {MEM_STEPS}")
    mon_start = {n: cg.snapshot()["usage_usec"] for n, cg in mons.items()}
    c_a = time.time()
    for _ in range(2):
        exec_bg(args.contenedor, f"timeout {args.carga} sh -c 'while :; do :; done'")
    for start, mb, hold in MEM_STEPS:
        # dd llena un búfer de `mb` MB (memoria anónima) y queda bloqueado escribiendo
        # en una tubería que nadie lee; lo retiene hasta que `sleep` termina.
        exec_bg(args.contenedor, f"sleep {start}; dd if=/dev/zero bs={mb}M count=1 2>/dev/null | sleep {hold}")
    time.sleep(args.carga)
    c_b = time.time()
    mon_end = {n: cg.snapshot()["usage_usec"] for n, cg in mons.items()}
    time.sleep(3)   # que Prometheus haya hecho el scrape del último segundo
    sampler.stop()

    out = {"descripcion": "verificación de definiciones cgroup frente a cAdvisor/Prometheus (F6.2); no es una medición",
           "contenedor": args.contenedor, "id": cid, "limites_cgroup": limits, "sello": stamp,
           "muestreo_propio_s": SAMPLE_S, "escalera_memoria": MEM_STEPS,
           "fases": [phase("reposo", cid, sampler.rows, r_a, r_b), phase("carga", cid, sampler.rows, c_a, c_b)],
           "monitoreo_en_carga_nucleos": {n: round((mon_end[n] - mon_start[n]) / 1e6 / (c_b - c_a), 4) for n in mons}}

    load = out["fases"][1]
    gauges_ok = all(f[k]["comparables_exactas"] > 0 and f[k]["iguales"] == f[k]["comparables_exactas"]
                    for f in out["fases"] for k in ("rss_vs_anon",))
    thr = load["throttled_seconds"]

    def below(part: str) -> bool:
        # Ojo: una diferencia de 0.0 es el mejor caso; no usar `x or 1` (0.0 es falso en Python).
        rel = thr.get(part, {}).get("dif_relativa")
        return rel is not None and rel < MAX_REL

    out["comprobaciones"] = {
        "rss_igual_a_anon_en_todas_las_estables": gauges_ok,
        "throttling_en_carga_mayor_que_0": (thr.get("b_control_cruzado", {}).get("delta_cgroup_bordes") or 0) > 0,
        "throttling_definicion_<5%": below("a_definicion"),
        "throttling_control_cruzado_<5%": below("b_control_cruzado"),
    }
    dest = ROOT / "results" / "f6" / "f6_2" / f"check_definitions_{args.contenedor}_{stamp}.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n")
    print(json.dumps({"comprobaciones": out["comprobaciones"], "monitoreo_en_carga_nucleos": out["monitoreo_en_carga_nucleos"],
                      "fases": out["fases"]}, indent=1, ensure_ascii=False))
    print(f"-> {dest.relative_to(ROOT)}")
    return 0 if all(out["comprobaciones"].values()) else 1


if __name__ == "__main__":
    sys.exit(main())
