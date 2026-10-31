"""spill.py — detección de volcado a disco por motor, como delta en la ventana (A6, F5-a).

PostgreSQL: Δ de pg_stat_database.temp_files / temp_bytes de la base del
            experimento entre inicio y fin de la ventana. > 0 → hubo volcado.
MongoDB:    Δ de todos los contadores numéricos de serverStatus() cuyo nombre
            contiene "spill" (sin suponer nombres concretos: varían entre
            versiones). Se guardan todos, crudos, para el reporte.

Un booleano colapsa una realidad graduada (A6): por eso se registran también
los bytes o contadores, no solo true/false.
"""

from __future__ import annotations


def flatten(doc, prefix: str = "") -> dict[str, float]:
    out = {}
    if isinstance(doc, dict):
        for k, v in doc.items():
            out.update(flatten(v, f"{prefix}.{k}" if prefix else str(k)))
    elif isinstance(doc, (int, float)) and not isinstance(doc, bool):
        out[prefix] = doc
    return out


def mongo_spill_counters(server_status: dict) -> dict[str, float]:
    return {k: v for k, v in flatten(server_status).items() if "spill" in k.lower()}


def counter_delta(start: dict, end: dict) -> dict[str, float]:
    """Δ de cada contador presente en ambos snapshots. Un contador que baja (reinicio) no cuenta."""
    num = lambda v: isinstance(v, (int, float)) and not isinstance(v, bool)  # noqa: E731
    return {k: end[k] - start[k] for k in start.keys() & end.keys()
            if num(start[k]) and num(end[k]) and end[k] - start[k] > 0}


PG_TEMP_SQL = "SELECT temp_files, temp_bytes FROM pg_stat_database WHERE datname = current_database()"


def pg_temp_counters(conn) -> dict[str, int]:
    files, size = conn.execute(PG_TEMP_SQL).fetchone()
    return {"temp_files": int(files), "temp_bytes": int(size)}
