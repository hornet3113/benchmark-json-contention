"""mongo.py — adaptador de MongoDB con pymongo (F5.3).

La variante de Q2 es una opción de aggregate(): allowDiskUse false/true
(playbook.pdf §5.2). Q1 no la recibe: corre con el valor por defecto del
servidor, igual que en check_equivalence.py. El límite de 300 s es maxTimeMS (F5-f).
"""

from __future__ import annotations

import json

from bson import SON
from pymongo import MongoClient
from pymongo.errors import ExecutionTimeout, PyMongoError

from benchmark_runner.engines.base import Engine, QueryFailed, QueryTimeout

URI = "mongodb://127.0.0.1:27017"   # puerto publicado solo en loopback (docker-compose.yml)


def aggregate_kwargs(cell, timeout_s: float) -> dict:
    """Opciones de aggregate() para la celda. Función pura: se prueba sin servidor."""
    kw = {"maxTimeMS": max(1, int(timeout_s * 1000))}
    allow = cell.option("allowDiskUse")
    if allow is not None:
        kw["allowDiskUse"] = allow
    return kw


class MongoEngine(Engine):
    engine, subdir, suffix = "mongodb", "mongo", ".json"

    def connect(self) -> None:
        # El texto del archivo ES el pipeline: JSON → lista de etapas, sin tocarlo.
        self.pipeline = json.loads(self.query_text)
        self.kwargs = aggregate_kwargs(self.cell, self.timeout_s)
        # Una conexión por worker: el pool no reparte trabajo entre workers.
        self.client = MongoClient(URI, maxPoolSize=1, serverSelectionTimeoutMS=30_000)
        self.coll = self.client[self.env["MONGO_DB"]]["orders"]
        self.client.admin.command("ping")
        self._connected = True

    def close(self) -> None:
        if self._connected:
            self.client.close()
            self._connected = False

    def _rows(self) -> list:
        try:
            return list(self.coll.aggregate(self.pipeline, **self.kwargs))
        except ExecutionTimeout as exc:
            raise QueryTimeout(str(exc)) from exc
        except PyMongoError as exc:
            raise QueryFailed(f"{type(exc).__name__}: {exc}") from exc

    def normalize(self, rows: list):
        if self.cell.query == "Q1":
            return {f"{r['_id']['country']}|{r['_id']['category']}":
                    {"total": r["total_revenue"], "avg": r["avg_revenue"], "count": r["count"]} for r in rows}
        return [[r["order_id"], r["customer"]["id"], r["payment"]["final_total"]] for r in rows]

    def session_info(self) -> dict:
        return {"aggregate_kwargs": self.kwargs}

    def explain(self):
        # El mismo aggregate con las mismas opciones, envuelto en explain executionStats.
        cmd = SON([("aggregate", "orders"), ("pipeline", self.pipeline), ("cursor", {}), *self.kwargs.items()])
        return self.client[self.env["MONGO_DB"]].command("explain", cmd, verbosity="executionStats")
