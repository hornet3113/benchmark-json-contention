"""Pruebas de benchmark_runner/telemetry.py contra un Prometheus falso (F6.4).

Lo que se protege:
  - F6-A4: la comprobación previa exige up==1 de los 3 jobs Y colectores sin fallos;
    si falla, registra memoria, intenta recuperar UNA vez y vuelve a comprobar con el
    valor actual; nunca lanza.
  - F6-A1: un fallo no detiene nada; queda en el resumen.
  - F6-e: los huecos se ven (muestras crudas), también en los bordes; sin series del
    motor la exportación es "fallida"; las consultas del motor van filtradas por id.
"""

from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from benchmark_runner import telemetry

CID = "c0ffee"
UP_OK = [{"metric": {"job": j}, "value": [0, "1"]} for j in telemetry.JOBS]


class FakeProm:
    """Responde según la consulta. `series` mapea un prefijo del selector → lista de marcas de tiempo."""

    def __init__(self, up=None, failing=(), failing_now=(), series=None, down=False):
        self.up = UP_OK if up is None else up
        self.failing, self.failing_now = list(failing), list(failing_now)
        self.series = series or {}
        self.down = down
        self.queries: list[str] = []

    def __call__(self, path: str, params: dict) -> dict:
        if self.down:
            raise ConnectionRefusedError("conexión rechazada")
        q = params["query"]
        self.queries.append(q)
        if q == "up":
            return {"result": self.up}
        if "node_scrape_collector_success" in q:
            names = self.failing if q.startswith("min_over_time") else self.failing_now
            return {"result": [{"metric": {"collector": c}, "value": [0, "0"]} for c in names]}
        for prefix, ts in self.series.items():
            if q.startswith(prefix):
                return {"result": [{"metric": {"id": f"/docker/{CID}"}, "values": [[t, "1"] for t in ts]}]}
        return {"result": []}


def full(t0: float, t1: float) -> list[float]:
    return [t0 - 5 + i for i in range(int(t1 - t0) + 11)]


class CheckTest(unittest.TestCase):
    def test_all_up_and_no_failing_collectors_is_ok(self):
        self.assertTrue(telemetry.check(FakeProm())["ok"])

    def test_a_job_down_fails_with_reason(self):
        up = [{"metric": {"job": "prometheus"}, "value": [0, "1"]}, {"metric": {"job": "cadvisor"}, "value": [0, "1"]},
              {"metric": {"job": "node"}, "value": [0, "0"]}]
        r = telemetry.check(FakeProm(up=up))
        self.assertFalse(r["ok"])
        self.assertIn("node", r["motivo"])

    def test_missing_job_fails(self):
        r = telemetry.check(FakeProm(up=UP_OK[:2]))
        self.assertFalse(r["ok"])

    def test_failing_collector_fails_even_if_up(self):
        # F6.3: "filesystem" falló en todos los scrapes con up=1.
        r = telemetry.check(FakeProm(failing=["filesystem"]))
        self.assertFalse(r["ok"])
        self.assertEqual(r["colectores_con_fallos"], ["filesystem"])

    def test_unreachable_prometheus_is_a_failure_not_an_exception(self):
        r = telemetry.check(FakeProm(down=True))
        self.assertFalse(r["ok"])
        self.assertIn("no responde", r["motivo"])

    def test_second_check_looks_only_at_current_value(self):
        fake = FakeProm(failing=["filesystem"], failing_now=[])
        self.assertTrue(telemetry.check(fake, recent_window_s=None)["ok"])
        self.assertIn("node_scrape_collector_success == 0", fake.queries)


class PreflightTest(unittest.TestCase):
    def setUp(self):
        self.recoveries = 0
        self.memory_reads = 0

    def recover(self):
        self.recoveries += 1
        return {"exit": 0}

    def memory(self):
        self.memory_reads += 1
        return {"MemAvailable_kib": 1}

    def test_ok_does_not_recover_nor_read_memory(self):
        r = telemetry.preflight(FakeProm(), self.recover, self.memory)
        self.assertTrue(r["ok"])
        self.assertEqual((self.recoveries, self.memory_reads), (0, 0))

    def test_failure_records_memory_recovers_once_and_rechecks(self):
        fake = FakeProm(failing=["filesystem"], failing_now=[])     # tras reiniciar, ya no falla
        r = telemetry.preflight(fake, self.recover, self.memory)
        self.assertEqual(self.recoveries, 1)
        self.assertEqual(self.memory_reads, 2)                     # al fallar y tras recuperar
        self.assertTrue(r["ok"] and r["recuperada"])
        self.assertFalse(r["primera"]["ok"])

    def test_unrecovered_failure_is_reported_not_raised(self):
        r = telemetry.preflight(FakeProm(down=True), self.recover, self.memory)
        self.assertFalse(r["ok"])
        self.assertFalse(r["recuperada"])
        self.assertEqual(self.recoveries, 1)                       # una sola vez


