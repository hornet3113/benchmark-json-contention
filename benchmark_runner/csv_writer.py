"""csv_writer.py — ÚNICO lugar del proyecto que conoce el esquema del CSV (R-26).

Esquema exigido por playbook.pdf §8.2 (p.4) y diapo 9/13: 14 columnas, en este
orden, sin agregar, quitar ni renombrar ninguna (CLAUDE.md, regla 8).

Encabezado (F5-h): el PDF lo escribe con un espacio después de cada coma.
Por defecto se escribe SIN espacios: con espacios, las columnas se llamarían
" engine", " profile"… y casi cualquier herramienta lo leería mal. Es un
parámetro (header_spaces) para poder regenerar con ", " si el docente lo pide.
La decisión se declara en la sección 2 del reporte.

Una fila por repetición, escrita y sincronizada a disco al cerrar cada
repetición (SPEC §2, decisión 6): si la corrida se corta, lo medido sobrevive.
scripts/validate_csv.py usa las definiciones de este módulo.
"""

from __future__ import annotations

import os
from pathlib import Path

COLUMNS = (
    "timestamp_epoch", "engine", "profile", "query_id", "concurrency", "run_number",
    "throughput_qps", "latency_p50_ms", "latency_p95_ms", "latency_p99_ms",
    "cpu_throttled_seconds", "max_rss_mb", "disk_spill", "status",
)

ENGINES = ("mongodb", "postgresql")
PROFILES = ("PROFILE_A_BASELINE", "PROFILE_B_MEDIUM", "PROFILE_C_SEVERE")
# A2 pendiente del docente: con 54 celdas la variante de Q2 va en query_id;
# con 36, Q2 es una sola. El validador recibe cuál aplica.
QUERY_IDS = {54: ("Q1", "Q2_MEM_LOW", "Q2_MEM_HIGH"), 36: ("Q1", "Q2")}
CONCURRENCIES = (1, 10, 50)
RUN_NUMBERS = (1, 2, 3)
STATUSES = ("ok", "spill", "oom", "error")
LATENCY_COLUMNS = ("latency_p50_ms", "latency_p95_ms", "latency_p99_ms")
# Columnas que pueden quedar VACÍAS, y solo con status error u oom: vacío
# significa "no se pudo medir" (p. ej. < 2 muestras, A4; o el contenedor murió
# por OOM y su cgroup desapareció). Nunca se rellenan con 0: un 0 de throttling
# afirmaría "se midió y dio cero" (CLAUDE.md, regla 7). throughput nunca va vacío.
NULLABLE_COLUMNS = (*LATENCY_COLUMNS, "cpu_throttled_seconds", "max_rss_mb")
NULLABLE_STATUSES = ("error", "oom")
# SPEC §4 fija 3 decimales para las latencias. El throughput lleva 6: con una
# ventana de 300 s cada consulta completada suma 1/300 = 0.00333 qps, y con 3
# decimales se perdería el conteo exacto justo en las celdas con pocas
# muestras (PROFILE_C, concurrencia 50). Con 6, completadas = qps × 300 se
# recupera sin ambigüedad.
FLOAT_DECIMALS = {"throughput_qps": 6}
DEFAULT_FLOAT_DECIMALS = 3


class SchemaError(ValueError):
    """Una fila que no cumple el esquema. Nunca se escribe."""


def header(header_spaces: bool = False) -> str:
    return (", " if header_spaces else ",").join(COLUMNS)


def resolve_status(*, oom: bool, error: bool, spill: bool) -> str:
    """Precedencia de SPEC §4: oom > error > spill > ok."""
    if oom:
        return "oom"
    if error:
        return "error"
    if spill:
        return "spill"
    return "ok"


def _fmt(value, column: str) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return f"{value:.{FLOAT_DECIMALS.get(column, DEFAULT_FLOAT_DECIMALS)}f}"
    return str(value)


def check_row(row: dict, *, matrix: int = 54) -> None:
    """Lanza SchemaError si la fila no cumple el esquema. Mismas reglas que validate_csv.py."""
    keys = tuple(row)
    if set(keys) != set(COLUMNS):
        missing = [c for c in COLUMNS if c not in row]
        extra = [k for k in keys if k not in COLUMNS]
        raise SchemaError(f"columnas distintas al esquema: faltan {missing}, sobran {extra}")

    def need(cond: bool, msg: str) -> None:
        if not cond:
            raise SchemaError(msg)

    need(isinstance(row["timestamp_epoch"], int) and not isinstance(row["timestamp_epoch"], bool)
         and row["timestamp_epoch"] > 0, f"timestamp_epoch inválido: {row['timestamp_epoch']!r}")
    need(row["engine"] in ENGINES, f"engine fuera de dominio: {row['engine']!r}")
    need(row["profile"] in PROFILES, f"profile fuera de dominio: {row['profile']!r}")
    need(row["query_id"] in QUERY_IDS[matrix], f"query_id fuera de dominio ({matrix} celdas): {row['query_id']!r}")
    need(row["concurrency"] in CONCURRENCIES, f"concurrency fuera de dominio: {row['concurrency']!r}")
    need(row["run_number"] in RUN_NUMBERS, f"run_number fuera de dominio: {row['run_number']!r}")
    need(row["status"] in STATUSES, f"status fuera de dominio: {row['status']!r}")
    need(isinstance(row["disk_spill"], bool), f"disk_spill debe ser booleano: {row['disk_spill']!r}")
    # SPEC §4: status=ok con disk_spill=true está prohibido.
    need(not (row["status"] == "ok" and row["disk_spill"]), "status=ok con disk_spill=true está prohibido")

    for col in ("throughput_qps", "cpu_throttled_seconds", "max_rss_mb", *LATENCY_COLUMNS):
        v = row[col]
        if v is None:
            need(col in NULLABLE_COLUMNS and row["status"] in NULLABLE_STATUSES,
                 f"{col} vacío solo se permite en {NULLABLE_COLUMNS} con status en {NULLABLE_STATUSES}")
            continue
        need(isinstance(v, (int, float)) and not isinstance(v, bool) and v >= 0, f"{col} inválido: {v!r}")
    lat = [row[c] for c in LATENCY_COLUMNS]
    need(all(v is None for v in lat) or all(v is not None for v in lat), "latencias: o las tres o ninguna")
    if lat[0] is not None:
        need(lat[0] <= lat[1] <= lat[2], f"percentiles no ordenados: {lat}")


def format_row(row: dict) -> str:
    return ",".join(_fmt(row[c], c) for c in COLUMNS)


class CsvWriter:
    """Agrega filas a un CSV; escribe el encabezado si el archivo es nuevo.

    Si el archivo ya existe, exige que su encabezado sea exactamente el
    esperado: nunca mezcla dos esquemas en un mismo archivo.
    """

    def __init__(self, path: Path, *, header_spaces: bool = False, matrix: int = 54):
        self.path = Path(path)
        self.header = header(header_spaces)
        self.matrix = matrix
        if self.path.exists() and self.path.stat().st_size:
            with self.path.open() as f:
                first = f.readline().rstrip("\n")
            if first != self.header:
                raise SchemaError(f"{self.path}: encabezado existente distinto al esperado: {first!r}")
        else:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._append(self.header)

    def _append(self, line: str) -> None:
        with self.path.open("a", newline="") as f:
            f.write(line + "\n")
            f.flush()
            os.fsync(f.fileno())

    def write(self, row: dict) -> None:
        check_row(row, matrix=self.matrix)
        self._append(format_row(row))
