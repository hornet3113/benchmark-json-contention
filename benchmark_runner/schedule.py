"""schedule.py — qué repeticiones faltan por correr, leídas del CSV que ya existe (F8).

La matriz son 108 o 162 corridas (A2) de ~7.5 min: no cabe en una sesión. Este
módulo responde "¿qué falta?" comparando la matriz con las filas ya escritas, para
que `scripts/run_benchmarks.sh` se pueda cortar y reanudar sin repetir nada ni
saltarse nada. Vive aparte del script para poder probarlo sin sudo y sin motores.

Clave de una repetición: (engine, profile, query_id, concurrency, run_number), la
misma con la que `validate_csv.py` busca duplicados.

Decisión de Alix (2026-11-02) sobre A2, mientras el docente no responda: la
**tanda 1** son las 36 celdas de `Q1` + `Q2_MEM_LOW` (la variante restrictiva).
Si el docente dice 54, se añade `Q2_MEM_HIGH` en la tanda 2; si dice 36, solo se
cambia la etiqueta `Q2_MEM_LOW` → `Q2` y los datos siguen valiendo. Por eso el
orden pone Q2_MEM_HIGH al final: lo que se corre primero sirve en los dos casos.
"""

from __future__ import annotations

import csv
from collections.abc import Iterable
from pathlib import Path

from benchmark_runner import matrix

KEY_COLUMNS = ("engine", "profile", "query_id", "concurrency", "run_number")
# Lo último de la matriz: así una tanda cortada deja hecho lo que vale con 36 y con 54 (A2).
TANDA_2_QUERIES = ("Q2_MEM_HIGH",)


def key(engine: str, profile: str, query_id: str, concurrency, run_number) -> tuple:
    return (engine, profile, query_id, int(concurrency), int(run_number))


def done(csv_path: Path) -> set[tuple]:
    """Repeticiones que ya tienen fila. Un CSV inexistente o vacío es "nada hecho"."""
    if not csv_path.exists():
        return set()
    with csv_path.open(newline="") as f:
        rows = list(csv.DictReader(f))
    out = set()
    for r in rows:
        if all(r.get(c) not in (None, "") for c in KEY_COLUMNS):
            out.add(key(*(r[c] for c in KEY_COLUMNS)))
    return out


def order(cell: matrix.Cell) -> tuple:
    """Orden de la matriz: motor, perfil, query y concurrencia. Q2_MEM_HIGH al final (A2)."""
    return (cell.query_id in TANDA_2_QUERIES, cell.engine, cell.profile,
            cell.query_id, cell.concurrency)


def pending(csv_path: Path, mode: int = 54, q2_variant: str | None = None,
            engines: Iterable[str] | None = None, profiles: Iterable[str] | None = None,
            query_ids: Iterable[str] | None = None,
            concurrencies: Iterable[int] | None = None) -> list[tuple[matrix.Cell, list[int]]]:
    """[(celda, [repeticiones que faltan])] en orden de ejecución, sin celdas vacías."""
    have = done(csv_path)
    out = []
    for cell in sorted(matrix.cells(mode, q2_variant), key=order):
        if engines and cell.engine not in engines:
            continue
        if profiles and cell.profile not in profiles:
            continue
        if query_ids and cell.query_id not in query_ids:
            continue
        if concurrencies and cell.concurrency not in concurrencies:
            continue
        missing = [r for r in matrix.REPETITIONS
                   if key(cell.engine, cell.profile, cell.query_id, cell.concurrency, r) not in have]
        if missing:
            out.append((cell, missing))
    return out


def summary(csv_path: Path, mode: int = 54, q2_variant: str | None = None) -> dict:
    """Cuántas corridas hay, faltan y sobran (filas que la matriz elegida no pide)."""
    have = done(csv_path)
    total = {key(c.engine, c.profile, c.query_id, c.concurrency, r)
             for c in matrix.cells(mode, q2_variant) for r in matrix.REPETITIONS}
    return {"matriz": mode, "corridas_de_la_matriz": len(total), "hechas": len(have & total),
            "faltan": len(total - have), "ajenas_a_esta_matriz": sorted(have - total)}
