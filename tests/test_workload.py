"""Runner (F5.4) sin contenedores: bucle cerrado con el motor falso y reglas de la fila.

Correr:  .venv/bin/python -m unittest discover -s tests -v
(no necesita drivers: el motor falso no importa pymongo ni psycopg)
"""

import sys
import time
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from benchmark_runner import csv_writer as S  # noqa: E402
from benchmark_runner import matrix as M  # noqa: E402
from benchmark_runner.config import Windows  # noqa: E402
from benchmark_runner.metrics.window import ClockSnapshot, Sample  # noqa: E402
from benchmark_runner.runner import assemble_row  # noqa: E402
from benchmark_runner.workload import LoadAborted, plan_workers, run_load  # noqa: E402

NS = 1_000_000_000
CELL = next(c for c in M.cells(54) if c.engine == "postgresql" and c.query_id == "Q2_MEM_LOW"
            and c.profile == "PROFILE_C_SEVERE" and c.concurrency == 1)
W = Windows(warmup_s=1, measure_s=2, cooldown_s=1)


def hooks():
    calls = {}
    return calls, (lambda: calls.setdefault("start", time.monotonic_ns())), (lambda: calls.setdefault("end", time.monotonic_ns()))


class RunLoadTest(unittest.TestCase):

    def test_consultas_rapidas(self):
        calls, on_start, on_end = hooks()
        r = run_load(CELL, W, ("fake", {"delay_s": 0.05}), concurrency=3, timeout_s=300,
                     on_window_start=on_start, on_window_end=on_end, grace_s=2)
        self.assertEqual(r.kinds["error"] + r.kinds["timeout"], 0)
        self.assertEqual(r.workers_terminated, 0)
        self.assertEqual(sorted(r.per_worker), [0, 1, 2])
        # Cada muestra lleva su worker (F5.5b) y nadie quedó cortado.
        self.assertEqual({s.wid for s in r.samples}, {0, 1, 2})
        self.assertEqual(r.unfinished_workers, [])
        # Los ganchos se ejecutan en el borde exacto de la ventana (±150 ms).
        self.assertLess(abs(calls["start"] - r.window_start_ns), 0.15 * NS)
        self.assertLess(abs(calls["end"] - r.window_end_ns), 0.15 * NS)
        self.assertEqual(r.window_end_ns - r.window_start_ns, 2 * NS)
        in_window = [s for s in r.samples if r.window_start_ns <= s.end_ns <= r.window_end_ns]
        # 3 workers × 2 s / 0.05 s ≈ 120; holgado por el planificador.
        self.assertGreater(len(in_window), 80)
        self.assertLess(len(in_window), 130)

    def test_consultas_mas_largas_que_la_repeticion(self):
        """PROFILE_C con concurrencia 50: ninguna consulta termina. El runner no se cuelga."""
        calls, on_start, on_end = hooks()
        t = time.monotonic()
        r = run_load(CELL, W, ("fake", {"delay_s": 30}), concurrency=2, timeout_s=300,
                     on_window_start=on_start, on_window_end=on_end, grace_s=0.5)
        self.assertLess(time.monotonic() - t, 15)
        self.assertEqual(r.workers_terminated, 2)
        self.assertEqual(r.samples, [])

    def test_fallos_intercalados(self):
        _, on_start, on_end = hooks()
        r = run_load(CELL, W, ("fake", {"delay_s": 0.02, "fail_every": 3, "timeout_every": 5}), concurrency=2,
                     timeout_s=300, on_window_start=on_start, on_window_end=on_end, grace_s=2)
        self.assertGreater(r.kinds["error"], 0)
        self.assertGreater(r.kinds["timeout"], 0)
        self.assertTrue(r.error_examples)

    def test_procesos_por_hilos(self):
        """6 workers en 2 procesos × 3 hilos: el motor vería 6 clientes, igual que con 6 procesos."""
        _, on_start, on_end = hooks()
        r = run_load(CELL, W, ("fake", {"delay_s": 0.05}), concurrency=6, timeout_s=300,
                     on_window_start=on_start, on_window_end=on_end, grace_s=2, processes=2)
        self.assertEqual((r.processes, r.threads_per_process), (2, 3))
        self.assertEqual(sorted(r.per_worker), list(range(6)))
        self.assertEqual(r.workers_terminated, 0)
        in_window = [s for s in r.samples if r.window_start_ns <= s.end_ns <= r.window_end_ns]
        self.assertGreater(len(in_window), 170)      # 6 × 2 s / 0.05 s ≈ 240

    def test_hilos_cortados_se_cuentan_por_hilo(self):
        _, on_start, on_end = hooks()
        r = run_load(CELL, W, ("fake", {"delay_s": 30}), concurrency=4, timeout_s=300,
                     on_window_start=on_start, on_window_end=on_end, grace_s=0.5, processes=2)
        self.assertEqual(r.workers_terminated, 4)
        self.assertEqual(r.unfinished_workers, [0, 1, 2, 3])

    def test_worker_que_no_conecta_aborta(self):
        _, on_start, on_end = hooks()
        with self.assertRaises(LoadAborted):
            run_load(CELL, W, ("fake", {"fail_connect": True}), concurrency=2, timeout_s=300,
                     on_window_start=on_start, on_window_end=on_end)


