#!/usr/bin/env python3
"""validate_csv.py — valida un CSV de mediciones contra el esquema del manual (R-26, R-27).

Uso:
    python3 scripts/validate_csv.py results/measurements.csv [--matrix 54|36]
                                    [--header-spaces] [--expect-rows N]

Comprueba:
  - encabezado EXACTO, byte a byte (por defecto sin espacios, F5-h; con
    --header-spaces, el de ", " literal del PDF);
  - 14 columnas en cada fila;
  - tipos y dominios cerrados: las MISMAS reglas que usa el escritor
    (benchmark_runner.csv_writer.check_row), así no pueden discrepar;
  - sin filas duplicadas por (engine, profile, query_id, concurrency, run_number);
  - opcionalmente, el número de filas (108 o 162 según A2).

Código de salida: 0 si el archivo es válido; 1 si no (lista cada problema).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from benchmark_runner import csv_writer as S  # noqa: E402

INT_COLS = ("timestamp_epoch", "concurrency", "run_number")
FLOAT_COLS = ("throughput_qps", *S.LATENCY_COLUMNS, "cpu_throttled_seconds", "max_rss_mb")
KEY = ("engine", "profile", "query_id", "concurrency", "run_number")


def parse_row(values: list[str]) -> dict:
    """Texto del CSV → valores tipados. Lanza SchemaError si un valor no se puede leer."""
    row = dict(zip(S.COLUMNS, values))
    try:
        for c in INT_COLS:
            row[c] = int(row[c])
        for c in FLOAT_COLS:
            row[c] = None if row[c] == "" else float(row[c])
    except ValueError as exc:
        raise S.SchemaError(f"valor no numérico: {exc}") from None
    if row["disk_spill"] not in ("true", "false"):
        raise S.SchemaError(f"disk_spill debe ser true/false: {row['disk_spill']!r}")
    row["disk_spill"] = row["disk_spill"] == "true"
    return row


def validate(path: Path, *, matrix: int = 54, header_spaces: bool = False,
             expect_rows: int | None = None) -> list[str]:
    problems: list[str] = []
    lines = path.read_text().split("\n")
    if lines and lines[-1] == "":
        lines.pop()                       # el archivo termina en salto de línea
    if not lines:
        return ["archivo vacío"]
    expected = S.header(header_spaces)
    if lines[0] != expected:
        problems.append(f"línea 1: encabezado distinto.\n    esperado: {expected!r}\n    obtenido: {lines[0]!r}")
    seen: dict[tuple, int] = {}
    for n, line in enumerate(lines[1:], start=2):
        values = line.split(",")
        if len(values) != len(S.COLUMNS):
            problems.append(f"línea {n}: {len(values)} columnas, se esperaban {len(S.COLUMNS)}")
            continue
        try:
            row = parse_row(values)
            S.check_row(row, matrix=matrix)
        except S.SchemaError as exc:
            problems.append(f"línea {n}: {exc}")
            continue
        key = tuple(row[k] for k in KEY)
        if key in seen:
            problems.append(f"línea {n}: fila duplicada de la línea {seen[key]}: {key}")
        seen.setdefault(key, n)
    rows = len(lines) - 1
    if expect_rows is not None and rows != expect_rows:
        problems.append(f"{rows} filas de datos, se esperaban {expect_rows}")
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("csv", type=Path)
    parser.add_argument("--matrix", type=int, choices=(54, 36), default=54, help="conteo de celdas (A2)")
    parser.add_argument("--header-spaces", action="store_true", help='encabezado con ", " (F5-h)')
    parser.add_argument("--expect-rows", type=int)
    args = parser.parse_args(argv)
    problems = validate(args.csv, matrix=args.matrix, header_spaces=args.header_spaces,
                        expect_rows=args.expect_rows)
    if problems:
        print(f"INVÁLIDO: {args.csv} — {len(problems)} problema(s)")
        for p in problems:
            print(f"  - {p}")
        return 1
    print(f"VÁLIDO: {args.csv}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
