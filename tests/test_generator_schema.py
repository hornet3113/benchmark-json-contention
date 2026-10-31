"""Pruebas de F2.1: contrato del registro, make_record() y validador.

Correr:  python3 -m unittest discover -s tests -v     (también funciona con pytest)
"""

import copy
import json
import random
import sys
import unittest
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from generator import distributions as D  # noqa: E402
from generator import schema  # noqa: E402
from generator.synthetic_data_generator import make_record  # noqa: E402


def records(n, seed=D.SEED):
    rng = random.Random(seed)
    return [make_record(rng) for _ in range(n)]


SAMPLE = records(2000)


class RegistroValidoTest(unittest.TestCase):

    def test_todos_los_registros_cumplen_el_contrato(self):
        for i, rec in enumerate(SAMPLE):
            self.assertEqual(schema.validate_record(rec), [], f"registro {i}")

    def test_profundidad_exactamente_3(self):
        self.assertEqual({schema.nesting_depth(r) for r in SAMPLE}, {3})

    def test_orden_de_claves(self):
        rec = SAMPLE[0]
        self.assertEqual(tuple(rec), schema.TOP_KEYS)
        self.assertEqual(tuple(rec["payment"]), schema.PAYMENT_KEYS)

    def test_sobrevive_ida_y_vuelta_por_json(self):
        for rec in SAMPLE[:200]:
            back = json.loads(json.dumps(rec))
            self.assertEqual(back, rec)
            self.assertEqual(schema.validate_record(back), [])


class OrderIdTest(unittest.TestCase):
    """order_id debe poder ser el id UUID de PostgreSQL sin cambiar de texto (SPEC §2)."""

    def test_forma_canonica_como_la_escribe_postgres(self):
        for rec in SAMPLE:
            oid = rec["order_id"]
            self.assertEqual(str(uuid.UUID(oid)), oid)
            self.assertEqual(oid, oid.lower())

    def test_unicos_en_la_muestra(self):
        ids = [r["order_id"] for r in SAMPLE]
        self.assertEqual(len(ids), len(set(ids)))


class TimestampTest(unittest.TestCase):

    def test_formato_estricto_y_en_rango(self):
        for rec in SAMPLE:
            ts = rec["timestamp"]
            self.assertRegex(ts, schema.TIMESTAMP_RE)
            dt = datetime.strptime(ts, D.TS_FORMAT).replace(tzinfo=timezone.utc)
            self.assertTrue(D.TS_START <= dt <= D.TS_END, ts)

    def test_orden_alfabetico_igual_al_cronologico(self):
        # Es lo que hace que el $gte de texto en Mongo y el ::timestamptz de
        # Postgres seleccionen las mismas filas en Q2 (trampa 1).
        ts = [r["timestamp"] for r in SAMPLE]
        as_dt = lambda s: datetime.strptime(s, D.TS_FORMAT)  # noqa: E731
        self.assertEqual(sorted(ts), sorted(ts, key=as_dt))


class ImportesTest(unittest.TestCase):

    def test_final_total_es_numero_y_cuadra(self):
        for rec in SAMPLE:
            p = rec["payment"]
            self.assertIsInstance(p["final_total"], float)
            t = p["totals"]
            self.assertEqual(round(p["final_total"] * 100),
                             round(t["subtotal"] * 100) + round(t["tax"] * 100) - round(t["discount"] * 100))

    def test_dos_decimales_como_maximo(self):
        for rec in SAMPLE[:300]:
            for v in [rec["payment"]["final_total"], *rec["payment"]["totals"].values(),
                      *(it["price"] for it in rec["items"])]:
                self.assertLessEqual(len(repr(v).partition(".")[2]), 2, v)


class DeterminismoTest(unittest.TestCase):

    def test_misma_semilla_mismos_registros(self):
        self.assertEqual(json.dumps(records(200)), json.dumps(SAMPLE[:200]))

    def test_otra_semilla_otros_registros(self):
        self.assertNotEqual(records(5, seed=43)[0]["order_id"], SAMPLE[0]["order_id"])


