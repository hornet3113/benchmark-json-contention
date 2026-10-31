"""Dominio de status y reglas entre columnas (R-27, SPEC §4).

Correr:  python3 -m unittest discover -s tests -v     (también funciona con pytest)
"""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from benchmark_runner import csv_writer as S  # noqa: E402
from test_csv_schema import good_row  # noqa: E402


class StatusTest(unittest.TestCase):

    def test_dominio_cerrado(self):
        self.assertEqual(S.STATUSES, ("ok", "spill", "oom", "error"))
        for bad in ("OK", "timeout", "", "fail"):
            with self.assertRaises(S.SchemaError):
                S.check_row(good_row(status=bad))

    def test_precedencia_oom_error_spill_ok(self):
        self.assertEqual(S.resolve_status(oom=True, error=True, spill=True), "oom")
        self.assertEqual(S.resolve_status(oom=False, error=True, spill=True), "error")
        self.assertEqual(S.resolve_status(oom=False, error=False, spill=True), "spill")
        self.assertEqual(S.resolve_status(oom=False, error=False, spill=False), "ok")

    def test_ok_con_spill_esta_prohibido(self):
        with self.assertRaises(S.SchemaError):
            S.check_row(good_row(status="ok", disk_spill=True))

    def test_spill_con_disk_spill_es_valido(self):
        S.check_row(good_row(status="spill", disk_spill=True))

    def test_error_con_disk_spill_es_valido(self):
        # Hubo volcado y además un error: manda error (precedencia), disk_spill dice lo observado.
        S.check_row(good_row(status="error", disk_spill=True))


class LatenciasVaciasTest(unittest.TestCase):
    """A4 y ajuste 2: sin muestras suficientes, latencias vacías y status=error. Nunca rellenadas."""

    EMPTY = {"latency_p50_ms": None, "latency_p95_ms": None, "latency_p99_ms": None}

    def test_vacias_con_error_valido(self):
        S.check_row(good_row(status="error", throughput_qps=0.0, **self.EMPTY))

    def test_vacias_con_ok_rechazado(self):
        with self.assertRaises(S.SchemaError):
            S.check_row(good_row(status="ok", **self.EMPTY))

    def test_parcialmente_vacias_rechazado(self):
        with self.assertRaises(S.SchemaError):
            S.check_row(good_row(status="error", latency_p99_ms=None))

    def test_throughput_nunca_vacio(self):
        with self.assertRaises(S.SchemaError):
            S.check_row(good_row(status="error", throughput_qps=None))

    def test_throttling_y_memoria_vacios_solo_con_error_u_oom(self):
        # El contenedor murió por OOM: su cgroup desapareció, no hay lectura final.
        S.check_row(good_row(status="oom", cpu_throttled_seconds=None, max_rss_mb=None, **self.EMPTY))
        S.check_row(good_row(status="error", cpu_throttled_seconds=None))
        for status in ("ok", "spill"):
            with self.assertRaises(S.SchemaError):
                S.check_row(good_row(status=status, disk_spill=status == "spill", cpu_throttled_seconds=None))

    def test_latencias_vacias_con_oom(self):
        S.check_row(good_row(status="oom", **self.EMPTY))

    def test_percentiles_desordenados_rechazados(self):
        with self.assertRaises(S.SchemaError):
            S.check_row(good_row(latency_p50_ms=100.0, latency_p95_ms=90.0))


class OtrosDominiosTest(unittest.TestCase):

    def test_perfiles_literales_del_manual(self):
        self.assertEqual(S.PROFILES, ("PROFILE_A_BASELINE", "PROFILE_B_MEDIUM", "PROFILE_C_SEVERE"))
        with self.assertRaises(S.SchemaError):
            S.check_row(good_row(profile="A"))

    def test_query_id_segun_a2(self):
        S.check_row(good_row(query_id="Q2_MEM_HIGH"), matrix=54)
        with self.assertRaises(S.SchemaError):
            S.check_row(good_row(query_id="Q2"), matrix=54)
        S.check_row(good_row(query_id="Q2"), matrix=36)

    def test_tipos(self):
        for over in ({"concurrency": 5}, {"run_number": 4}, {"engine": "mysql"},
                     {"disk_spill": "false"}, {"timestamp_epoch": 1.5}, {"throughput_qps": -1.0},
                     {"max_rss_mb": True}):
            with self.assertRaises(S.SchemaError, msg=over):
                S.check_row(good_row(**over))


if __name__ == "__main__":
    unittest.main()
