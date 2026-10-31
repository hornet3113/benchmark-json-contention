"""matrix.py — la matriz de escenarios, parametrizable para 36 o 54 celdas (A2).

A2 sigue PENDIENTE DEL DOCENTE (CLAUDE.md):
  54 celdas (propuesta): 2 motores × 3 perfiles × {Q1, Q2_MEM_LOW, Q2_MEM_HIGH} × 3 concurrencias
  36 celdas (literal de §6): 2 motores × 3 perfiles × {Q1, Q2} × 3 concurrencias; con una sola
                              variante de Q2, que hay que elegir explícitamente (q2_variant).
Cada celda × 3 repeticiones: 162 o 108 corridas.

Variantes de Q2 (playbook.pdf §5.2), que solo cambian CÓMO se ejecuta la query:
  MEM_LOW  = Mongo allowDiskUse:false · Postgres work_mem '4MB'   (la restrictiva)
  MEM_HIGH = Mongo allowDiskUse:true  · Postgres work_mem '64MB'
Q1 no tiene variantes: corre con la configuración por defecto (Postgres:
work_mem por defecto, 4MB; decisión de Alix, SPEC A12).

Orden: por bloques de motor y perfil, como recomienda PLAN F8. Así un bloque
cabe en una sesión, y cambiar de perfil es solo reiniciar el contenedor.
"""

from __future__ import annotations

from dataclasses import dataclass

from benchmark_runner.config import CONCURRENCIES, ENGINES, PROFILES, REPETITIONS

QUERY_FILES = {"Q1": "q1_unwind_group", "Q2": "q2_sort_topk"}
VARIANTS = {
    "MEM_LOW": {"mongodb": {"allowDiskUse": False}, "postgresql": {"work_mem": "4MB"}},
    "MEM_HIGH": {"mongodb": {"allowDiskUse": True}, "postgresql": {"work_mem": "64MB"}},
}


@dataclass(frozen=True)
class Cell:
    engine: str
    profile: str
    query_id: str       # valor literal de la columna query_id del CSV
    query: str          # "Q1" | "Q2": qué archivo de queries/ se ejecuta
    options: tuple      # opciones de ejecución, p. ej. (("work_mem", "4MB"),)
    concurrency: int

    @property
    def cell_id(self) -> str:
        return f"{self.engine}_{self.profile}_{self.query_id}_c{self.concurrency}"

    def option(self, name: str, default=None):
        return dict(self.options).get(name, default)


@dataclass(frozen=True)
class Run:
    cell: Cell
    run_number: int

    @property
    def run_id(self) -> str:
        return f"{self.cell.cell_id}_r{self.run_number}"


def _queries(mode: int, q2_variant: str | None) -> list[tuple[str, str, str | None]]:
    """(query_id, query, variante) según el conteo de A2."""
    if mode == 54:
        if q2_variant is not None:
            raise ValueError("con 54 celdas se corren las dos variantes de Q2: no se elige q2_variant")
        return [("Q1", "Q1", None), ("Q2_MEM_LOW", "Q2", "MEM_LOW"), ("Q2_MEM_HIGH", "Q2", "MEM_HIGH")]
    if mode == 36:
        if q2_variant not in VARIANTS:
            raise ValueError(f"con 36 celdas hay que elegir explícitamente q2_variant entre {list(VARIANTS)}")
        return [("Q1", "Q1", None), ("Q2", "Q2", q2_variant)]
    raise ValueError(f"conteo de celdas no válido: {mode} (A2: 36 o 54)")


def cells(mode: int = 54, q2_variant: str | None = None) -> list[Cell]:
    out = []
    for engine in ENGINES:
        for profile in PROFILES:
            for query_id, query, variant in _queries(mode, q2_variant):
                opts = tuple(sorted(VARIANTS[variant][engine].items())) if variant else ()
                for c in CONCURRENCIES:
                    out.append(Cell(engine, profile, query_id, query, opts, c))
    return out


def runs(mode: int = 54, q2_variant: str | None = None) -> list[Run]:
    return [Run(cell, r) for cell in cells(mode, q2_variant) for r in REPETITIONS]