class ValidadorDetectaErroresTest(unittest.TestCase):
    """Si el validador no atrapa estos casos, que la muestra "pase" no prueba nada."""

    def broken(self, mutate):
        rec = copy.deepcopy(SAMPLE[0])
        mutate(rec)
        return schema.validate_record(rec)

    def assertRejects(self, mutate, fragment):
        errors = self.broken(mutate)
        self.assertTrue(any(fragment in e for e in errors), f"esperaba '{fragment}' en {errors}")

    def test_final_total_como_string(self):
        self.assertRejects(lambda r: r["payment"].update(final_total=str(r["payment"]["final_total"])),
                           "payment.final_total")

    def test_final_total_dentro_de_totals(self):
        def m(r):
            r["payment"]["totals"]["final_total"] = r["payment"].pop("final_total")
        self.assertRejects(m, "payment:")

    def test_final_total_que_no_cuadra(self):
        self.assertRejects(lambda r: r["payment"].update(final_total=r["payment"]["final_total"] + 0.01),
                           "!= subtotal + tax - discount")

    def test_timestamp_con_fraccion(self):
        self.assertRejects(lambda r: r.update(timestamp=r["timestamp"].replace("Z", ".5Z")), "timestamp")

    def test_timestamp_con_desfase_horario(self):
        self.assertRejects(lambda r: r.update(timestamp=r["timestamp"].replace("Z", "+00:00")), "timestamp")

    def test_order_id_en_mayusculas(self):
        self.assertRejects(lambda r: r.update(order_id=r["order_id"].upper()), "order_id")

    def test_discounts_como_objetos_suben_a_4_niveles(self):
        self.assertRejects(lambda r: r["items"][0].update(discounts=[{"pct": 5}]), "anidamiento: 4")

    def test_clave_faltante(self):
        self.assertRejects(lambda r: r["customer"]["geo"].pop("zip"), "faltan ['zip']")

    def test_clave_de_mas(self):
        self.assertRejects(lambda r: r["metadata"].update(extra=1), "sobran ['extra']")

    def test_barra_invertida_rompe_copy(self):
        self.assertRejects(lambda r: r["metadata"].update(user_agent="a\\b"), "COPY")

    def test_qty_booleano(self):
        self.assertRejects(lambda r: r["items"][0].update(qty=True), "qty")


class OrdenDeClavesTest(unittest.TestCase):
    """JSONB reordena las claves: lo leído de Postgres no conserva el orden (F3)."""

    @staticmethod
    def reordered(value):
        # Mismo orden que aplica JSONB: por longitud de clave y luego bytewise.
        if isinstance(value, dict):
            return {k: OrdenDeClavesTest.reordered(value[k]) for k in sorted(value, key=lambda k: (len(k), k))}
        if isinstance(value, list):
            return [OrdenDeClavesTest.reordered(v) for v in value]
        return value

    def test_estricto_rechaza_otro_orden(self):
        rec = self.reordered(SAMPLE[0])
        self.assertTrue(schema.validate_record(rec))

    def test_sin_orden_acepta_otro_orden(self):
        rec = self.reordered(SAMPLE[0])
        self.assertEqual(schema.validate_record(rec, strict_order=False), [])

    def test_sin_orden_sigue_exigiendo_las_mismas_claves(self):
        rec = self.reordered(SAMPLE[0])
        rec["payment"].pop("final_total")
        errors = schema.validate_record(rec, strict_order=False)
        self.assertTrue(any("faltan ['final_total']" in e for e in errors), errors)

    def test_sin_orden_sigue_revisando_tipos(self):
        rec = self.reordered(SAMPLE[0])
        rec["payment"]["final_total"] = "31.16"
        self.assertTrue(any("final_total" in e for e in schema.validate_record(rec, strict_order=False)))


class ProfundidadTest(unittest.TestCase):

    def test_definicion(self):
        self.assertEqual(schema.nesting_depth({"a": 1}), 0)
        self.assertEqual(schema.nesting_depth({"a": {"b": 1}}), 1)
        self.assertEqual(schema.nesting_depth({"a": [{"b": [1]}]}), 3)


class DistribucionesTest(unittest.TestCase):
    """Metas de SPEC A8 con ±1 punto. La aceptación formal es sobre 500 000 (F2.3);
    aquí se comprueba con 20 000 que los parámetros apuntan bien."""

    @classmethod
    def setUpClass(cls):
        cls.recs = records(20_000)
        cls.items = [it for r in cls.recs for it in r["items"]]

    def test_pesos_de_items_tienen_media_exacta_3(self):
        w = D.ITEM_COUNT_WEIGHTS
        self.assertEqual(sum(k * v for k, v in w.items()) / sum(w.values()), 3.0)

    def test_media_de_items(self):
        mean = len(self.items) / len(self.recs)
        self.assertTrue(2.9 <= mean <= 3.1, mean)

    def test_completed_70(self):
        frac = sum(r["payment"]["status"] == "completed" for r in self.recs) / len(self.recs)
        self.assertAlmostEqual(frac, 0.70, delta=0.01)

    def test_timestamp_2026_50(self):
        frac = sum(r["timestamp"] >= "2026-01-01T00:00:00Z" for r in self.recs) / len(self.recs)
        self.assertAlmostEqual(frac, 0.50, delta=0.01)

    def test_price_mayor_50(self):
        frac = sum(it["price"] > 50 for it in self.items) / len(self.items)
        self.assertAlmostEqual(frac, 4000 / 8901, delta=0.01)

    def test_240_grupos_pais_categoria(self):
        groups = Counter((r["customer"]["geo"]["country"], it["category"])
                         for r in self.recs for it in r["items"])
        self.assertEqual(len(groups), 12 * 20)

    def test_catalogos_ascii(self):
        texts = [*D.CATEGORIES, *D.USER_AGENTS, *D.FLAG_VALUES,
                 *(s for _, st in D.COUNTRIES.values() for k, v in st.items() for s in (k, *v))]
        for t in texts:
            self.assertTrue(t.isascii(), t)


if __name__ == "__main__":
    unittest.main()
