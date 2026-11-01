"""Pruebas de benchmark_runner/schedule.py: qué falta por correr de la matriz (F8).

Lo que se protege: que una tanda cortada se reanude sin repetir ni saltarse nada,
que el conteo de A2 (36 o 54) se respete, y que Q2_MEM_HIGH quede al final para
que lo primero que se corre valga con los dos conteos (decisión de Alix).
"""

from __future__ import annotations

import csv
import shutil
import tempfile
import unittest
from pathlib import Path

from benchmark_runner import csv_writer, matrix, schedule


def write_csv(path: Path, keys) -> None:
    """CSV con el encabezado real y una fila por clave (solo las columnas de la clave importan)."""
    with path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(csv_writer.COLUMNS)
        for engine, profile, query_id, conc, run in keys:
            row = {c: "" for c in csv_writer.COLUMNS}
            row.update({"engine": engine, "profile": profile, "query_id": query_id,
                        "concurrency": conc, "run_number": run, "status": "ok"})
            w.writerow([row[c] for c in csv_writer.COLUMNS])


class ScheduleTest(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.csv = self.dir / "measurements.csv"

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_without_csv_everything_is_pending(self):
        pend = schedule.pending(self.csv, 54)
        self.assertEqual(len(pend), 54)
        self.assertEqual(sum(len(r) for _, r in pend), 162)
        self.assertEqual(schedule.summary(self.csv, 54)["faltan"], 162)

    def test_36_cells_needs_a_variant_and_gives_108_runs(self):
        pend = schedule.pending(self.csv, 36, q2_variant="MEM_LOW")
        self.assertEqual(sum(len(r) for _, r in pend), 108)
        self.assertEqual({c.query_id for c, _ in pend}, {"Q1", "Q2"})

    def test_done_runs_are_skipped_and_the_rest_of_the_cell_stays(self):
        cell = sorted(matrix.cells(54), key=schedule.order)[0]
        write_csv(self.csv, [(cell.engine, cell.profile, cell.query_id, cell.concurrency, 1),
                             (cell.engine, cell.profile, cell.query_id, cell.concurrency, 2)])
        pend = dict(((c.engine, c.profile, c.query_id, c.concurrency), r) for c, r in schedule.pending(self.csv, 54))
        self.assertEqual(pend[(cell.engine, cell.profile, cell.query_id, cell.concurrency)], [3])
        self.assertEqual(schedule.summary(self.csv, 54)["hechas"], 2)

    def test_a_finished_cell_disappears(self):
        cell = sorted(matrix.cells(54), key=schedule.order)[0]
        write_csv(self.csv, [(cell.engine, cell.profile, cell.query_id, cell.concurrency, r) for r in (1, 2, 3)])
        pend = schedule.pending(self.csv, 54)
        self.assertEqual(len(pend), 53)
        self.assertNotIn(cell.cell_id, [c.cell_id for c, _ in pend])

    def test_q2_mem_high_goes_last(self):
        """A2: la tanda 1 (Q1 + Q2_MEM_LOW) vale tanto si el docente dice 36 como 54."""
        pend = schedule.pending(self.csv, 54)
        high = [i for i, (c, _) in enumerate(pend) if c.query_id == "Q2_MEM_HIGH"]
        self.assertEqual(high, list(range(36, 54)))

    def test_filters_by_engine_profile_and_query(self):
        pend = schedule.pending(self.csv, 54, engines=("mongodb",), profiles=("PROFILE_C_SEVERE",),
                                query_ids=("Q1", "Q2_MEM_LOW"))
        self.assertEqual(len(pend), 6)                       # 2 queries × 3 concurrencias
        self.assertTrue(all(c.engine == "mongodb" and c.profile == "PROFILE_C_SEVERE" for c, _ in pend))

    def test_filters_by_concurrency(self):
        """El humo de run_benchmarks.sh corre solo c=1: sin este filtro forzaría la
        concurrencia de celdas de c=10 y c=50 y escribiría filas duplicadas."""
        pend = schedule.pending(self.csv, 54, engines=("mongodb",), profiles=("PROFILE_C_SEVERE",),
                                query_ids=("Q2_MEM_LOW",), concurrencies=(1,))
        self.assertEqual(len(pend), 1)
        self.assertEqual(pend[0][0].concurrency, 1)

    def test_rows_from_another_matrix_are_reported_not_ignored(self):
        """Si el CSV trae Q2_MEM_LOW y luego se elige la matriz de 36, hay que verlo."""
        write_csv(self.csv, [("mongodb", "PROFILE_A_BASELINE", "Q2_MEM_LOW", 1, 1)])
        s = schedule.summary(self.csv, 36, q2_variant="MEM_LOW")
        self.assertEqual(s["hechas"], 0)
        self.assertEqual(s["ajenas_a_esta_matriz"], [("mongodb", "PROFILE_A_BASELINE", "Q2_MEM_LOW", 1, 1)])

    def test_incomplete_rows_do_not_count_as_done(self):
        with self.csv.open("w", newline="") as f:
            w = csv.writer(f)
            w.writerow(csv_writer.COLUMNS)
            w.writerow([""] * len(csv_writer.COLUMNS))
        self.assertEqual(schedule.done(self.csv), set())
        self.assertEqual(schedule.summary(self.csv, 54)["faltan"], 162)


if __name__ == "__main__":
    unittest.main()
