"""Pruebas de los criterios de la celda piloto (scripts/checks/check_pilot_f7.py, F7.1).

Lo que se protege:
  - el CV y la tendencia son criterios independientes: el caso de Alix (100-110-120,
    CV 9 % y deriva del 20 %) tiene que salir como tendencia;
  - la monotonía sola no basta (F7-b): con 3 valores sale por azar 1 de cada 3 veces;
  - la primera consulta en frío se toma por worker, y un worker que nunca terminó
    ninguna consulta no se cuenta como "cabe en el calentamiento".
"""

from __future__ import annotations

import shutil
import sys
import tempfile
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

    def test_worker_cut_at_the_end_still_fits(self):
        """El corte al final de la ventana no dice nada de la primera consulta (piloto r1 de Mongo)."""
        r = pilot.cold_first_queries(raw([(0, 33, 0), (33, 60, 0)], unfinished=[0]))
        self.assertEqual(r["workers_sin_ninguna_consulta_terminada"], [])
        self.assertTrue(r["cabe_en_el_calentamiento"])


if __name__ == "__main__":
    unittest.main()


class PlanCriterionTest(unittest.TestCase):
    """R-31 tal como lo diseñó F5: UN plan por celda, en la repetición 1 de c=1."""

    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.plan = self.dir / "plan.json"
        self.plan.write_text("{}")

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def runs(self, plans, errors=(None, None, None)):
        return [{"run_number": i + 1, "plan": p, "plan_error": e}
                for i, (p, e) in enumerate(zip(plans, errors))]

    def check(self, runs):
        return (any(r["plan"] and Path(r["plan"]).exists() for r in runs)
                and not any(r["plan_error"] for r in runs))

    def test_only_the_first_run_captures_it(self):
        self.assertTrue(self.check(self.runs([str(self.plan), None, None])))

    def test_no_plan_at_all_fails(self):
        self.assertFalse(self.check(self.runs([None, None, None])))

    def test_a_plan_error_fails_even_with_a_file(self):
        self.assertFalse(self.check(self.runs([str(self.plan), None, None], (None, "TimeoutError: x", None))))

    def test_a_path_that_does_not_exist_fails(self):
        self.assertFalse(self.check(self.runs([str(self.dir / "no_existe.json"), None, None])))


class ColdSweepUnitsTest(unittest.TestCase):
    """F7.3: las duraciones van en SEGUNDOS, porque se comparan con los 60 s del manual."""

    def test_first_query_durations_are_seconds(self):
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "checks"))
        import check_cold_f73 as cold
        r = cold.analyse({
            "run_id": "x", "ventana_ns": {"inicio": 60 * S, "fin": 90 * S},
            "ventanas_s": {"warmup_s": 60, "measure_s": 30, "cooldown_s": 5},
            # worker 0: 35 s en frío (cabe en 60) y luego 2 s · worker 1: 70 s (no cabe)
            "muestras": [[0, 35 * S, 1, 0], [35 * S, 37 * S, 1, 0], [0, 70 * S, 1, 1]],
            "consultas": {"workers_sin_terminar": []},
            "fila_csv": {"engine": "mongodb", "profile": "PROFILE_A_BASELINE", "query_id": "Q1",
                         "concurrency": 50, "status": "ok", "latency_p50_ms": 1.0,
                         "latency_p95_ms": 2.0, "latency_p99_ms": 3.0}})
        self.assertEqual(r["primera_consulta_s"]["max"], 70.0)
        self.assertEqual(r["primeras_que_pasan_del_calentamiento"], 1)      # solo la de 70 s
        self.assertFalse(r["cabe_en_el_calentamiento"])
        self.assertEqual(r["primeras_que_terminan_en_la_ventana"], 1)       # la de 70 s acaba en la ventana


class DatasetAfterOomTest(unittest.TestCase):
    """R-08 + petición de Alix (2026-11-02): tras un OOM se recuenta antes de seguir."""

    def test_count_is_compared_with_500000(self):
        from benchmark_runner.runner import DATASET_ROWS, count_dataset
        self.assertEqual(DATASET_ROWS, 500_000)
        # Sin motor levantado, la conexión falla: no se puede contar → NO intacto, y sin lanzar.
        out = count_dataset("postgresql", {"POSTGRES_DB": "bench", "POSTGRES_USER": "bench",
                                           "POSTGRES_PASSWORD": "x"})
        self.assertIn("error", out)
        self.assertIsNone(out["filas"])
        self.assertFalse(out["intacto"])

    def test_only_an_exact_count_is_intact(self):
        from benchmark_runner.runner import DATASET_ROWS
        for filas, intacto in ((DATASET_ROWS, True), (DATASET_ROWS - 1, False), (0, False), (None, False)):
            self.assertEqual(filas == DATASET_ROWS, intacto)


class V7HelperTest(unittest.TestCase):
    """V7 (opción 3): con la regla instalada no hacen falta credenciales en caché."""

    def test_missing_helper_means_not_installed(self):
        from benchmark_runner import lifecycle
        original = lifecycle.V7_HELPER
        try:
            lifecycle.V7_HELPER = "/no/existe/bench-drop-caches"
            self.assertFalse(lifecycle.v7_helper_allowed())
        finally:
            lifecycle.V7_HELPER = original

    def test_keepalive_does_not_run_when_the_rule_is_installed(self):
        from benchmark_runner import lifecycle
        original = lifecycle.v7_helper_allowed
        try:
            lifecycle.v7_helper_allowed = lambda: True
            k = lifecycle.SudoKeepAlive(every_s=0.01)
            self.assertTrue(k.innecesario)
            k.start()
            k.join(timeout=1)
            # Con la regla, `sudo -n -v` falla siempre: el hilo no debe acumular fallos.
            self.assertEqual(k.failures, 0)
        finally:
            lifecycle.v7_helper_allowed = original