def fake_load(latencies_ms, *, kinds=None, timeouts=0, parallel=False, ws=100 * NS, we=400 * NS):
    """Consultas en serie (un worker) o en paralelo (todas arrancan juntas, como con c=50)."""
    samples, t = [], ws + NS
    for lat in latencies_ms:
        start = ws - 10 * NS if parallel else t
        samples.append(Sample(start, start + int(lat * 1e6), True))
        t += int(lat * 1e6)
    for _ in range(timeouts):                     # timeouts que terminan dentro de la ventana
        samples.append(Sample(ws - 200 * NS, ws + 100 * NS, False, "timeout"))
    return SimpleNamespace(samples=samples, window_start_ns=ws, window_end_ns=we,
                           kinds=kinds or {"ok": len(samples), "timeout": 0, "error": 0})


def edge(wall_s, mono_s, throttled_usec=0, oom_kill=0, cgroup=True):
    return {"clock": ClockSnapshot(int(wall_s * NS), int(mono_s * NS), int(mono_s * NS)),
            "cgroup": {"throttled_usec": throttled_usec, "oom_kill": oom_kill} if cgroup else {}}


class AssembleRowTest(unittest.TestCase):

    RUN = M.Run(CELL, 1)
    LAT = [float(x) for x in range(100, 160)]

    def build(self, load=None, start=None, end=None, rss=512.0, spill=False, oom_flag=False, running=True):
        row, reasons, self.cens = assemble_row(self.RUN, load=load or fake_load(self.LAT),
                                    start=start or edge(1000, 100, 0), end=end or edge(1300, 400, 5_500_000),
                                    max_rss_mib=rss, spill_observed=spill, oom_killed_flag=oom_flag,
                                    container_running=running)
        S.check_row(row)          # toda fila que produce el runner cumple el esquema
        return row, reasons

    def test_normal(self):
        row, _ = self.build()
        self.assertEqual(row["status"], "ok")
        self.assertAlmostEqual(row["throughput_qps"], 60 / 300)
        self.assertAlmostEqual(row["cpu_throttled_seconds"], 5.5)
        self.assertEqual(row["timestamp_epoch"], 1000)        # inicio de la ventana, reloj de pared
        self.assertEqual((row["engine"], row["query_id"], row["run_number"]), ("postgresql", "Q2_MEM_LOW", 1))

    def test_spill(self):
        row, _ = self.build(spill=True)
        self.assertEqual((row["status"], row["disk_spill"]), ("spill", True))

    def test_menos_de_dos_muestras(self):
        row, reasons = self.build(load=fake_load([500.0]))
        self.assertEqual(row["status"], "error")
        self.assertIsNone(row["latency_p99_ms"])
        self.assertTrue(any("1 muestra" in r for r in reasons))

    def test_suspension(self):
        row, reasons = self.build(end=edge(4300, 400, 5_500_000))     # 3 000 s de pared en 300 s monotónicos
        self.assertEqual(row["status"], "error")
        self.assertTrue(any("suspensión" in r for r in reasons))

    def test_oom_con_cgroup_desaparecido(self):
        row, reasons = self.build(end=edge(1300, 400, cgroup=False), rss=None, oom_flag=True, running=False)
        self.assertEqual(row["status"], "oom")
        self.assertIsNone(row["cpu_throttled_seconds"])     # vacío: no se midió. Nunca 0.
        self.assertIsNone(row["max_rss_mb"])

    def test_oom_por_contador(self):
        row, _ = self.build(end=edge(1300, 400, 5_500_000, oom_kill=1))
        self.assertEqual(row["status"], "oom")

    def test_error_de_consulta(self):
        row, _ = self.build(load=fake_load(self.LAT, kinds={"ok": 60, "timeout": 0, "error": 2}))
        self.assertEqual(row["status"], "error")

    def test_contenedor_caido(self):
        self.assertEqual(self.build(running=False)[0]["status"], "error")

    def test_sin_timeouts_percentiles_validos(self):
        self.build()
        self.assertEqual(self.cens["fraccion_timeouts"], 0.0)
        self.assertEqual(self.cens["percentil_valido"], {"p50": True, "p95": True, "p99": True})

    def test_censura_1_por_ciento_es_error(self):
        """Decisión de Alix: con ≥ 1 % de timeouts el P99 cae en la zona censurada → error."""
        lat = [100.0 + i for i in range(99)]
        row, reasons = self.build(load=fake_load(lat, timeouts=1))         # 1 de 100 = 1 %
        self.assertEqual(row["status"], "error")
        self.assertAlmostEqual(self.cens["fraccion_timeouts"], 0.01)
        self.assertEqual(self.cens["percentil_valido"], {"p50": True, "p95": True, "p99": False})
        self.assertTrue(any("censurados por la derecha" in r for r in reasons))
        self.assertIsNotNone(row["latency_p99_ms"])        # las latencias se escriben igual

    def test_censura_por_debajo_del_1_por_ciento_no_es_error(self):
        lat = [100.0 + i for i in range(200)]
        row, _ = self.build(load=fake_load(lat, timeouts=1))                # 1 de 201 < 1 %
        self.assertEqual(row["status"], "ok")
        self.assertTrue(self.cens["percentil_valido"]["p99"])

    def test_censura_de_la_corrida_3_del_humo(self):
        """El caso real de F5.5: 4 completadas y 46 timeouts → 92 %: ningún percentil vale."""
        row, _ = self.build(load=fake_load([231_000.0, 231_000.0, 233_000.0, 281_000.0], timeouts=46,
                                           parallel=True), spill=True)
        self.assertEqual((row["status"], row["disk_spill"]), ("error", True))
        self.assertAlmostEqual(self.cens["fraccion_timeouts"], 0.92)
        self.assertEqual(self.cens["percentil_valido"], {"p50": False, "p95": False, "p99": False})

    def test_p95_vale_entre_1_y_5_por_ciento(self):
        lat = [100.0 + i for i in range(97)]
        self.build(load=fake_load(lat, timeouts=3))                          # 3 %
        self.assertEqual(self.cens["percentil_valido"], {"p50": True, "p95": True, "p99": False})

    def test_baja_densidad_se_anota(self):
        _, reasons = self.build(load=fake_load([100.0, 120.0, 130.0]))
        self.assertTrue(any("baja densidad" in r for r in reasons))


