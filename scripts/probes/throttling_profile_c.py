#!/usr/bin/env python3
"""throttling_profile_c.py — sonda: throttling mecánico en PROFILE_C y control cruzado cgroup/Prometheus (F6.3)

Uso (monitoreo arriba; sin sudo; levanta el motor con PROFILE_C):
    .venv/bin/python scripts/probes/throttling_profile_c.py --motor postgresql --segundos 120

ESTO ES UNA SONDA, NO UN RESULTADO DEL BENCHMARK: no produce filas del CSV.

F6-g: la carga son 2 bucles de CPU (`docker exec`) dentro del contenedor del
motor, contra 1 CPU de cuota: el throttling de CFS es mecánico y no depende
del planificador de cada motor. PLAN F6: "si sale 0, el límite no se está
aplicando y todo el experimento es inválido".

F6-h: la ventana es ≥ 60 s. Se compara (b) el Δ de throttled_usec del cgroup en
los bordes de la ventana, como lo calcula el runner, con el Δ de
container_cpu_cfs_throttled_seconds_total entre las muestras de Prometheus más
cercanas a esos bordes; y (a) las dos fuentes en las mismas marcas de tiempo.
Mismas funciones que F6.2 (scripts/checks/check_definitions.py).

La línea base en reposo del mismo motor y perfil (scripts/probes/throttling_baseline.py)
se resta aparte en el reporte; aquí se informa el total.

Pasa si: Δ throttling > 0 y diferencia (b) < 5 %.
Salida: results/f6/probes/throttling_profile_c_<motor>_<sello>.json
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time

import probe_common as pc
from benchmark_runner.lifecycle import CONTAINER
from benchmark_runner.metrics.cgroup import SAMPLE_COLUMNS, AnonSampler
from scripts.checks.check_definitions import MAX_REL, compare_counter, prom_raw

LOOPS = 2


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--motor", required=True, choices=["postgresql", "mongodb"])
    ap.add_argument("--segundos", type=int, default=120)
    args = ap.parse_args()
    if args.segundos < 60:
        ap.error("--segundos debe ser ≥ 60 (F6-h)")

    st = pc.stamp()
    cg = pc.engine_up("c_severe", args.motor)
    cid = cg.path.name
    limits = {n: cg.read(n).strip() for n in ("cpu.max", "cpuset.cpus")}
    time.sleep(15)                                   # que el arranque del motor no entre en la ventana
    for _ in range(LOOPS):
        subprocess.run(["docker", "exec", "-d", CONTAINER[args.motor], "timeout", str(args.segundos + 5),
                        "sh", "-c", "while :; do :; done"], check=True)
    time.sleep(2)                                    # bucles ya corriendo
    sampler = AnonSampler(cg, 1.0)
    rows = []
    start = pc.edge(cg)
    t_a = start["clock"].wall_ns / 1e9
    sampler.start()
    time.sleep(args.segundos)
    sampler.stop()
    end = pc.edge(cg)
    t_b = end["clock"].wall_ns / 1e9
    time.sleep(3)                                    # último scrape

    # compare_counter espera lecturas propias con reloj de pared: las del muestreador de 1 s más los bordes.
    i_thr, i_use = SAMPLE_COLUMNS.index("throttled_usec"), SAMPLE_COLUMNS.index("usage_usec")
    for s in sampler.samples:
        rows.append({"t": t_a + (s[0] - start["clock"].mono_ns) / 1e9, "throttled_usec": s[i_thr], "usage_usec": s[i_use]})
    rows = ([{"t": t_a, **{k: start["cgroup"][k] for k in ("throttled_usec", "usage_usec")}}] + rows
            + [{"t": t_b, **{k: end["cgroup"][k] for k in ("throttled_usec", "usage_usec")}}])
    thr = compare_counter(prom_raw("container_cpu_cfs_throttled_seconds_total", cid, t_a - 1, t_b + 1),
                          rows, "throttled_usec", 1e6, t_a, t_b)
    use = compare_counter(prom_raw("container_cpu_usage_seconds_total", cid, t_a - 1, t_b + 1),
                          rows, "usage_usec", 1e6, t_a, t_b)
    d_thr = (end["cgroup"]["throttled_usec"] - start["cgroup"]["throttled_usec"]) / 1e6
    rel = thr.get("b_control_cruzado", {}).get("dif_relativa")
    checks = {"throttling_>0": d_thr > 0, "control_cruzado_<5%": rel is not None and rel < MAX_REL}
    out = {"descripcion": "sonda de throttling en PROFILE_C (F6.3); NO es una medición ni una fila del CSV",
           "motor": args.motor, "perfil": "PROFILE_C_SEVERE", "sello": st, "limites_cgroup": limits,
           "carga": f"{LOOPS} × docker exec timeout … sh -c 'while :; do :; done'", "segundos": args.segundos,
           "throttled_s_cgroup": round(d_thr, 6),
           "nr_throttled": end["cgroup"]["nr_throttled"] - start["cgroup"]["nr_throttled"],
           "nr_periods": end["cgroup"]["nr_periods"] - start["cgroup"]["nr_periods"],
           "uso_cpu_s": round((end["cgroup"]["usage_usec"] - start["cgroup"]["usage_usec"]) / 1e6, 6),
           "throttling_cgroup_vs_prometheus": thr, "uso_cpu_cgroup_vs_prometheus": use, "comprobaciones": checks}
    dest = pc.save(f"throttling_profile_c_{args.motor}_{st}", out)
    print(f"== {args.motor}: throttling {d_thr:.3f} s en {args.segundos} s · periodos {out['nr_throttled']}/{out['nr_periods']}"
          f" · uso {out['uso_cpu_s']:.2f} s · (a) {thr.get('a_definicion')} · (b) {thr.get('b_control_cruzado')}")
    print(checks)
    print(f"-> {dest.relative_to(pc.ROOT)}")
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
