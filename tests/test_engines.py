"""Adaptadores de motor (F5.3), sin servidores: opciones, sesión, lectura de queries y errores.

Requiere los drivers del .venv (si no están, se omite):
    .venv/bin/python -m unittest discover -s tests -v
"""

import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

HAVE_DRIVERS = all(importlib.util.find_spec(m) for m in ("pymongo", "psycopg"))

from benchmark_runner import matrix as M  # noqa: E402

ENV = {"MONGO_DB": "bench", "POSTGRES_DB": "bench", "POSTGRES_USER": "bench", "POSTGRES_PASSWORD": "x"}


def cell(engine, query_id):
    return next(c for c in M.cells(54) if c.engine == engine and c.query_id == query_id)


@unittest.skipUnless(HAVE_DRIVERS, "drivers no instalados: usar .venv/bin/python")
class OpcionesTest(unittest.TestCase):

    def test_mongo_variantes_y_timeout(self):
        from benchmark_runner.engines.mongo import aggregate_kwargs
        self.assertEqual(aggregate_kwargs(cell("mongodb", "Q2_MEM_LOW"), 300), {"maxTimeMS": 300000, "allowDiskUse": False})
        self.assertEqual(aggregate_kwargs(cell("mongodb", "Q2_MEM_HIGH"), 300), {"maxTimeMS": 300000, "allowDiskUse": True})
        # Q1: sin allowDiskUse, por defecto del servidor (igual que check_equivalence.py)
        self.assertEqual(aggregate_kwargs(cell("mongodb", "Q1"), 300), {"maxTimeMS": 300000})
        self.assertEqual(aggregate_kwargs(cell("mongodb", "Q1"), 0.0001)["maxTimeMS"], 1)   # nunca 0 (= sin límite)

    def test_postgres_sesion(self):
        from benchmark_runner.engines.postgres import session_statements
        self.assertEqual(session_statements(cell("postgresql", "Q2_MEM_LOW"), 300),
                         ["SET statement_timeout = '300000ms'", "SET work_mem = '4MB'"])
        self.assertEqual(session_statements(cell("postgresql", "Q2_MEM_HIGH"), 300)[1], "SET work_mem = '64MB'")
        # Q1: work_mem por defecto (SPEC A12)
        self.assertEqual(session_statements(cell("postgresql", "Q1"), 300), ["SET statement_timeout = '300000ms'"])
        self.assertEqual(session_statements(cell("postgresql", "Q1"), 0.0001)[0], "SET statement_timeout = '1ms'")


@unittest.skipUnless(HAVE_DRIVERS, "drivers no instalados: usar .venv/bin/python")
class QueriesDesdeDiscoTest(unittest.TestCase):
    """El adaptador lee el archivo de queries/ tal cual: es el que se verificó contra el PDF."""

    def test_texto_identico_al_archivo(self):
        from benchmark_runner.engines.base import make_engine
        for engine in ("mongodb", "postgresql"):
            for qid in ("Q1", "Q2_MEM_LOW"):
                e = make_engine(cell(engine, qid), env=ENV)
                self.assertEqual(e.query_text, e.query_path().read_text())
                self.assertTrue(e.query_path().is_relative_to(ROOT / "queries"))

    def test_rechaza_celda_de_otro_motor(self):
        from benchmark_runner.engines.mongo import MongoEngine
        with self.assertRaises(ValueError):
            MongoEngine(cell("postgresql", "Q1"), env=ENV)


@unittest.skipUnless(HAVE_DRIVERS, "drivers no instalados: usar .venv/bin/python")
class ErroresTest(unittest.TestCase):
    """Los errores de cada driver se traducen a QueryTimeout / QueryFailed."""

    def test_mongo(self):
        from pymongo.errors import ExecutionTimeout, OperationFailure
        from benchmark_runner.engines.base import QueryFailed, QueryTimeout
        from benchmark_runner.engines.mongo import MongoEngine
        e = MongoEngine(cell("mongodb", "Q1"), env=ENV)
        e.pipeline, e.kwargs = [], {}
        for exc, expected in ((ExecutionTimeout("tiempo"), QueryTimeout), (OperationFailure("x"), QueryFailed)):
            class Coll:
                def aggregate(self, *a, _exc=exc, **k):
                    raise _exc
            e.coll = Coll()
            with self.assertRaises(expected):
                e.execute()

    def test_postgres(self):
        import psycopg
        from psycopg import errors
        from benchmark_runner.engines.base import QueryFailed, QueryTimeout
        from benchmark_runner.engines.postgres import PostgresEngine
        e = PostgresEngine(cell("postgresql", "Q1"), env=ENV)
        for exc, expected in ((errors.QueryCanceled("canceling statement due to statement timeout"), QueryTimeout),
                              (psycopg.OperationalError("conexión perdida"), QueryFailed)):
            class Conn:
                def execute(self, *a, _exc=exc, **k):
                    raise _exc
            e.conn = Conn()
            with self.assertRaises(expected):
                e.execute()


@unittest.skipUnless(HAVE_DRIVERS, "drivers no instalados: usar .venv/bin/python")
class NormalizacionTest(unittest.TestCase):

    def test_formas_iguales_a_check_equivalence(self):
        from decimal import Decimal
        from benchmark_runner.engines.mongo import MongoEngine
        from benchmark_runner.engines.postgres import PostgresEngine
        m = MongoEngine(cell("mongodb", "Q1"), env=ENV)
        self.assertEqual(m.normalize([{"_id": {"country": "MX", "category": "toys"}, "total_revenue": 1.5,
                                       "avg_revenue": 0.75, "count": 2}]),
                         {"MX|toys": {"total": 1.5, "avg": 0.75, "count": 2}})
        m2 = MongoEngine(cell("mongodb", "Q2_MEM_LOW"), env=ENV)
        self.assertEqual(m2.normalize([{"_id": 1, "order_id": "a", "customer": {"id": "C1"}, "payment": {"final_total": 9.5}}]),
                         [["a", "C1", 9.5]])
        p = PostgresEngine(cell("postgresql", "Q1"), env=ENV)
        self.assertEqual(p.normalize([("MX", "toys", Decimal("1.50"), Decimal("0.75"), 2)]),
                         {"MX|toys": {"total": Decimal("1.50"), "avg": Decimal("0.75"), "count": 2}})


if __name__ == "__main__":
    unittest.main()
