"""base.py — contrato común de los adaptadores de motor (F5.3).

Un adaptador = UNA conexión de UN worker para UNA celda. Se configura una vez
(variante y límite de tiempo) y luego ejecuta la misma query en bucle.

Reglas:
  - La query se lee de queries/ en el momento de construir el adaptador. Nunca
    está escrita en el código (CLAUDE.md, trampas conocidas).
  - execute() consume TODAS las filas del resultado: la latencia incluye la
    transferencia al cliente, igual en los dos motores (SPEC §2, decisión 4).
  - Los errores se traducen a QueryTimeout o QueryFailed para que el runner los
    cuente como fallos sin detenerse (A4).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from benchmark_runner.config import QUERY_TIMEOUT_S
from benchmark_runner.env import QUERIES_DIR, load_env
from benchmark_runner.matrix import QUERY_FILES, Cell


class QueryTimeout(Exception):
    """La query superó el límite de tiempo (A4, F5-f)."""


class QueryFailed(Exception):
    """Cualquier otro error al ejecutar la query."""


class Engine(ABC):
    engine: str          # "mongodb" | "postgresql"
    subdir: str          # carpeta en queries/
    suffix: str          # extensión del archivo de la query

    def __init__(self, cell: Cell, *, timeout_s: float = QUERY_TIMEOUT_S, env: dict | None = None):
        if cell.engine != self.engine:
            raise ValueError(f"celda de {cell.engine} en un adaptador de {self.engine}")
        self.cell = cell
        self.timeout_s = timeout_s
        self.env = env or load_env()
        self.query_text = self.query_path().read_text()
        self._connected = False

    def query_path(self) -> Path:
        return QUERIES_DIR / self.subdir / f"{QUERY_FILES[self.cell.query]}{self.suffix}"

    # --- ciclo de vida ---------------------------------------------------------
    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *exc):
        self.close()

    @abstractmethod
    def connect(self) -> None: ...

    @abstractmethod
    def close(self) -> None: ...

    @abstractmethod
    def _rows(self) -> list:
        """Ejecuta la query y devuelve todas las filas (o lanza QueryTimeout/QueryFailed)."""

    @abstractmethod
    def normalize(self, rows: list):
        """Filas → forma comparable con check_equivalence.py (Q1: dict por grupo; Q2: lista)."""

    @abstractmethod
    def session_info(self) -> dict:
        """Lo que la sesión tiene aplicado de verdad (p. ej. SHOW work_mem, R-17)."""

    @abstractmethod
    def explain(self):
        """Plan de ejecución con estadísticas reales (R-31). Ejecuta la query: nunca dentro de la ventana."""

    # --- uso -------------------------------------------------------------------
    def execute(self) -> int:
        """Una ejecución completa. Devuelve cuántas filas devolvió."""
        return len(self._rows())

    def fetch(self):
        """Una ejecución con el resultado normalizado (para verificar, no para medir)."""
        return self.normalize(self._rows())


def make_engine(cell: Cell, **kw) -> Engine:
    if cell.engine == "mongodb":
        from benchmark_runner.engines.mongo import MongoEngine
        return MongoEngine(cell, **kw)
    from benchmark_runner.engines.postgres import PostgresEngine
    return PostgresEngine(cell, **kw)
