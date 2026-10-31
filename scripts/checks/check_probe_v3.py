"""check_probe_v3.py — verificación de la sonda v3 (F5.5b) contra Mongo real con PROFILE_A, 10×5, ventanas 25/20/2 y fotos cada 2 s.

No es medición: no limpia caché ni escribe CSV. Uso (Mongo arriba):  taskset -c 8-11 .venv/bin/python scripts/checks/check_probe_v3.py
Salida archivada (2026-11-01): results/f5/f5_5/check_probe_v3.txt
"""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from benchmark_runner import matrix
from benchmark_runner.config import Windows
from benchmark_runner.env import load_env
from benchmark_runner.metrics.concurrency import PeriodicReader, cross, summarize
from benchmark_runner.runner import EngineProbe
from benchmark_runner.workload import run_load


def main():
    cell = next(c for c in matrix.cells(54) if c.engine == "mongodb" and c.query_id == "Q2_MEM_LOW"
                and c.profile == "PROFILE_A_BASELINE" and c.concurrency == 50)
    probe = EngineProbe("mongodb", load_env())
    series = PeriodicReader(probe.activity, 2)
    edges = {}
    def on_start():
        edges["inicio"] = probe.activity(); series.start()
    def on_end():
        edges["fin"] = probe.activity(); series.stop()
    r = run_load(cell, Windows(25, 20, 2), ("real", {}), concurrency=50, timeout_s=300,
                 on_window_start=on_start, on_window_end=on_end, grace_s=40, processes=10)
    photos = sorted([{"momento": k, **v} for k, v in edges.items()] + series.samples, key=lambda p: p["t0_ns"])
    rows = cross(photos, [(s.start_ns, s.end_ns, s.wid) for s in r.samples], r.unfinished_workers, "mongodb")
    for x in rows:
        print({k: x[k] for k in ("momento", "duracion_ms", "motor", "cliente_seguro", "cliente_en_t0", "faltan", "terminan_<=250ms_despues")})
    print("resumen", summarize(rows), "errores serie", series.errors, "cortados", r.unfinished_workers,
          "getmore vistos", [p.get("getmore_activos") for p in photos])
    probe.close()

if __name__ == '__main__':
    main()
