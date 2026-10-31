"""Pruebas de las funciones puras de scripts/verify_gate.py (F3), sin Docker.

Correr:  python3 -m unittest discover -s tests -v     (también funciona con pytest)
"""

import copy
import importlib.util
import json
import random
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
_spec = importlib.util.spec_from_file_location("verify_gate", ROOT / "scripts" / "verify_gate.py")
vg = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(vg)

from generator.synthetic_data_generator import make_record  # noqa: E402

RNG = random.Random(42)
DOCS = [make_record(RNG) for _ in range(5)]


def by_id(docs):
    return {d["order_id"]: d for d in docs}


def jsonb_order(value):
    """Reordena claves como JSONB: por longitud y luego bytewise."""
    if isinstance(value, dict):
        return {k: jsonb_order(value[k]) for k in sorted(value, key=lambda k: (len(k), k))}
    if isinstance(value, list):
        return [jsonb_order(v) for v in value]
    return value


class FirstDifferenceTest(unittest.TestCase):

    def test_iguales_con_otro_orden_de_claves(self):
        self.assertIsNone(vg.first_difference(DOCS[0], jsonb_order(DOCS[0])))

    def test_entero_y_flotante_iguales_son_iguales(self):
        self.assertIsNone(vg.first_difference({"a": 12}, {"a": 12.0}))

    def test_numero_frente_a_texto_es_diferencia(self):
        b = copy.deepcopy(DOCS[0])
        b["payment"]["final_total"] = str(b["payment"]["final_total"])
        self.assertEqual(vg.first_difference(DOCS[0], b), "$.payment.final_total")

    def test_booleano_frente_a_entero_es_diferencia(self):
        self.assertEqual(vg.first_difference({"a": 1}, {"a": True}), "$.a")

    def test_numero_cambiado(self):
        b = copy.deepcopy(DOCS[0])
        b["items"][0]["price"] += 0.01
        self.assertEqual(vg.first_difference(DOCS[0], b), "$.items[0].price")

    def test_clave_faltante(self):
        b = copy.deepcopy(DOCS[0])
        del b["metadata"]["flags"]
        self.assertEqual(vg.first_difference(DOCS[0], b), "$.metadata.flags")

    def test_orden_de_arreglo_si_importa(self):
        self.assertEqual(vg.first_difference({"c": [1.0, 2.0]}, {"c": [2.0, 1.0]}), "$.c[0]")


class ThreeWayTest(unittest.TestCase):

    def test_todo_igual(self):
        r = vg.three_way(by_id(DOCS), by_id(DOCS), by_id([jsonb_order(d) for d in DOCS]))
        self.assertEqual(r["iguales_en_los_tres"], 5)
        self.assertTrue(r["ok"])

    def test_documento_faltante_en_un_motor(self):
        r = vg.three_way(by_id(DOCS), by_id(DOCS[:4]), by_id(DOCS))
        self.assertEqual(r["faltan_en"]["mongo"], 1)
        self.assertEqual(r["iguales_en_los_tres"], 4)
        self.assertFalse(r["ok"])

    def test_documento_de_mas_en_un_motor(self):
        extra = make_record(random.Random(7))
        r = vg.three_way(by_id(DOCS), by_id(DOCS), by_id([*DOCS, extra]))
        self.assertEqual(r["faltan_en"]["fuente"], 1)
        self.assertFalse(r["ok"])

    def test_documento_distinto_se_cuenta_y_se_explica(self):
        pg = copy.deepcopy(DOCS)
        pg[2]["payment"]["final_total"] = str(pg[2]["payment"]["final_total"])
        r = vg.three_way(by_id(DOCS), by_id(DOCS), by_id(pg))
        self.assertEqual(r["distintos"], {"mongo": 0, "postgres": 1})
        self.assertEqual(r["ejemplos"][0]["primera_diferencia"], {"postgres": "$.payment.final_total"})
        self.assertFalse(r["ok"])