class CliTest(unittest.TestCase):

    ARGS = ["run-cell", "--engine", "postgresql", "--profile", "PROFILE_C_SEVERE", "--query-id", "Q1",
            "--concurrency", "50"]

    def test_ventanas_solo_con_smoke(self):
        from benchmark_runner.cli import main
        self.assertEqual(main([*self.ARGS, "--ventanas", "10", "300", "10", "--confirmo-medicion-real"]), 2)

    def test_actividad_cada_solo_con_smoke(self):
        from benchmark_runner.cli import main
        self.assertEqual(main([*self.ARGS, "--actividad-cada", "10", "--confirmo-medicion-real"]), 2)
        self.assertEqual(main([*self.ARGS, "--actividad-cada", "0", "--smoke"]), 2)

    def test_real_exige_confirmacion(self):
        from benchmark_runner.cli import main
        self.assertEqual(main(self.ARGS), 2)

    def test_salida_no_se_admite_con_smoke(self):
        from benchmark_runner.cli import main
        self.assertEqual(main([*self.ARGS, "--smoke", "--salida", "f7"]), 2)

    def test_salida_rechaza_rutas(self):
        """F7-a: es un nombre de subcarpeta de results/, no una ruta."""
        from benchmark_runner.cli import main
        for bad in ("../x", "a/b", "/tmp", ".", "", "  "):
            self.assertEqual(main([*self.ARGS, "--confirmo-medicion-real", "--salida", bad]), 2, bad)


class MongoActivityTest(unittest.TestCase):
    """El filtro de currentOp debe ir como campos del comando (defecto de F5.5)."""

    def test_filtro_en_el_comando_y_solo_aggregates(self):
        from benchmark_runner.runner import mongo_activity
        calls = []

        class Admin:
            def command(self, name, value=1, **kw):
                calls.append((name, value, kw))
                if name == "currentOp":
                    return {"inprog": [{"command": {"aggregate": "orders"}, "client": "a"},
                                       {"command": {"aggregate": "orders"}, "client": "b"},
                                       {"command": {"getMore": 7, "collection": "orders"}, "client": "d"},
                                       {"command": {"hello": 1}, "client": "c"}]}
                return {"connections": {"current": 153, "active": 102}}

        r = mongo_activity(Admin(), "bench")
        self.assertIn(("currentOp", 1, {"active": True, "ns": "bench.orders"}), calls)
        # Un cliente en getMore sigue con su consulta: cuenta como cliente, no como aggregate (F5.5b).
        self.assertEqual((r["consultas_activas"], r["getmore_activos"], r["clientes_con_consulta_activa"]), (2, 1, 3))
        self.assertEqual(r["conexiones_actuales"], 153)
        # La foto lleva su intervalo, y serverStatus queda fuera de él.
        self.assertEqual(calls[0][0], "serverStatus")
        self.assertLessEqual(r["t0_ns"], r["t1_ns"])


class PlanWorkersTest(unittest.TestCase):

    def test_reparto_por_defecto(self):
        self.assertEqual(plan_workers(1), (1, 1))
        self.assertEqual(plan_workers(10), (10, 1))
        self.assertEqual(plan_workers(50), (10, 5))

    def test_reparto_explicito(self):
        self.assertEqual(plan_workers(50, 50), (50, 1))
        with self.assertRaises(ValueError):
            plan_workers(50, 7)


class CpusetTest(unittest.TestCase):

    def test_parse(self):
        from benchmark_runner.cli import parse_cpuset
        self.assertEqual(parse_cpuset("8-11"), {8, 9, 10, 11})
        self.assertEqual(parse_cpuset("0,2,4-5"), {0, 2, 4, 5})


if __name__ == "__main__":
    unittest.main()
