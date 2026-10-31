#!/usr/bin/env python3
"""check_telemetry_live.py — comprobación previa y exportación contra el Prometheus REAL (F6.4).

Uso (monitoreo arriba; sin sudo; levanta Postgres en PROFILE_C):
    .venv/bin/python scripts/checks/check_telemetry_live.py

Las pruebas unitarias (tests/test_telemetry.py) usan un Prometheus falso; esto
ejercita benchmark_runner/telemetry.py, sin tocarlo, contra el de verdad:
  1. comprobación previa con todo sano → ok, sin recuperación;
  2. `docker stop benchmon_node_exporter` A PROPÓSITO → la comprobación previa
     debe fallar, registrar memoria y swap de la VM, ejecutar up_monitoring.sh
     una vez, recuperarse y anotarlo (F6-A4);
  3. exportación de una ventana de 60 s de bench_postgres en reposo → "completa",
     y con las series que usan las figuras.

Es una verificación, no una medición: no escribe en ningún CSV.
Salida: results/f6/f6_4/check_telemetry_live_<sello>.json
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from benchmark_runner import lifecycle, telemetry  # noqa: E402

WINDOW_S = 60


def main() -> int:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    recover = lambda: telemetry.run_recovery(ROOT)  # noqa: E731
    up = subprocess.run([str(ROOT / "scripts" / "up_profile.sh"), "c_severe", "postgres"], capture_output=True, text=True)
    if up.returncode != 0:
        sys.exit(up.stdout + up.stderr)
    cid = lifecycle.container_id("postgresql")

    print("== 1. comprobación previa con todo sano", flush=True)
    healthy = telemetry.preflight(telemetry.http_get, recover)

    print("== 2. node_exporter detenido a propósito", flush=True)
    subprocess.run(["docker", "stop", "benchmon_node_exporter"], check=True, capture_output=True)
    time.sleep(3)                                   # que Prometheus haya visto up=0
    t0 = time.monotonic()
    broken = telemetry.preflight(telemetry.http_get, recover)
    broken["segundos"] = round(time.monotonic() - t0, 1)

    print(f"== 3. ventana de {WINDOW_S} s de bench_postgres y exportación", flush=True)
    time.sleep(5)
    w0 = time.time()
    time.sleep(WINDOW_S)
    w1 = time.time()
    exp = telemetry.export(telemetry.http_get, cid, w0, w1)
    counts = {m: sum(len(s["muestras"]) for s in v) for m, v in exp["series"].items()}

    checks = {
        "1_sano_ok_sin_recuperar": healthy["ok"] and "recuperacion" not in healthy,
        "2_detecta_el_fallo": not broken["primera"]["ok"],
        "2_registra_memoria_al_fallar": "MemAvailable_kib" in broken.get("memoria_vm_al_fallar", {}),
        "2_recupera_una_vez": broken.get("recuperacion", {}).get("exit") == 0 and broken.get("recuperada") is True,
        "3_exportacion_completa": exp.get("estado") == "completa",
        "3_series_de_las_figuras": all(counts.get(m, 0) >= WINDOW_S for m in
                                       ("container_memory_rss", "container_cpu_cfs_throttled_seconds_total",
                                        "container_memory_working_set_bytes", "node_memory_MemAvailable_bytes")),
    }
    out = {"descripcion": "telemetry.py contra el Prometheus real (F6.4); no es una medición", "sello": stamp,
           "container_id": cid, "sano": healthy, "node_exporter_detenido": broken,
           "exportacion_resumen": {k: exp.get(k) for k in ("estado", "motivo", "ventana_wall_s", "huecos_en_ventana",
                                                           "segundos_sin_muestra_max")},
           "muestras_por_serie": counts, "comprobaciones": checks}
    dest = ROOT / "results" / "f6" / "f6_4" / f"check_telemetry_live_{stamp}.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n")
    print(json.dumps({"comprobaciones": checks, "fallo_detectado": broken["primera"].get("motivo"),
                      "recuperacion_s": broken["segundos"], "exportacion": out["exportacion_resumen"],
                      "muestras_por_serie": counts}, ensure_ascii=False, indent=1))
    print(f"-> {dest.relative_to(ROOT)}")
    subprocess.run([str(ROOT / "scripts" / "down_profile.sh")], capture_output=True)
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