class GapsTest(unittest.TestCase):
    def test_complete_series_has_no_gaps(self):
        self.assertEqual(telemetry.gaps([float(t) for t in range(0, 101)], 0, 100), [])

    def test_inner_gap(self):
        ts = [float(t) for t in range(0, 101) if not 40 < t < 44]
        self.assertEqual(telemetry.gaps(ts, 0, 100), [[40.0, 44.0]])

    def test_edge_gaps(self):
        ts = [float(t) for t in range(10, 91)]
        self.assertEqual(telemetry.gaps(ts, 0, 100), [[0.0, 10.0], [90.0, 100.0]])

    def test_no_samples_is_one_gap_over_the_window(self):
        self.assertEqual(telemetry.gaps([], 0, 100), [[0, 100]])


class ExportTest(unittest.TestCase):
    W0, W1 = 1000.0, 1300.0

    def export(self, fake):
        return telemetry.export(fake, CID, self.W0, self.W1, now=lambda: 10**10, sleep=lambda s: None)

    def test_complete(self):
        ts = full(self.W0, self.W1)
        fake = FakeProm(series={"container_": ts, "node_": ts, "up[": ts})
        e = self.export(fake)
        self.assertEqual(e["estado"], "completa")
        self.assertEqual(e["huecos_en_ventana"], {})
        container_q = [q for q in fake.queries if q.startswith("container_")]
        self.assertTrue(container_q and all(f'id="/docker/{CID}"' in q for q in container_q))

    def test_gap_is_marked_not_hidden(self):
        ts = full(self.W0, self.W1)
        holed = [t for t in ts if not 1100 < t < 1110]
        e = self.export(FakeProm(series={"container_memory_rss": holed, "container_": ts, "node_": ts, "up[": ts}))
        self.assertEqual(e["estado"], "con_huecos")
        self.assertEqual(e["huecos_en_ventana"]["container_memory_rss"], [[1100.0, 1110.0]])
        self.assertAlmostEqual(e["segundos_sin_muestra_max"], 10.0)

    def test_no_engine_series_is_failed(self):
        ts = full(self.W0, self.W1)
        e = self.export(FakeProm(series={"node_": ts, "up[": ts}))
        self.assertEqual(e["estado"], "fallida")
        self.assertIn("container_memory_rss", e["motivo"])

    def test_unreachable_is_failed_not_raised(self):
        self.assertEqual(self.export(FakeProm(down=True))["estado"], "fallida")

    def test_waits_for_last_scrape(self):
        waited = []
        telemetry.export(FakeProm(), CID, self.W0, self.W1, now=lambda: self.W1, sleep=waited.append)
        self.assertEqual(waited, [telemetry.EXPORT_MARGIN_S + telemetry.SCRAPE_SETTLE_S])


class SummaryTest(unittest.TestCase):
    OK_PRE = {"ok": True, "primera": {"ok": True}}

    def test_ok(self):
        s = telemetry.summary(self.OK_PRE, {"estado": "completa"})
        self.assertEqual((s["fallo"], s["motivos"]), (False, []))

    def test_gaps_are_not_a_failure_but_are_reported(self):
        s = telemetry.summary(self.OK_PRE, {"estado": "con_huecos", "huecos_en_ventana": {"x": [[1, 5]]},
                                            "segundos_sin_muestra_max": 4.0})
        self.assertFalse(s["fallo"])
        self.assertEqual(len(s["motivos"]), 1)

    def test_recovered_preflight_is_reported_not_a_failure(self):
        pre = {"ok": True, "recuperada": True, "primera": {"ok": False, "motivo": "up{job=node}=0.0"}}
        s = telemetry.summary(pre, {"estado": "completa"})
        self.assertFalse(s["fallo"])
        self.assertIn("recuperada", s["motivos"][0])

    def test_failed_export_or_preflight_is_a_failure(self):
        self.assertTrue(telemetry.summary(self.OK_PRE, {"estado": "fallida", "motivo": "x"})["fallo"])
        pre = {"ok": False, "recuperada": False, "primera": {"ok": False, "motivo": "no responde"}}
        self.assertTrue(telemetry.summary(pre, {"estado": "completa"})["fallo"])


class VmMemoryTest(unittest.TestCase):
    def test_reads_memory_swap_and_pressure(self):
        d = Path(tempfile.mkdtemp())
        try:
            (d / "pressure").mkdir()
            (d / "meminfo").write_text("MemTotal: 100 kB\nMemAvailable: 40 kB\nSwapTotal: 10 kB\nSwapFree: 7 kB\n"
                                       "Committed_AS: 90 kB\n")
            (d / "vmstat").write_text("pswpin 3\npswpout 4\noom_kill 1\nnr_free_pages 9\n")
            (d / "pressure" / "memory").write_text("some avg10=0.00\nfull avg10=0.00\n")
            m = telemetry.vm_memory(d)
            self.assertEqual((m["MemAvailable_kib"], m["SwapFree_kib"], m["pswpout"], m["oom_kill"]), (40, 7, 4, 1))
            self.assertEqual(len(m["pressure_memory"]), 2)
        finally:
            shutil.rmtree(d)

    def test_missing_files_are_recorded_not_raised(self):
        m = telemetry.vm_memory(Path("/no/existe"))
        self.assertIn("meminfo_error", m)


if __name__ == "__main__":
    unittest.main()
