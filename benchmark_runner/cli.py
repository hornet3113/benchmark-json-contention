"""cli.py — línea de comandos del runner (F5.4).

Uso (desde la raíz del repo, con el entorno del proyecto):
    sudo -v      # una vez: credenciales en caché para la limpieza de caché (V7)
    .venv/bin/python -m benchmark_runner.cli run-cell --smoke \\
        --engine postgresql --profile PROFILE_C_SEVERE --query-id Q2_MEM_LOW --concurrency 1 [--runs 1 2 3]

--smoke   ventanas 5/20/5 s; escribe en results/smoke/ (F5-g). NO son resultados.
Sin --smoke la corrida es REAL (60/300/60 s) y escribe en results/measurements.csv:
exige --confirmo-medicion-real, para que una prueba nunca ensucie el CSV del experimento.
--salida DIR desvía la salida a results/DIR/ (F7-a): el piloto de F7 va a
results/f7/ y no mezcla sus condiciones con el CSV de la matriz. Con --smoke el
archivo sigue llamándose measurements_smoke.csv, así que un CSV de humo nunca se
confunde con uno real; sirve para que un humo con ventanas propias (F7.3, F7.4)
no pise results/smoke/.

El proceso y sus workers se fijan en RUNNER_CPUSET (docker/images.env, F5-c):
no comparten núcleo físico con el motor.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from benchmark_runner import lifecycle, matrix
from benchmark_runner.config import SMOKE_WINDOWS, WINDOWS, Windows
from benchmark_runner.env import ROOT, load_env


def parse_cpuset(text: str) -> set[int]:
    """'8-11' o '0,2,4-5' → {8, 9, 10, 11}."""
    cpus: set[int] = set()
    for part in text.split(","):
        a, _, b = part.strip().partition("-")
        cpus.update(range(int(a), int(b or a) + 1))
    return cpus


def valid_salida(name: str) -> bool:
    """Un nombre simple de subcarpeta de results/: ni rutas, ni '..', ni vacío (F7-a)."""
    return bool(name.strip()) and Path(name).name == name and not name.startswith(".")


def output_paths(smoke: bool, salida: str | None) -> tuple[Path, str]:
    """Carpeta y nombre del CSV. El humo conserva su nombre aunque cambie de carpeta (F7.3/F7.4)."""
    sub = salida if salida else ("smoke" if smoke else "")
    return ROOT / "results" / sub, ("measurements_smoke.csv" if smoke else "measurements.csv")


def find_cell(mode: int, q2_variant: str | None, engine: str, profile: str, query_id: str, concurrency: int):
    for c in matrix.cells(mode, q2_variant):
        if (c.engine, c.profile, c.query_id, c.concurrency) == (engine, profile, query_id, concurrency):
            return c
    raise SystemExit(f"no existe esa celda en la matriz de {mode}: {engine} {profile} {query_id} c={concurrency}")


def main(argv: list[str] | None = None) -> int:
    from benchmark_runner.runner import run_one

    parser = argparse.ArgumentParser(description="Runner del benchmark (F5).")
    sub = parser.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run-cell", help="ejecuta las repeticiones de UNA celda")
    r.add_argument("--engine", required=True, choices=("mongodb", "postgresql"))
    r.add_argument("--profile", required=True, choices=("PROFILE_A_BASELINE", "PROFILE_B_MEDIUM", "PROFILE_C_SEVERE"))
    r.add_argument("--query-id", required=True)
    r.add_argument("--concurrency", required=True, type=int, choices=(1, 10, 50))
    r.add_argument("--runs", nargs="+", type=int, default=[1], choices=(1, 2, 3))
    r.add_argument("--matrix", type=int, choices=(54, 36), default=54, help="conteo de celdas (A2, pendiente)")
    r.add_argument("--q2-variant", choices=("MEM_LOW", "MEM_HIGH"), help="solo con --matrix 36")
    r.add_argument("--smoke", action="store_true", help="ventanas 5/20/5 s, salida en results/smoke/")
    r.add_argument("--ventanas", nargs=3, type=int, metavar=("CAL", "MED", "ENF"),
                   help="solo con --smoke: otras duraciones (s) para pruebas de carga; la salida sigue en results/smoke/")
    r.add_argument("--confirmo-medicion-real", action="store_true", help="necesario sin --smoke")
    r.add_argument("--salida", metavar="DIR",
                   help="subcarpeta de results/ donde van el CSV, los crudos, los planes y la telemetría "
                        "(F7-a; el piloto usa f7). Con --smoke el CSV sigue siendo measurements_smoke.csv")
    r.add_argument("--procesos", type=int,
                   help="solo con --smoke: procesos del runner (por defecto min(c, 10), con c/procesos hilos cada uno)")
    r.add_argument("--actividad-cada", type=float, metavar="S",
                   help="solo con --smoke: foto de la actividad del motor cada S s dentro de la ventana (F5.5b)")
    r.add_argument("--no-explain", action="store_true", help="no capturar el plan (R-31)")
    r.add_argument("--header-spaces", action="store_true", help='encabezado con ", " (F5-h)')
    args = parser.parse_args(argv)

    if args.procesos and not args.smoke:
        print("ERROR: --procesos solo se admite con --smoke (comparaciones del runner, F5.5).", file=sys.stderr)
        return 2
    if args.actividad_cada is not None and (not args.smoke or args.actividad_cada <= 0):
        print("ERROR: --actividad-cada solo se admite con --smoke y con S > 0 (comparaciones del runner, F5.5b).",
              file=sys.stderr)
        return 2
    if args.salida is not None and not valid_salida(args.salida):
        # Un nombre simple de subcarpeta: nada de rutas ni de subir a directorios de arriba.
        print("ERROR: --salida es un nombre de subcarpeta de results/ (p. ej. f7), sin barras ni puntos.",
              file=sys.stderr)
        return 2
    if args.ventanas and not args.smoke:
        print("ERROR: --ventanas solo se admite con --smoke: las corridas reales usan 60/300/60 (playbook.pdf §6).",
              file=sys.stderr)
        return 2
    if not args.smoke and not args.confirmo_medicion_real:
        print("ERROR: sin --smoke es una medición REAL que escribe en results/measurements.csv.\n"
              "       Añade --confirmo-medicion-real si es lo que quieres.", file=sys.stderr)
        return 2
    # Primero los argumentos: no se pide `sudo -v` para algo que no va a correr.
    cell = find_cell(args.matrix, args.q2_variant, args.engine, args.profile, args.query_id, args.concurrency)
    if not lifecycle.sudo_ready():
        print("ERROR: no hay credenciales de sudo en caché y la limpieza de caché las necesita (V7).\n"
              "       Ejecuta `sudo -v` en esta terminal y vuelve a lanzar.", file=sys.stderr)
        return 2

    cpus = parse_cpuset(load_env()["RUNNER_CPUSET"])
    os.sched_setaffinity(0, cpus)                     # los workers lo heredan (F5-c)
    base, csv_name = output_paths(args.smoke, args.salida)
    csv_path = base / csv_name
    windows = (Windows(*args.ventanas) if args.ventanas else SMOKE_WINDOWS) if args.smoke else WINDOWS

    keepalive = lifecycle.SudoKeepAlive()
    keepalive.start()
    rc = 0
    try:
        for n in args.runs:
            run = matrix.Run(cell, n)
            print(f"== {run.run_id}  ventanas {vars(windows)}  CPUs del runner {sorted(cpus)}", flush=True)
            try:
                res = run_one(run, windows=windows, csv_path=csv_path, raw_dir=base / "raw",
                              explain_dir=None if args.no_explain else base / "explains",
                              header_spaces=args.header_spaces, matrix=args.matrix, cpus=cpus,
                              processes=args.procesos, activity_every_s=args.actividad_cada)
            except lifecycle.RunAborted as exc:
                print(f"   ABORTADA (sin fila en el CSV): {exc}", flush=True)
                aborted = base / "abortadas.jsonl"
                aborted.parent.mkdir(parents=True, exist_ok=True)
                with aborted.open("a") as f:
                    f.write(json.dumps({"run_id": run.run_id, "motivo": str(exc)}, ensure_ascii=False) + "\n")
                rc = 1
                break
            row = res["row"]
            print(f"   status={row['status']} qps={row['throughput_qps']:.6f} p50/p95/p99={row['latency_p50_ms']}/"
                  f"{row['latency_p95_ms']}/{row['latency_p99_ms']} ms throttled={row['cpu_throttled_seconds']} s "
                  f"rss={row['max_rss_mb']} MiB spill={row['disk_spill']} ({res['wall_s']} s)", flush=True)
            for reason in res["reasons"]:
                print(f"   - {reason}", flush=True)
            print(f"   crudo: {Path(res['raw']).relative_to(ROOT)}  · CSV: {csv_path.relative_to(ROOT)}", flush=True)
            if res.get("dataset") is not None:
                d = res["dataset"]
                print(f"   dataset tras el OOM: {d.get('filas')} de {d['esperadas']} filas "
                      f"({d['segundos']} s){'' if d['intacto'] else '  ← DAÑADO'}", flush=True)
            if res.get("parar"):
                # R-08: no se siguen midiendo horas sobre un dataset que ya no es el del experimento.
                print("   DETENIDO: el dataset no está intacto tras el OOM. Recárgalo con "
                      "scripts/load_dataset.sh (DESTRUCTIVO) y verifica con scripts/run_gate.sh "
                      "antes de seguir.", file=sys.stderr, flush=True)
                rc = 3
                break
            tele = res.get("telemetria")
            if tele is not None:
                print(f"   telemetría: {'FALLO' if tele['fallo'] else tele['estado_exportacion']}"
                      f"  ({Path(tele['archivo']).relative_to(ROOT)})", flush=True)
                for reason in tele["motivos"]:
                    print(f"   - telemetría: {reason}", flush=True)
                if tele["fallo"] or tele["motivos"]:
                    # F6-f: el fallo queda en el log, con memoria y swap de la VM. NO detiene la matriz (F6-A1).
                    with (base / "telemetria_eventos.jsonl").open("a") as f:
                        f.write(json.dumps({"run_id": run.run_id, "fallo": tele["fallo"], "motivos": tele["motivos"],
                                            "memoria_vm": tele.get("memoria_vm")}, ensure_ascii=False) + "\n")
    finally:
        keepalive.stop()
        lifecycle.stop_engines()
    return rc


if __name__ == "__main__":
    sys.exit(main())
