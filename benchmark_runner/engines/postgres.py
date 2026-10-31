"""postgres.py — adaptador de PostgreSQL con psycopg 3 (F5.3).

La variante de Q2 es la sesión: SET work_mem = '4MB' / '64MB' (playbook.pdf
§5.2), aplicada una vez al conectar y confirmada con SHOW work_mem (R-17).
Q1 no la recibe: work_mem por defecto (4MB), decisión de Alix (SPEC A12).
El límite de 300 s es statement_timeout (F5-f). El SQL se envía tal cual
está en el archivo.
"""

from __future__ import annotations

import psycopg
from psycopg import errors

from benchmark_runner.engines.base import Engine, QueryFailed, QueryTimeout


def session_statements(cell, timeout_s: float) -> list[str]:
    """SET de la sesión para la celda. Función pura: se prueba sin servidor."""
    stmts = [f"SET statement_timeout = '{max(1, int(timeout_s * 1000))}ms'"]
    work_mem = cell.option("work_mem")
    if work_mem is not None:
        stmts.append(f"SET work_mem = '{work_mem}'")
    return stmts


class PostgresEngine(Engine):
    engine, subdir, suffix = "postgresql", "postgres", ".sql"

    def connect(self) -> None:
        e = self.env
        self.conn = psycopg.connect(host="127.0.0.1", port=5432, dbname=e["POSTGRES_DB"], user=e["POSTGRES_USER"],
                                    password=e["POSTGRES_PASSWORD"], autocommit=True, connect_timeout=30)
        self.statements = session_statements(self.cell, self.timeout_s)
        for stmt in self.statements:
            self.conn.execute(stmt)
        self.work_mem = self.conn.execute("SHOW work_mem").fetchone()[0]
        self.statement_timeout = self.conn.execute("SHOW statement_timeout").fetchone()[0]
        self._connected = True

    def close(self) -> None:
        if self._connected:
            self.conn.close()
            self._connected = False

    def _rows(self) -> list:
        try:
            # Sin parámetros: psycopg no interpreta el texto, lo envía tal cual.
            return self.conn.execute(self.query_text).fetchall()
        except errors.QueryCanceled as exc:      # statement_timeout
            raise QueryTimeout(str(exc).strip()) from exc
        except psycopg.Error as exc:
            raise QueryFailed(f"{type(exc).__name__}: {str(exc).strip()}") from exc

    def normalize(self, rows: list):
        if self.cell.query == "Q1":
            return {f"{country}|{category}": {"total": total, "avg": avg, "count": count}
                    for country, category, total, avg, count in rows}
        return [[oid, cust, final] for oid, cust, final in rows]

    def explain(self):
        # El texto del archivo, sin tocar, con EXPLAIN delante; misma sesión y mismo work_mem.
        return self.conn.execute("EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + self.query_text).fetchone()[0]

    def session_info(self) -> dict:
        return {"statements": self.statements, "SHOW work_mem": self.work_mem,
                "SHOW statement_timeout": self.statement_timeout}
