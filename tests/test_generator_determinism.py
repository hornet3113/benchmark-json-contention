"""Pruebas de F2.2: escritura JSONL, determinismo, prefijo, estadísticas y CLI.

Correr:  python3 -m unittest discover -s tests -v     (también funciona con pytest)
"""

import copy
import hashlib
import json
import random
import re
import sys
import tempfile
import unittest
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from generator import synthetic_data_generator as G  # noqa: E402


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class GenerateTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        d = Path(cls.tmp.name)
        cls.a = d / "a_300.jsonl"
        cls.b = d / "b_300.jsonl"
        cls.small = d / "c_100.jsonl"
        cls.stats_a = G.generate(300, cls.a)
        cls.stats_b = G.generate(300, cls.b)
        cls.stats_small = G.generate(100, cls.small)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_misma_semilla_mismo_hash(self):
        self.assertEqual(self.stats_a["sha256"], self.stats_b["sha256"])
        self.assertEqual(self.a.read_bytes(), self.b.read_bytes())

    def test_hash_declarado_es_el_del_archivo(self):
        self.assertEqual(self.stats_a["sha256"], sha256(self.a.read_bytes()))
        self.assertEqual(self.stats_a["bytes"], self.a.stat().st_size)

    def test_el_archivo_chico_es_el_inicio_del_grande(self):
        small = self.small.read_bytes()
        big_prefix = b"".join(self.a.read_bytes().splitlines(keepends=True)[:100])
        self.assertEqual(small, big_prefix)
        self.assertEqual(self.stats_small["sha256"], sha256(big_prefix))

    def test_una_linea_json_por_registro(self):
        lines = self.a.read_bytes().split(b"\n")
        self.assertEqual(lines[-1], b"")          # termina en salto de línea
        self.assertEqual(len(lines) - 1, 300)
        for line in lines[:-1]:
            json.loads(line)

    def test_no_queda_archivo_temporal(self):
        self.assertEqual(sorted(p.name for p in self.a.parent.iterdir()),
                         ["a_300.jsonl", "b_300.jsonl", "c_100.jsonl"])

    def test_estadisticas_basicas(self):
        s = self.stats_a
        self.assertTrue(s["contrato_ok"])
        self.assertEqual(s["registros"], 300)
        self.assertEqual(s["registros_invalidos"], 0)
        self.assertEqual(s["order_id_repetidos"], 0)
        self.assertEqual(s["anidamiento_niveles"], {3: 300})
        self.assertEqual(s["semilla"], 42)
        self.assertIn("synthetic_data_generator.py", s["generador"]["sha256_fuentes"])

    def test_otra_semilla_otro_hash(self):
        out = Path(self.tmp.name) / "seed43.jsonl"
        self.assertNotEqual(G.generate(100, out, seed=43)["sha256"], self.stats_small["sha256"])
        out.unlink()


class SerializeTest(unittest.TestCase):

    def test_formato_fijo(self):
        rec = G.make_record(random.Random(42))
        line = G.serialize(rec)
        self.assertTrue(line.endswith(b"\n"))
        line.decode("ascii")
        # Sin espacios tras "," o ":" FUERA de los textos (dentro sí puede
        # haberlos: el user_agent lleva "(KHTML, like Gecko)").
        structure = re.sub(rb'"(?:[^"\\]|\\.)*"', b'""', line)
        self.assertNotIn(b", ", structure)
        self.assertNotIn(b": ", structure)
        self.assertEqual(json.loads(line), rec)


class StatsTest(unittest.TestCase):
    """Los detectores se prueban con datos fabricados: si no ven un problema
    puesto a propósito, que no lo vean en el dataset real no significa nada."""

    BASE = G.make_record(random.Random(42))

    def rec(self, final_total, status="completed", ts="2026-05-01T00:00:00Z"):
        r = copy.deepcopy(self.BASE)
        r["order_id"] = str(uuid.uuid4())
        r["timestamp"] = ts
        r["payment"]["status"] = status
        r["payment"]["totals"] = {"subtotal": final_total, "tax": 0.0, "discount": 0.0}
        r["payment"]["final_total"] = final_total
        return r

    def stats(self, recs, top_k):
        s = G.Stats(top_k=top_k)
        for r in recs:
            s.add(r)
        return s

    def test_detecta_empate_en_la_frontera(self):
        s = self.stats([self.rec(10.0), self.rec(9.0), self.rec(9.0)], top_k=2)
        b = s.q2_boundary()
        self.assertTrue(b["aplica"])
        self.assertTrue(b["empate_en_la_frontera"])
        self.assertEqual((b["final_total_fila_k"], b["final_total_fila_k_mas_1"]), (9.0, 9.0))

    def test_sin_empate(self):
        b = self.stats([self.rec(10.0), self.rec(9.0), self.rec(8.0)], top_k=2).q2_boundary()
        self.assertFalse(b["empate_en_la_frontera"])

    def test_solo_cuenta_filas_que_pasan_el_filtro_de_q2(self):
        recs = [self.rec(10.0), self.rec(9.0),
                self.rec(9.5, status="pending"),               # no completed
                self.rec(9.5, ts="2025-12-31T23:59:59Z"),       # antes de 2026
                self.rec(8.0, ts="2026-01-01T00:00:00Z")]       # justo en el límite: sí entra
        s = self.stats(recs, top_k=2)
        self.assertEqual(s.q2_rows, 3)
        self.assertEqual(s.q2_boundary()["final_total_fila_k_mas_1"], 8.0)

    def test_no_aplica_si_hay_menos_filas_que_k(self):
        b = self.stats([self.rec(10.0)], top_k=5).q2_boundary()
        self.assertFalse(b["aplica"])

    def test_detecta_order_id_repetido(self):
        r = self.rec(10.0)
        s = self.stats([r, copy.deepcopy(r)], top_k=1)
        self.assertEqual(s.duplicate_order_ids, 1)
        self.assertFalse(s.ok)

    def test_registro_invalido_se_cuenta_sin_romper(self):
        bad = self.rec(10.0)
        del bad["payment"]
        s = self.stats([bad, self.rec(9.0)], top_k=1)
        self.assertEqual(s.invalid_records, 1)
        self.assertEqual(s.records, 2)
        self.assertFalse(s.ok)
        self.assertTrue(s.error_examples)


class CliTest(unittest.TestCase):

    def test_solo_acepta_los_tamanos_del_plan(self):
        with self.assertRaises(SystemExit) as cm:
            G.main(["--size", "123"])
        self.assertEqual(cm.exception.code, 2)

    def test_rutas_por_defecto(self):
        self.assertEqual(G.default_paths(500_000, 42),
                         (ROOT / "data" / "orders_500000_seed42.jsonl", ROOT / "results" / "dataset_stats.json"))
        self.assertEqual(G.default_paths(1000, 42)[1], ROOT / "results" / "f2" / "dataset_stats_1000_seed42.json")


if __name__ == "__main__":
    unittest.main()
