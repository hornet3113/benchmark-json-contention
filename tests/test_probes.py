"""Pruebas de la lógica de las sondas de F6.3 que no necesita motores.

Lo que se protege: que la confirmación por EXPLAIN/explain no dé un falso
positivo (un `usedDisk: false` o `spills: 0` NO es volcado) ni un falso
negativo (los nombres de las claves cambian entre versiones de Mongo).
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "probes"))

import spill_mongo  # noqa: E402
import spill_postgres  # noqa: E402


class MongoDiskMarksTest(unittest.TestCase):
    def test_false_and_zero_are_not_disk(self):
        plan = {"stages": [{"$sort": {"usedDisk": False, "spills": 0, "spilledDataStorageSize": 0}}]}
        marks = spill_mongo.disk_marks(plan)
        self.assertEqual(len(marks), 3)
        self.assertFalse(spill_mongo.used_disk(marks))

    def test_true_or_positive_anywhere_is_disk(self):
        nested = {"queryPlanner": {}, "executionStats": {"executionStages": {"inputStage": {"usedDisk": True}}}}
        self.assertTrue(spill_mongo.used_disk(spill_mongo.disk_marks(nested)))
        self.assertTrue(spill_mongo.used_disk(spill_mongo.disk_marks([{"x": {"spills": 4}}])))

    def test_no_marks_is_not_disk(self):
        self.assertFalse(spill_mongo.used_disk(spill_mongo.disk_marks({"a": 1, "b": [1, 2]})))


class PostgresSortNodesTest(unittest.TestCase):
    def test_finds_nested_sorts(self):
        plan = {"Node Type": "Gather Merge", "Plans": [
            {"Node Type": "Sort", "Sort Method": "external merge", "Sort Space Type": "Disk", "Plans": []},
            {"Node Type": "Seq Scan"}]}
        nodes = spill_postgres.sort_nodes(plan)
        self.assertEqual([n["Sort Method"] for n in nodes], ["external merge"])

    def test_topn_is_not_external(self):
        plan = {"Node Type": "Limit", "Plans": [{"Node Type": "Sort", "Sort Method": "top-N heapsort",
                                                  "Sort Space Type": "Memory"}]}
        self.assertFalse(any("external" in n["Sort Method"] for n in spill_postgres.sort_nodes(plan)))


if __name__ == "__main__":
    unittest.main()