class CanonicalDigestTest(unittest.TestCase):
    """compare() en streaming: misma regla de igualdad que first_difference()."""

    def digest(self, doc, **kw):
        return vg.canonical_digest(json.dumps(doc), **kw)[1]

    def test_ignora_orden_de_claves(self):
        self.assertEqual(self.digest(DOCS[0]), self.digest(jsonb_order(DOCS[0])))

    def test_12_igual_a_12_punto_0(self):
        self.assertEqual(vg.canonical_digest('{"order_id":"a","x":12}')[1],
                         vg.canonical_digest('{"order_id":"a","x":12.0}')[1])

    def test_numero_frente_a_texto(self):
        b = copy.deepcopy(DOCS[0])
        b["payment"]["final_total"] = str(b["payment"]["final_total"])
        self.assertNotEqual(self.digest(DOCS[0]), self.digest(b))

    def test_booleano_frente_a_entero(self):
        self.assertNotEqual(vg.canonical_digest('{"order_id":"a","x":1}')[1],
                            vg.canonical_digest('{"order_id":"a","x":true}')[1])

    def test_numero_cambiado_en_un_centavo(self):
        b = copy.deepcopy(DOCS[0])
        b["items"][0]["price"] = round(b["items"][0]["price"] + 0.01, 2)
        self.assertNotEqual(self.digest(DOCS[0]), self.digest(b))

    def test_quita_el_id_de_mongo(self):
        with_id = {"_id": {"$oid": "65f0"}, **DOCS[0]}
        self.assertEqual(self.digest(with_id, drop_mongo_id=True), self.digest(DOCS[0]))
        self.assertNotEqual(self.digest(with_id), self.digest(DOCS[0]))

    def test_devuelve_el_order_id(self):
        self.assertEqual(vg.canonical_digest(json.dumps(DOCS[0]))[0], DOCS[0]["order_id"])


class OtrasTest(unittest.TestCase):

    def test_quita_id_de_mongo(self):
        self.assertEqual(vg.strip_mongo_id({"_id": {"$oid": "x"}, "a": 1}), {"a": 1})

    def test_r15_detecta_indice_sobre_final_total(self):
        defs = ["CREATE UNIQUE INDEX orders_pkey ON public.orders USING btree (id)",
                "CREATE INDEX x ON public.orders USING btree ((((data -> 'payment'::text) ->> 'final_total'::text)))"]
        self.assertEqual(vg.index_mentions(defs), [defs[1]])
        self.assertEqual(vg.index_mentions(defs[:1]), [])


if __name__ == "__main__":
    unittest.main()


class CompareFilesTest(unittest.TestCase):
    """compare_files() sobre archivos reales en disco, con defectos puestos a propósito."""

    def setUp(self):
        import tempfile
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.src = self.write("src.jsonl", DOCS, source=True)

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, name, docs, mongo=False, source=False):
        # Fuente: orden del generador (se valida estricto). Mongo: conserva el
        # orden y agrega _id. Postgres: claves reordenadas como JSONB.
        path = self.dir / name
        with path.open("w") as f:
            for i, d in enumerate(docs):
                if not source:
                    d = {"_id": {"$oid": f"{i:024x}"}, **d} if mongo else jsonb_order(d)
                f.write(json.dumps(d) + "\n")
        return path

    def run_case(self, mongo_docs, pg_docs):
        return vg.compare_files(self.src, self.write("m.jsonl", mongo_docs, mongo=True), self.write("p.jsonl", pg_docs))

    def test_todo_igual(self):
        r = self.run_case(DOCS, DOCS)
        c = r["comparacion_tres_direcciones"]
        self.assertTrue(r["ok"])
        self.assertEqual(c["iguales_en_los_tres"], 5)
        self.assertEqual(r["documentos_con_mismo_orden_de_claves_que_la_fuente"], {"mongo": 5, "postgres": 0})

    def test_documento_cambiado_en_postgres(self):
        pg = copy.deepcopy(DOCS)
        pg[3]["payment"]["final_total"] = str(pg[3]["payment"]["final_total"])
        r = self.run_case(DOCS, pg)
        c = r["comparacion_tres_direcciones"]
        self.assertFalse(r["ok"])
        self.assertEqual(c["distintos"], {"mongo": 0, "postgres": 1})
        self.assertEqual(c["iguales_en_los_tres"], 4)
        self.assertEqual(c["ejemplos"][0]["primera_diferencia"], "$.payment.final_total")
        self.assertEqual(r["validacion_esquema_100pct"]["postgres (sin orden)"]["invalidos"], 1)

    def test_documento_faltante_en_mongo(self):
        c = self.run_case(DOCS[:4], DOCS)["comparacion_tres_direcciones"]
        self.assertEqual(c["faltan_en"], {"fuente": 0, "mongo": 1, "postgres": 0})
        self.assertEqual(c["iguales_en_los_tres"], 4)
        self.assertFalse(c["ok"])

    def test_documento_de_mas_en_postgres(self):
        extra = make_record(random.Random(7))
        c = self.run_case(DOCS, [*DOCS, extra])["comparacion_tres_direcciones"]
        self.assertEqual(c["faltan_en"]["fuente"], 1)
        self.assertFalse(c["ok"])
