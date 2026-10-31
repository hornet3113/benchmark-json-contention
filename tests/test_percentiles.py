"""Percentiles (F5-b): valores conocidos, método declarado y el caso de < 2 muestras (ajuste 2).

Correr:  python3 -m unittest discover -s tests -v     (también funciona con pytest)
"""

import math
import random
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from benchmark_runner.metrics import percentiles as P  # noqa: E402


def linear(xs, p):
    """Fórmula escrita a mano (numpy 'linear'): h = (n−1)·p, interpolar entre x[⌊h⌋] y x[⌊h⌋+1]."""
    xs = sorted(xs)
    h = (len(xs) - 1) * p
    lo = math.floor(h)
    hi = min(lo + 1, len(xs) - 1)
    return xs[lo] + (h - lo) * (xs[hi] - xs[lo])


class ValoresConocidosTest(unittest.TestCase):

    def test_uno_a_diez(self):
        r = P.compute([float(x) for x in range(1, 11)])
        self.assertAlmostEqual(r.p50, 5.5)
        self.assertAlmostEqual(r.p95, 9.55)     # h = 9·0.95 = 8.55 → 9 + 0.55·(10 − 9)
        self.assertAlmostEqual(r.p99, 9.91)     # h = 8.91 → 9 + 0.91
        self.assertEqual(r.n, 10)

    def test_orden_de_entrada_no_importa(self):
        xs = [float(x) for x in range(1, 101)]
        shuffled = xs[:]
        random.Random(1).shuffle(shuffled)
        self.assertEqual(P.compute(xs), P.compute(shuffled))

    def test_coincide_con_la_formula_lineal(self):
        rng = random.Random(42)
        for n in (2, 3, 7, 20, 101, 5000):
            xs = [rng.lognormvariate(3, 1) for _ in range(n)]
            r = P.compute(xs)
            for got, p in ((r.p50, 0.50), (r.p95, 0.95), (r.p99, 0.99)):
                self.assertAlmostEqual(got, linear(xs, p), places=9, msg=f"n={n} p={p}")

    def test_metodo_declarado(self):
        self.assertIn("inclusive", P.METHOD)


class PocasMuestrasTest(unittest.TestCase):
    """A4: en PROFILE_C con concurrencia 50 puede no completarse casi nada."""

    def test_cero_muestras_no_lanza(self):
        r = P.compute([])
        self.assertFalse(r.available)
        self.assertIsNone(r.p99)
        self.assertIn("0 muestra", r.reason)

    def test_una_muestra_no_lanza(self):
        r = P.compute([123.4])
        self.assertFalse(r.available)
        self.assertIn("1 muestra", r.reason)

    def test_dos_muestras_si_calcula(self):
        r = P.compute([10.0, 20.0])
        self.assertTrue(r.available)
        self.assertAlmostEqual(r.p50, 15.0)
        self.assertTrue(r.low_density)

    def test_baja_densidad_por_debajo_de_20(self):
        self.assertTrue(P.compute([float(x) for x in range(19)]).low_density)
        self.assertFalse(P.compute([float(x) for x in range(20)]).low_density)


if __name__ == "__main__":
    unittest.main()
