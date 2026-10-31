"""Matriz parametrizable para 36 o 54 celdas (A2) y política de ventana / suspensión (A4, F5-d).

Correr:  python3 -m unittest discover -s tests -v     (también funciona con pytest)
"""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from benchmark_runner import csv_writer as S  # noqa: E402
from benchmark_runner import matrix as M  # noqa: E402
from benchmark_runner.metrics import window as W  # noqa: E402

S_NS = 1_000_000_000


class MatrizTest(unittest.TestCase):

    def test_54_celdas_162_corridas(self):
        self.assertEqual(len(M.cells(54)), 54)
        self.assertEqual(len(M.runs(54)), 162)

    def test_36_celdas_108_corridas_con_variante_explicita(self):
        self.assertEqual(len(M.cells(36, "MEM_LOW")), 36)
        self.assertEqual(len(M.runs(36, "MEM_HIGH")), 108)

    def test_36_sin_elegir_variante_falla(self):
        with self.assertRaises(ValueError):
            M.cells(36)

    def test_54_no_admite_variante(self):
        with self.assertRaises(ValueError):
            M.cells(54, "MEM_LOW")

    def test_ids_unicos(self):
        ids = [r.run_id for r in M.runs(54)]
        self.assertEqual(len(ids), len(set(ids)))

    def test_query_ids_en_el_dominio_del_csv(self):
        for mode, var in ((54, None), (36, "MEM_LOW")):
            self.assertTrue({c.query_id for c in M.cells(mode, var)} <= set(S.QUERY_IDS[mode]))

    def test_variantes_por_motor(self):
        cells = {(c.engine, c.query_id): c for c in M.cells(54)}
        self.assertIs(cells[("mongodb", "Q2_MEM_LOW")].option("allowDiskUse"), False)
        self.assertIs(cells[("mongodb", "Q2_MEM_HIGH")].option("allowDiskUse"), True)
        self.assertEqual(cells[("postgresql", "Q2_MEM_LOW")].option("work_mem"), "4MB")
        self.assertEqual(cells[("postgresql", "Q2_MEM_HIGH")].option("work_mem"), "64MB")
        self.assertEqual(cells[("postgresql", "Q1")].options, ())      # Q1: configuración por defecto

    def test_orden_por_bloques_de_motor_y_perfil(self):
        seq = [(c.engine, c.profile) for c in M.cells(54)]
        blocks = [seq[0]] + [b for a, b in zip(seq, seq[1:]) if a != b]
        self.assertEqual(len(blocks), 6)       # 2 motores × 3 perfiles, cada bloque contiguo


class VentanaTest(unittest.TestCase):
    """A4: cuentan las completadas dentro de la ventana; las en vuelo se descartan."""

    WS, WE = 100 * S_NS, 400 * S_NS     # ventana de 300 s

    def test_clasificacion(self):
        samples = [
            W.Sample(110 * S_NS, 120 * S_NS, True),    # dentro
            W.Sample(90 * S_NS, 105 * S_NS, True),     # empezó en el calentamiento, terminó dentro: cuenta
            W.Sample(390 * S_NS, 410 * S_NS, True),    # seguía en vuelo al cerrar: se descarta
            W.Sample(50 * S_NS, 60 * S_NS, True),      # calentamiento: no cuenta
            W.Sample(200 * S_NS, 210 * S_NS, False),   # falló dentro: no es latencia
        ]
        r = W.classify(samples, self.WS, self.WE)
        self.assertEqual(r.completed_ok, 2)
        self.assertEqual(r.failed_in_window, 1)
        self.assertEqual(r.started_before_window, 1)
        self.assertEqual(sorted(r.latencies_ms), [10_000.0, 15_000.0])
        self.assertAlmostEqual(r.throughput_qps, 2 / 300)

    def test_ventana_sin_completadas(self):
        r = W.classify([W.Sample(150 * S_NS, 500 * S_NS, True)], self.WS, self.WE)
        self.assertEqual((r.completed_ok, r.throughput_qps, r.latencies_ms), (0, 0.0, []))


class SuspensionTest(unittest.TestCase):

    def snap(self, wall, mono, boot):
        return W.ClockSnapshot(int(wall * S_NS), int(mono * S_NS), int(boot * S_NS))

    def test_sin_suspension(self):
        c = W.check_suspension(self.snap(0, 0, 0), self.snap(300.4, 300, 300.1))
        self.assertFalse(c.suspended)
        self.assertIsNone(c.reason)

    def test_vm_congelada_reloj_de_pared(self):
        # Lo que se vio en F3-G3: el reloj de pared avanza mucho más que el monotónico.
        c = W.check_suspension(self.snap(0, 0, 0), self.snap(3180, 210, 210))
        self.assertTrue(c.suspended)
        self.assertIn("suspensión", c.reason)

    def test_suspension_solo_en_boottime(self):
        self.assertTrue(W.check_suspension(self.snap(0, 0, 0), self.snap(300, 300, 360)).suspended)

    def test_salto_hacia_atras_del_reloj_de_pared(self):
        self.assertTrue(W.check_suspension(self.snap(0, 0, 0), self.snap(290, 300, 300)).suspended)

    def test_umbral(self):
        self.assertFalse(W.check_suspension(self.snap(0, 0, 0), self.snap(302.0, 300, 300)).suspended)
        self.assertTrue(W.check_suspension(self.snap(0, 0, 0), self.snap(302.5, 300, 300)).suspended)

    def test_snapshot_real_tiene_los_tres_relojes(self):
        s = W.snapshot()
        self.assertGreater(s.wall_ns, 0)
        self.assertGreater(s.mono_ns, 0)
        self.assertGreaterEqual(s.boot_ns, s.mono_ns)


if __name__ == "__main__":
    unittest.main()
