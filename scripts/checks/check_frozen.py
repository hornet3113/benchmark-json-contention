#!/usr/bin/env python3
"""check_frozen.py — rss de cAdvisor frente a `anon` con el contenedor CONGELADO (F6.2).

Uso (un motor arriba; lo pausa unos segundos y lo reanuda siempre):
    .venv/bin/python scripts/checks/check_frozen.py --contenedor bench_postgres --segundos 20

Por qué existe: comparar muestra a muestra con el contenedor vivo deja una duda
irreducible. Si `anon` cambia y vuelve entre dos lecturas propias, una muestra
de cAdvisor puede no coincidir sin que la definición sea distinta
(check_definitions_*: 1 de 57 en Postgres, 1 de 43 en Mongo, ambos en reposo).
Con `docker pause` (cgroup freezer) ningún proceso del contenedor corre y
`anon` no puede moverse: si cAdvisor y el cgroup difieren ahí, la definición
es distinta; si coinciden en TODAS las muestras, la diferencia era de tiempo.

Es una verificación, no una medición: no escribe en ningún CSV.
Salida: results/f6/f6_2/check_frozen_<contenedor>_<sello>.json
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

from benchmark_runner.metrics.cgroup import Cgroup  # noqa: E402
from scripts.checks.check_definitions import prom_raw  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--contenedor", required=True, choices=["bench_postgres", "bench_mongo"])
    ap.add_argument("--segundos", type=int, default=20)
    args = ap.parse_args()

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    cid = subprocess.run(["docker", "inspect", "-f", "{{.Id}}", args.contenedor],
                         capture_output=True, text=True, check=True).stdout.strip()
    cg = Cgroup(cid)
    own: list[tuple[float, int, int]] = []
    subprocess.run(["docker", "pause", args.contenedor], check=True, capture_output=True)
    try:
        time.sleep(2)   # que el freezer haya detenido todo
        frozen = cg.read("cgroup.freeze").strip()
        t_a = time.time()
        while time.time() - t_a < args.segundos:
            mem = cg.flat("memory.stat")
            own.append((time.time(), mem["anon"], int(cg.read("memory.current")) - mem["inactive_file"]))
            time.sleep(0.2)
        t_b = time.time()
    finally:
        subprocess.run(["docker", "unpause", args.contenedor], check=True, capture_output=True)
    time.sleep(3)   # último scrape

    rss = prom_raw("container_memory_rss", cid, t_a, t_b)
    ws = prom_raw("container_memory_working_set_bytes", cid, t_a, t_b)
    anon_vals, ws_vals = {a for _, a, _ in own}, {w for _, _, w in own}
    out = {"descripcion": "rss/working_set de cAdvisor frente al cgroup con el contenedor congelado (F6.2)",
           "contenedor": args.contenedor, "sello": stamp, "segundos": round(t_b - t_a, 3),
           "cgroup.freeze": frozen, "lecturas_propias": len(own),
           "anon_valores_distintos_congelado": sorted(anon_vals),
           "rss_prometheus": {"muestras": len(rss), "valores_distintos": sorted({int(v) for _, v in rss})},
           "working_set_valores_propios": sorted(ws_vals),
           "working_set_prometheus": {"muestras": len(ws), "valores_distintos": sorted({int(v) for _, v in ws})}}
    out["comprobaciones"] = {
        "congelado": frozen == "1" and len(anon_vals) == 1,
        "rss_igual_a_anon_en_todas": len(rss) >= args.segundos - 2 and {int(v) for _, v in rss} == anon_vals,
        "working_set_igual_en_todas": len(ws) >= args.segundos - 2 and {int(v) for _, v in ws} == ws_vals,
    }
    dest = ROOT / "results" / "f6" / "f6_2" / f"check_frozen_{args.contenedor}_{stamp}.json"
    dest.write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n")
    print(json.dumps(out, indent=1, ensure_ascii=False))
    print(f"-> {dest.relative_to(ROOT)}")
    return 0 if all(out["comprobaciones"].values()) else 1


if __name__ == "__main__":
    sys.exit(main())
