"""Pruebas de los criterios de la celda piloto (scripts/checks/check_pilot_f7.py, F7.1).

Lo que se protege:
  - el CV y la tendencia son criterios independientes: el caso de Alix (100-110-120,
    CV 9 % y deriva del 20 %) tiene que salir como tendencia;
  - la monotonía sola no basta (F7-b): con 3 valores sale por azar 1 de cada 3 veces;
  - la primera consulta en frío se toma por worker, y un worker que nunca terminó
    ninguna consulta no se cuenta como "cabe en el calentamiento".
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "checks"))

import check_pilot_f7 as pilot  # noqa: E402

S = 1_000_000_000      # 1 s en ns


def raw(samples, *, warmup_s=60, window_start_s=60, unfinished=()):
    """Crudo mínimo con lo que mira cold_first_queries. samples: (inicio_s, fin_s, wid)."""
    return {"ventana_ns": {"inicio": window_start_s * S, "fin": (window_start_s + 300) * S},
            "ventanas_s": {"warmup_s": warmup_s, "measure_s": 300, "cooldown_s": 60},
            "muestras": [[a * S, b * S, 1, w] for a, b, w in samples],
            "consultas": {"workers_sin_terminar": list(unfinished)}}


class CvTest(unittest.TestCase):
    def test_identical_values_have_no_variation(self):
        self.assertEqual(pilot.cv([2.0, 2.0, 2.0]), 0.0)

    def test_known_value(self):
        self.assertAlmostEqual(pilot.cv([100, 110, 120]), 0.0909, places=3)

    def test_needs_two_values(self):
        self.assertIsNone(pilot.cv([1.0]))

    def test_zero_mean_is_none_not_a_crash(self):
        self.assertIsNone(pilot.cv([0.0, 0.0]))


class TrendTest(unittest.TestCase):
    def test_alix_case_progressive_degradation(self):
        """100-110-120: CV 9 % (pasa) pero la tendencia tiene que verse."""
        t = pilot.trend([100, 110, 120])
        self.assertTrue(t["hay_tendencia"])
        self.assertEqual(t["monotona"], "creciente")
        self.assertAlmostEqual(t["cambio_rel"], 0.20, places=4)

    def test_mongo_probe_case(self):
        self.assertTrue(pilot.trend([31.0, 62.0, 161.0])["hay_tendencia"])

    def test_decreasing_counts_too(self):
        t = pilot.trend([120, 110, 100])
        self.assertTrue(t["hay_tendencia"])
        self.assertEqual(t["monotona"], "decreciente")

    def test_monotonic_but_tiny_is_not_a_trend(self):
        """F7-b: la monotonía sola sale por azar; hace falta tamaño."""
        t = pilot.trend([100, 100.5, 101])
        self.assertEqual(t["monotona"], "creciente")
        self.assertFalse(t["hay_tendencia"])

    def test_big_but_not_monotonic_is_not_a_trend(self):
        t = pilot.trend([100, 140, 120])
        self.assertIsNone(t["monotona"])
        self.assertFalse(t["hay_tendencia"])

    def test_needs_three_values(self):
        self.assertFalse(pilot.trend([100, 130])["hay_tendencia"])


class ColdFirstQueryTest(unittest.TestCase):
    def test_takes_the_first_query_of_each_worker(self):
        # worker 0: 40 s y luego 5 s · worker 1: 30 s y luego 6 s
        r = pilot.cold_first_queries(raw([(0, 40, 0), (40, 45, 0), (0, 30, 1), (30, 36, 1)]))
        self.assertEqual(r["primera_consulta_ms"], [30000.0, 40000.0])
        self.assertEqual(r["max_s"], 40.0)
        self.assertTrue(r["cabe_en_el_calentamiento"])

    def test_cold_query_longer_than_warmup_does_not_fit(self):
        r = pilot.cold_first_queries(raw([(0, 74, 0)]))      # los ~74 s vistos en el humo de F5.5
        self.assertFalse(r["cabe_en_el_calentamiento"])
        self.assertEqual(r["max_s"], 74.0)

    def test_first_query_inside_the_window_is_counted(self):
        # El worker 1 empieza su primera consulta ya dentro de la ventana (empieza en 60 s).
        r = pilot.cold_first_queries(raw([(0, 10, 0), (70, 80, 1)]))
        self.assertEqual(r["primera_consulta_dentro_de_la_ventana"], 1)

    def test_worker_without_any_finished_query_does_not_fit(self):
        r = pilot.cold_first_queries(raw([(0, 10, 0)], unfinished=[1]))
        self.assertEqual(r["workers_sin_ninguna_consulta_terminada"], [1])
        self.assertFalse(r["cabe_en_el_calentamiento"])


if __name__ == "__main__":
    unittest.main()
