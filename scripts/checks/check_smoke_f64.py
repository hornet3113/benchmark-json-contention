#!/usr/bin/env python3
"""check_smoke_f64.py — ¿cuadran la fila, la serie de 1 s y Prometheus en cada repetición del humo? (F6.4)

Uso:  .venv/bin/python scripts/checks/check_smoke_f64.py [CARPETA]
      (CARPETA es la de la corrida; por defecto results/smoke. F7.4 usa results/f7_memoria)

Por cada crudo de results/smoke/raw/:
  1. Serie de 1 s del runner (serie_cgroup_1s): cubre la ventana, y su máximo de
     `anon` es EXACTAMENTE max_rss_mb de la fila (mismo dato, F6 pedido de Alix).
  2. Telemetría: estado de la exportación ("completa" / "con_huecos" / "fallida") y motivos.
  3. Fila frente a Prometheus:
     - max_rss_mb frente al máximo de container_memory_rss en la ventana (las dos
       fuentes leen `anon`, F6.2, pero en instantes distintos: se informa la diferencia);
     - cpu_throttled_seconds frente al Δ de container_cpu_cfs_throttled_seconds_total
       entre las muestras más cercanas a los bordes. El 5 % (PLAN F6) solo se exige
       con ≥ 1 s de throttling: con menos, el desfase de los bordes pesa demasiado (F6.2, hallazgo 2).
  4. Memoria de la VM en la ventana (MemAvailable mínima, swap, presión de memoria).
  5. El monitoreo bajo carga (F6-c): núcleos y memoria de Prometheus, cAdvisor y
     node_exporter, throttling, duración máxima de scrape y up mínimo, en la ventana.

Es una verificación, no una medición: no escribe en ningún CSV.
Salida: results/smoke/check_f64.json. Exit 0 si se cumple lo exigible en todas.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from benchmark_runner import telemetry  # noqa: E402

SMOKE = ROOT / "results" / "smoke"
MAX_REL = 0.05
MIN_THROTTLE_FOR_5PCT_S = 1.0


def series(exp: dict, metric: str) -> list[tuple[float, float]]:
    return sorted((t, v) for s in exp["series"].get(metric, []) for t, v in s["muestras"])


def nearest(samples: list[tuple[float, float]], t: float) -> tuple[float, float]:
    return min(samples, key=lambda p: abs(p[0] - t))


def in_window(samples, w0, w1):
    return [(t, v) for t, v in samples if w0 <= t <= w1]


def monitoring(w0: float, w1: float) -> dict:
    """Consumo del monitoreo en la ventana, según cAdvisor (no hay lectura propia retroactiva)."""
    out = subprocess.run(["docker", "ps", "--no-trunc", "--filter", "name=benchmon_", "--format", "{{.Names}} {{.ID}}"],
                         capture_output=True, text=True).stdout
    res = {}
    for name, cid in (l.split() for l in out.splitlines() if l.strip()):
        def raw(m):
            return sorted((t, v) for s in telemetry.raw_series(telemetry.http_get, f'{m}{{id="/docker/{cid}"}}', w0, w1)
                          for t, v in s["muestras"])
        cpu, thr, mem = (raw("container_cpu_usage_seconds_total"), raw("container_cpu_cfs_throttled_seconds_total"),
                         raw("container_memory_usage_bytes"))
        span = (cpu[-1][0] - cpu[0][0]) if len(cpu) > 1 else None
        res[name] = {"nucleos_medios": round((cpu[-1][1] - cpu[0][1]) / span, 4) if span else None,
                     "throttled_s": round(thr[-1][1] - thr[0][1], 3) if len(thr) > 1 else None,
                     "memory_usage_max_mib": round(max(v for _, v in mem) / 2**20, 1) if mem else None}
    scrape = {s["etiquetas"].get("job"): round(max(v for _, v in s["muestras"]), 4)
              for s in telemetry.raw_series(telemetry.http_get, "scrape_duration_seconds", w0, w1) if s["muestras"]}
    up_min = {s["etiquetas"].get("job"): min(v for _, v in s["muestras"])
              for s in telemetry.raw_series(telemetry.http_get, "up", w0, w1) if s["muestras"]}
    return {"contenedores": res, "scrape_max_s": scrape, "up_min": up_min}


def evaluate(raw: dict) -> dict:
    row = raw["fila_csv"]
    w_ns = (raw["ventana_ns"]["fin"] - raw["ventana_ns"]["inicio"]) / 1e9
    s = raw.get("serie_cgroup_1s") or {}
    cols, rows = s.get("columnas", []), s.get("filas", [])
    out: dict = {"status": row["status"], "max_rss_mb": row["max_rss_mb"],
                 "cpu_throttled_seconds": row["cpu_throttled_seconds"], "ventana_s": round(w_ns, 3)}
    if rows:
        ia = cols.index("anon")
        out["serie_1s"] = {"filas": len(rows), "max_anon_mib": max(r[ia] for r in rows) / 2**20}
        out["serie_1s"]["igual_a_max_rss_mb"] = out["serie_1s"]["max_anon_mib"] == row["max_rss_mb"]
        iw = (cols.index("memory_current"), cols.index("inactive_file"))
        out["serie_1s"]["working_set_max_mib"] = round(max(r[iw[0]] - r[iw[1]] for r in rows) / 2**20, 1)
        out["serie_1s"]["shmem_max_mib"] = round(max(r[cols.index("shmem")] for r in rows) / 2**20, 1)
    else:
        out["serie_1s"] = None

    tele = raw.get("telemetria")
    out["telemetria"] = None if tele is None else {k: tele.get(k) for k in ("fallo", "estado_exportacion", "motivos")}
    if not tele:
        return out
    doc = json.loads(Path(tele["archivo"]).read_text())
    exp = doc["exportacion"]
    w0, w1 = exp["ventana_wall_s"]
    out["huecos_en_ventana"] = exp.get("huecos_en_ventana")
    rss = in_window(series(exp, "container_memory_rss"), w0, w1)
    if rss and row["max_rss_mb"] is not None:
        pmax = max(v for _, v in rss) / 2**20
        out["rss_prometheus_max_mib"] = round(pmax, 3)
        out["rss_dif_rel"] = round(abs(pmax - row["max_rss_mb"]) / row["max_rss_mb"], 5)
    ws = in_window(series(exp, "container_memory_working_set_bytes"), w0, w1)
    if ws:
        out["working_set_prometheus_max_mib"] = round(max(v for _, v in ws) / 2**20, 1)
    thr = series(exp, "container_cpu_cfs_throttled_seconds_total")
    if len(thr) > 1 and row["cpu_throttled_seconds"] is not None:
        (ta, va), (tb, vb) = nearest(thr, w0), nearest(thr, w1)
        d = vb - va
        out["throttling_prometheus_s"] = round(d, 6)
        out["throttling_desfase_bordes_s"] = [round(ta - w0, 3), round(tb - w1, 3)]
        ref = row["cpu_throttled_seconds"]
        out["throttling_dif_rel"] = round(abs(d - ref) / ref, 5) if ref else None
        out["throttling_exige_5pct"] = ref >= MIN_THROTTLE_FOR_5PCT_S
    avail = in_window(series(exp, "node_memory_MemAvailable_bytes"), w0, w1)
    pswp = series(exp, "node_vmstat_pswpout")
    press = series(exp, "node_pressure_memory_waiting_seconds_total")
    out["vm"] = {"mem_available_min_mib": round(min(v for _, v in avail) / 2**20, 1) if avail else None,
                 "pswpout_delta": (pswp[-1][1] - pswp[0][1]) if len(pswp) > 1 else None,
                 "presion_memoria_espera_s": round(press[-1][1] - press[0][1], 3) if len(press) > 1 else None}
    out["monitoreo"] = monitoring(w0, w1)

    checks = {"serie_1s_cubre_la_ventana": bool(rows) and len(rows) >= w_ns - 2,
              "serie_1s_max_es_max_rss_mb": bool(out["serie_1s"]) and out["serie_1s"]["igual_a_max_rss_mb"],
              "telemetria_sin_fallo": not tele["fallo"]}
    if out.get("throttling_exige_5pct"):
        checks["throttling_columna_vs_prometheus_<5%"] = out["throttling_dif_rel"] < MAX_REL
    out["comprobaciones"] = checks
    return out


def main() -> int:
    global SMOKE
    if len(sys.argv) > 1:
        SMOKE = Path(sys.argv[1]).resolve()
    files = sorted((SMOKE / "raw").glob("*.json"))
    if not files:
        sys.exit(f"no hay crudos en {SMOKE / 'raw'}")
    res = {f.stem: evaluate(json.loads(f.read_text())) for f in files}
    ok = all(all(r.get("comprobaciones", {"sin_telemetria": False}).values()) for r in res.values())
    (SMOKE / "check_f64.json").write_text(json.dumps(res, ensure_ascii=False, indent=1) + "\n")
    for run_id, r in res.items():
        print(f"== {run_id}: status={r['status']}  telemetría={r['telemetria']}")
        s = r.get("serie_1s") or {}
        print(f"   serie 1 s: {s.get('filas')} filas en {r['ventana_s']} s · max anon {s.get('max_anon_mib')} = "
              f"max_rss_mb {r['max_rss_mb']}? {s.get('igual_a_max_rss_mb')} · working_set {s.get('working_set_max_mib')}"
              f" MiB · shmem {s.get('shmem_max_mib')} MiB")
        print(f"   Prometheus: rss max {r.get('rss_prometheus_max_mib')} MiB (dif {r.get('rss_dif_rel')}) · "
              f"throttling {r.get('throttling_prometheus_s')} s vs columna {r['cpu_throttled_seconds']} "
              f"(dif {r.get('throttling_dif_rel')}, exige 5 %: {r.get('throttling_exige_5pct')}) · huecos {r.get('huecos_en_ventana')}")
        print(f"   VM: {r.get('vm')}")
        m = r.get("monitoreo") or {}
        print(f"   monitoreo: {m.get('contenedores')} · scrape máx {m.get('scrape_max_s')} · up mín {m.get('up_min')}")
        print(f"   {r.get('comprobaciones')}")
    print(f"-> {SMOKE / 'check_f64.json'} · {'TODO CUADRA' if ok else 'REVISAR'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
