#!/usr/bin/env python3
"""check_anon_blips.py — ¿cambia `anon` y vuelve a su valor en menos de 0.2 s? (F6.2)

Uso (un motor arriba, sin carga):
    .venv/bin/python scripts/checks/check_anon_blips.py --contenedor bench_postgres --segundos 60

Por qué existe: en check_definitions_bench_postgres_20261102T033532Z.json, en
reposo, una muestra de container_memory_rss difirió 112 KiB de `anon` aunque
las dos lecturas propias que la encerraban (0.2 s de separación) eran iguales.
Si `anon` hace "picos" más cortos que ese intervalo, una muestra de cAdvisor
puede caer dentro de uno sin que el muestreo de 0.2 s lo vea. Este script lee
`anon` cada ~10 ms y cuenta los picos: cambios que vuelven exactamente al valor
anterior en ≤ 0.2 s.

Es una verificación, no una medición: no escribe en ningún CSV.
Salida: results/f6/f6_2/check_anon_blips_<contenedor>_<sello>.json
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

INTERVAL_S = 0.01
BLIP_MAX_S = 0.2


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--contenedor", required=True, choices=["bench_postgres", "bench_mongo"])
    ap.add_argument("--segundos", type=int, default=60)
    args = ap.parse_args()

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    cid = subprocess.run(["docker", "inspect", "-f", "{{.Id}}", args.contenedor],
                         capture_output=True, text=True, check=True).stdout.strip()
    cg = Cgroup(cid)
    rows: list[tuple[float, int]] = []
    end = time.monotonic() + args.segundos
    while time.monotonic() < end:
        rows.append((time.monotonic(), cg.anon_bytes()))
        time.sleep(INTERVAL_S)

    # Tramos de valor constante; un pico es un tramo corto entre dos tramos con el mismo valor.
    runs: list[list] = []
    for t, v in rows:
        if runs and runs[-1][2] == v:
            runs[-1][1] = t
        else:
            runs.append([t, t, v])
    blips = []
    for prev, cur, nxt in zip(runs, runs[1:], runs[2:]):
        dur = nxt[0] - cur[0]
        if prev[2] == nxt[2] and dur <= BLIP_MAX_S:
            blips.append({"duracion_ms": round(dur * 1000, 1), "dif_kib": (cur[2] - prev[2]) // 1024})

    out = {"descripcion": "picos breves de anon (F6.2); no es una medición", "contenedor": args.contenedor,
           "sello": stamp, "segundos": args.segundos, "lecturas": len(rows),
           "intervalo_medio_ms": round((rows[-1][0] - rows[0][0]) / (len(rows) - 1) * 1000, 2),
           "cambios_de_valor": len(runs) - 1, "picos_<=200ms": len(blips),
           "picos_por_minuto": round(len(blips) * 60 / args.segundos, 2),
           "picos_ejemplos": blips[:20],
           "dif_kib_de_los_picos": sorted({b["dif_kib"] for b in blips})}
    dest = ROOT / "results" / "f6" / "f6_2" / f"check_anon_blips_{args.contenedor}_{stamp}.json"
    dest.write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n")
    print(json.dumps({k: v for k, v in out.items() if k != "picos_ejemplos"}, indent=1, ensure_ascii=False))
    print(f"-> {dest.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
