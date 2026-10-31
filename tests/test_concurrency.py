"""Cruce de las fotos del motor con las marcas del runner (F5.5b, criterio v3).

Correr:  .venv/bin/python -m unittest discover -s tests -v
"""

import sys
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from benchmark_runner.metrics.concurrency import (PeriodicReader, cross, engine_clients,  # noqa: E402
                                                  in_flight, summarize)

MS = 1_000_000


class InFlightTest(unittest.TestCase):
    # worker 0: [0, 100] y [100, 300]; worker 1: [50, 250]; worker 2: [0, 80] y luego cortado.
    SAMPLES = [(0, 100 * MS, 0), (100 * MS, 300 * MS, 0), (50 * MS, 250 * MS, 1), (0, 80 * MS, 2)]

    def test_en_vuelo_durante_todo_el_intervalo(self):
        # [120, 130] ms: w0 (2.ª consulta), w1 y w2 (cortado, en vuelo desde 80 ms).
        self.assertEqual(in_flight(self.SAMPLES, [2], 120 * MS, 130 * MS), 3)
        # Sin saber que w2 quedó cortado, solo 2.
        self.assertEqual(in_flight(self.SAMPLES, [], 120 * MS, 130 * MS), 2)

    def test_una_consulta_que_termina_dentro_de_la_foto_no_es_segura(self):
        # [240, 260] ms: w1 termina a 250, no estuvo en vuelo toda la foto.
        self.assertEqual(in_flight(self.SAMPLES, [], 240 * MS, 260 * MS), 1)

    def test_cortado_sin_ninguna_muestra(self):
        self.assertEqual(in_flight([], [5], 10 * MS, 20 * MS), 1)

    def test_cortado_cuenta_solo_desde_su_ultima_muestra(self):
        self.assertEqual(in_flight(self.SAMPLES, [2], 10 * MS, 20 * MS), 2)   # w0 y w2 (1.ª consulta); w1 aún no


class CrossTest(unittest.TestCase):

    def test_faltan_y_terminan_despues(self):
        samples = [(0, 1000 * MS, w) for w in range(3)] + [(0, 205 * MS, 3)]
        photos = [{"momento": "serie", "t0_ns": 100 * MS, "t1_ns": 110 * MS, "clientes_con_consulta_activa": 3}]
        r = cross(photos, samples, [], "mongodb")[0]
        self.assertEqual((r["motor"], r["cliente_seguro"], r["faltan"]), (3, 4, 1))
        self.assertEqual(r["terminan_<=250ms_despues"], 1)       # la de w3 terminó a 205 ms
        self.assertEqual(r["duracion_ms"], 10.0)

    def test_postgres_usa_consultas_activas(self):
        self.assertEqual(engine_clients({"consultas_activas": 50, "clientes": 51}, "postgresql"), 50)
        self.assertIsNone(engine_clients({}, "mongodb"))

    def test_resumen(self):
        rows = [{"motor": 50, "faltan": 0}, {"motor": 47, "faltan": 3}, {"motor": 50, "faltan": 0},
                {"motor": None, "faltan": None}]
        s = summarize(rows)
        self.assertEqual((s["fotos"], s["fotos_validas"], s["mediana_motor"], s["min_motor"]), (4, 3, 50, 47))
        self.assertEqual((s["media_faltan"], s["max_faltan"]), (1.0, 3))


class PeriodicReaderTest(unittest.TestCase):

    def test_lee_cada_intervalo_y_registra_errores(self):
        n = {"i": 0}

        def read():
            n["i"] += 1
            if n["i"] == 2:
                raise RuntimeError("se cayó")
            return {"t0_ns": time.monotonic_ns(), "t1_ns": time.monotonic_ns()}

        r = PeriodicReader(read, 0.05)
        r.start()
        time.sleep(0.33)
        r.stop()
        self.assertGreaterEqual(len(r.samples), 3)
        self.assertEqual(len(r.errors), 1)
        self.assertTrue(all(s["momento"] == "serie" for s in r.samples))

    def test_no_lee_antes_del_primer_intervalo(self):
        r = PeriodicReader(lambda: {"t0_ns": 0, "t1_ns": 0}, 10)
        r.start()
        r.stop()
        self.assertEqual(r.samples, [])


if __name__ == "__main__":
    unittest.main()
