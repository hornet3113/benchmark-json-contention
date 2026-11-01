#!/usr/bin/env python3
"""descartar_repeticion.py — descarta una repetición para poder repetirla (F8-b).

Uso:
    .venv/bin/python scripts/descartar_repeticion.py \\
        --engine mongodb --profile PROFILE_C_SEVERE --query-id Q2_MEM_LOW \\
        --concurrency 50 --run-number 2 \\
        --motivo "el equipo se suspendió 4 min dentro de la ventana"
    .venv/bin/python scripts/descartar_repeticion.py --listar

Por qué existe. Si el equipo se suspende a mitad de una ventana, el runner lo
detecta (F5-d) y escribe una fila `status=error`. Pero esa fila **ya existe**, así
que `run_benchmarks.sh` da la repetición por hecha y no la repite nunca: la
matriz se queda con un agujero permanente. Editar el CSV a mano está prohibido
(CLAUDE.md: "la repetición afectada se descarta y se repite; nunca se corrige a
mano"). Esto lo hace de forma trazable.

Qué hace, con la condición que puso Alix (2026-11-02) — **descartar tiene que ser
visible y auditable, no silencioso**:

  1. El **motivo es obligatorio**: sin `--motivo` no hace nada.
  2. Copia el CSV a `measurements.csv.bak-<sello>` antes de tocarlo.
  3. Mueve la fila a `descartadas.csv`, en la misma carpeta, con el motivo, la
     fecha del descarte y quién lo pidió. Ese archivo **nunca se borra**: es la
     tabla que va al reporte (R-27.1; si no hubo descartes, el reporte lo dice).
  4. Mueve el crudo y la telemetría a `raw/descartadas/` y `telemetry/descartadas/`.
     La evidencia de lo que pasó NO se borra.
  5. Reescribe el CSV **sin esa fila**, copiando las demás líneas tal cual (byte a
     byte, encabezado incluido): no se reformatea ningún número.

Después, `run_benchmarks.sh` vuelve a ver la repetición como pendiente y la corre.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from benchmark_runner import csv_writer  # noqa: E402
from benchmark_runner.schedule import KEY_COLUMNS, key  # noqa: E402

DISCARDED = "descartadas.csv"
EXTRA_COLUMNS = ("descartada_utc", "motivo", "pedido_por", "run_id", "crudo_movido_a")


def run_id(row: dict) -> str:
    return (f"{row['engine']}_{row['profile']}_{row['query_id']}"
            f"_c{row['concurrency']}_r{row['run_number']}")


def read_rows(csv_path: Path) -> tuple[str, list[tuple[str, dict]]]:
    """(línea del encabezado tal cual, [(línea tal cual, fila parseada)])."""
    text = csv_path.read_text()
    lines = text.splitlines(keepends=True)
    if not lines:
        sys.exit(f"{csv_path} está vacío")
    header, data = lines[0], lines[1:]
    parsed = list(csv.DictReader(io.StringIO(text)))
    if len(parsed) != len([line for line in data if line.strip()]):
        sys.exit(f"{csv_path}: hay filas que ocupan más de una línea; revísalo a mano")
    return header, list(zip([line for line in data if line.strip()], parsed))


def append_discarded(path: Path, row: dict, extra: dict) -> None:
    columns = [*csv_writer.COLUMNS, *EXTRA_COLUMNS]
    nuevo = not path.exists()
    with path.open("a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=columns)
        if nuevo:
            w.writeheader()
        w.writerow({**row, **extra})


def move_aside(path: Path, subdir: str, stamp: str) -> str | None:
    if not path.exists():
        return None
    dest_dir = path.parent / subdir
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{path.stem}_{stamp}{path.suffix}"
    shutil.move(str(path), dest)
    return str(dest.relative_to(ROOT))


def listar(base: Path) -> int:
    path = base / DISCARDED
    if not path.exists():
        print(f"descartadas: 0 (no existe {path.relative_to(ROOT)})")
        return 0
    rows = list(csv.DictReader(path.open()))
    print(f"descartadas: {len(rows)}")
    for r in rows:
        print(f"   {r.get('run_id')} · {r.get('descartada_utc')} · status={r.get('status')} · {r.get('motivo')}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--salida", default="", metavar="DIR",
                    help="subcarpeta de results/ con el CSV (por defecto results/)")
    ap.add_argument("--listar", action="store_true", help="muestra las filas ya descartadas y sale")
    ap.add_argument("--engine", choices=("mongodb", "postgresql"))
    ap.add_argument("--profile")
    ap.add_argument("--query-id")
    ap.add_argument("--concurrency", type=int)
    ap.add_argument("--run-number", type=int)
    ap.add_argument("--motivo", help="OBLIGATORIO: por qué se descarta (va al reporte)")
    ap.add_argument("--pedido-por", default="Alix")
    args = ap.parse_args()

    base = ROOT / "results" / args.salida if args.salida else ROOT / "results"
    if args.listar:
        return listar(base)

    faltan = [n for n in ("engine", "profile", "query_id", "concurrency", "run_number", "motivo")
              if getattr(args, n) in (None, "")]
    if faltan:
        ap.error("faltan argumentos obligatorios: " + ", ".join("--" + n.replace("_", "-") for n in faltan))
    if not args.motivo.strip():
        ap.error("--motivo no puede estar vacío: descartar tiene que ser auditable")

    csv_path = base / "measurements.csv"
    if not csv_path.exists():
        sys.exit(f"no existe {csv_path}")
    wanted = key(args.engine, args.profile, args.query_id, args.concurrency, args.run_number)
    header, rows = read_rows(csv_path)
    hits = [(line, row) for line, row in rows if key(*(row[c] for c in KEY_COLUMNS)) == wanted]
    if not hits:
        sys.exit(f"no hay ninguna fila con {wanted} en {csv_path.relative_to(ROOT)}")
    if len(hits) > 1:
        sys.exit(f"hay {len(hits)} filas con {wanted}: el CSV tiene duplicados, revísalo antes")

    line, row = hits[0]
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    rid = run_id(row)
    shutil.copy2(csv_path, csv_path.with_suffix(f".csv.bak-{stamp}"))
    crudo = move_aside(base / "raw" / f"{rid}.json", "descartadas", stamp)
    tele = move_aside(base / "telemetry" / f"{rid}.json", "descartadas", stamp)
    append_discarded(base / DISCARDED, row,
                     {"descartada_utc": stamp, "motivo": args.motivo.strip(),
                      "pedido_por": args.pedido_por, "run_id": rid, "crudo_movido_a": crudo or ""})
    # El encabezado y las demás líneas se copian tal cual: ningún número se reformatea.
    kept = [l for l, r in rows if l is not line]
    csv_path.write_text(header + "".join(kept))

    print(json.dumps({"descartada": rid, "status_que_tenia": row["status"], "motivo": args.motivo.strip(),
                      "crudo_movido_a": crudo, "telemetria_movida_a": tele,
                      "copia_de_seguridad": str(csv_path.with_suffix(f'.csv.bak-{stamp}').relative_to(ROOT)),
                      "registro": str((base / DISCARDED).relative_to(ROOT)),
                      "filas_en_el_csv": len(kept)}, ensure_ascii=False, indent=1))
    print("Ahora run_benchmarks.sh la volverá a ver como pendiente.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
