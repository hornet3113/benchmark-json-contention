"""Pruebas de scripts/check_equivalence.py (F4): referencia exacta, comparadores y planes.

Sin Docker: los resultados de los motores se fabrican. Si los comparadores no
detectan un problema puesto a propósito, que "cuadre" en G2 no probaría nada.

Correr:  python3 -m unittest discover -s tests -v     (también funciona con pytest)
"""

import copy
import importlib.util
import json
import random
import sys
import unittest
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
_spec = importlib.util.spec_from_file_location("check_equivalence", ROOT / "scripts" / "check_equivalence.py")
ce = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ce)

from generator.synthetic_data_generator import make_record, serialize  # noqa: E402


def exact_docs(n, seed=42):
    rng = random.Random(seed)
    return [json.loads(serialize(make_record(rng)), parse_float=Decimal) for _ in range(n)]


DOCS = exact_docs(3000)
T1 = ce.truth_q1(DOCS)
T2 = ce.truth_q2(DOCS)


def doc(oid, final, status="completed", ts="2026-06-01T00:00:00Z", cust="C000001"):
    return {"order_id": oid, "timestamp": ts, "customer": {"id": cust},
            "payment": {"status": status, "final_total": Decimal(final)}}


class ReferenciaQ1Test(unittest.TestCase):

    def test_coincide_con_un_calculo_independiente_en_float(self):
        acc = {}
        for d in DOCS:
            for it in d["items"]:
                if float(it["price"]) > 50:
                    k = (d["customer"]["geo"]["country"], it["category"])
                    a = acc.setdefault(k, [0.0, 0])
                    a[0] += it["qty"] * float(it["price"])
                    a[1] += 1
        self.assertEqual(set(acc), set(T1))
        for k, (tot, n) in acc.items():
            self.assertEqual(T1[k]["count"], n)
            self.assertAlmostEqual(float(T1[k]["total"]), tot, places=6)

    def test_precio_exactamente_50_no_entra(self):
        d = copy.deepcopy(DOCS[0])
        d["items"] = [{**d["items"][0], "price": Decimal("50.00"), "qty": 1}]
        self.assertEqual(ce.truth_q1([d]), {})


class ReferenciaQ2Test(unittest.TestCase):

    def test_limite_de_fecha_incluido_y_excluido(self):
        self.assertTrue(ce.q2_filter(doc("a", "1", ts="2026-01-01T00:00:00Z")))
        self.assertFalse(ce.q2_filter(doc("a", "1", ts="2025-12-31T23:59:59Z")))
        self.assertFalse(ce.q2_filter(doc("a", "1", status="pending")))

    def test_detecta_la_trampa_de_fracciones_de_segundo(self):
        # Texto: ".5Z" < "Z" → no entra. Tiempo: 00:00:00.5 ≥ 00:00:00 → sí entra.
        with self.assertRaises(ValueError):
            ce.q2_filter(doc("a", "1", ts="2026-01-01T00:00:00.5Z"))

    def test_frontera_y_repetidos(self):
        docs = [doc(f"id{i}", v) for i, v in enumerate(["10", "9", "9", "8"])]
        old = ce.Q2_LIMIT
        try:
            ce.Q2_LIMIT = 2                      # top [10, 9] · frontera 9 | 9
            t = ce.truth_q2(docs)
            self.assertTrue(t["frontera"]["empate"])
            self.assertEqual(t["repetidos_dentro_del_top"], 0)
            ce.Q2_LIMIT = 3                      # top [10, 9, 9] · frontera 9 | 8
            t = ce.truth_q2(docs)
            self.assertFalse(t["frontera"]["empate"])
            self.assertEqual(t["repetidos_dentro_del_top"], 1)
        finally:
            ce.Q2_LIMIT = old

    def test_sobre_datos_reales_el_top_esta_ordenado(self):
        vals = [r[2] for r in T2["top"]]
        self.assertEqual(vals, sorted(vals, reverse=True))
        self.assertLessEqual(len(vals), ce.Q2_LIMIT)


def engine_q1(truth, scale=Decimal(1), as_float=True):
    return {k: {"total": float(v["total"] * scale) if as_float else v["total"] * scale,
                "avg": float(v["avg"] * scale) if as_float else v["avg"] * scale,
                "count": v["count"]} for k, v in truth.items()}


class CompareQ1Test(unittest.TestCase):

    def test_floats_de_mongo_dentro_de_tolerancia(self):
        r = ce.compare_q1(T1, engine_q1(T1))
        self.assertTrue(r["ok"], r)

    def test_decimal_exacto_da_cero(self):
        r = ce.compare_q1(T1, engine_q1(T1, as_float=False))
        self.assertEqual(r["max_dif_rel_total_revenue"], "0.000e+00")

    def test_fuera_de_tolerancia(self):
        r = ce.compare_q1(T1, engine_q1(T1, scale=Decimal("1.00001")))
        self.assertFalse(r["ok"])

    def test_grupo_faltante_y_sobrante(self):
        rows = engine_q1(T1)
        k = next(iter(rows))
        rows.pop(k)
        rows[("XX", "nada")] = {"total": 1.0, "avg": 1.0, "count": 1}
        r = ce.compare_q1(T1, rows)
        self.assertEqual((len(r["faltan"]), len(r["sobran"])), (1, 1))
        self.assertFalse(r["ok"])

    def test_count_distinto(self):
        rows = engine_q1(T1)
        k = next(iter(rows))
        rows[k]["count"] += 1
        self.assertFalse(ce.compare_q1(T1, rows)["ok"])


class CompareQ2Test(unittest.TestCase):

    def test_mismo_conjunto_en_otro_orden(self):
        rows = list(reversed([(o, c, float(f)) for o, c, f in T2["top"]]))
        self.assertTrue(ce.compare_q2(T2["top"], rows)["ok"])

    def test_un_order_id_cambiado(self):
        rows = [(o, c, f) for o, c, f in T2["top"]]
        rows[-1] = ("otro", rows[-1][1], rows[-1][2])
        r = ce.compare_q2(T2["top"], rows)
        self.assertEqual((r["faltan"], r["sobran"]), (1, 1))
        self.assertFalse(r["ok"])

    def test_customer_id_distinto(self):
        rows = [(o, c, f) for o, c, f in T2["top"]]
        rows[0] = (rows[0][0], "C999999", rows[0][2])
        self.assertFalse(ce.compare_q2(T2["top"], rows)["ok"])

    def test_vector_fuera_de_tolerancia(self):
        rows = [(o, c, f) for o, c, f in T2["top"]]
        rows[0] = (rows[0][0], rows[0][1], rows[0][2] * Decimal("1.001"))
        self.assertFalse(ce.compare_q2(T2["top"], rows)["ok"])

    def test_filas_de_menos(self):
        self.assertFalse(ce.compare_q2(T2["top"], T2["top"][:-1])["ok"])


class VariantesYPlanesTest(unittest.TestCase):

    def test_same_result_ignora_el_orden_de_filas(self):
        self.assertTrue(ce.same_result([["a", "c", 2.0], ["b", "c", 1.0]], [["b", "c", 1.0], ["a", "c", 2.0]]))
        self.assertFalse(ce.same_result([["a", "c", 2.0]], [["a", "c", 2.5]]))

    def test_resumen_plan_mongo(self):
        plan = {"stages": [{"$cursor": {"queryPlanner": {"winningPlan": {"stage": "PROJECTION", "inputStage": {
                    "stage": "FETCH", "inputStage": {"stage": "IXSCAN", "indexName": "idx_orders_timestamp"}}}},
                    "executionStats": {"totalDocsExamined": 50, "totalKeysExamined": 50}}},
                {"$sort": {"usedDisk": False}}]}
        s = ce.mongo_plan_summary(plan)
        self.assertEqual(s["etapas_pipeline"], ["$cursor", "$sort"])
        self.assertEqual(s["indices_usados"], ["idx_orders_timestamp"])
        self.assertEqual(s["etapas_plan"], ["PROJECTION", "FETCH", "IXSCAN"])
        self.assertFalse(s["usedDisk"])
        self.assertEqual(s["totalDocsExamined"], 50)

    def test_resumen_plan_postgres(self):
        plan = [{"Plan": {"Node Type": "Limit", "Plans": [{"Node Type": "Sort", "Sort Method": "top-N heapsort",
                 "Sort Space Used": 200, "Sort Space Type": "Memory", "Plans": [{"Node Type": "Seq Scan"}]}]},
                 "Execution Time": 3.5}]
        s = ce.pg_plan_summary(plan)
        self.assertEqual(s["nodos"], ["Limit", "Sort", "Seq Scan"])
        self.assertFalse(s["usa_indice"])
        self.assertEqual(s["ordenamientos"][0]["Sort Method"], "top-N heapsort")

    def test_csv_de_psql_con_show(self):
        wm, rows = ce.parse_pg_csv("work_mem\n4MB\norder_id,customer_id,final_total\na,C1,10.50\n")
        self.assertEqual(wm, "4MB")
        self.assertEqual(rows, [{"order_id": "a", "customer_id": "C1", "final_total": "10.50"}])


class QueriesLiteralesTest(unittest.TestCase):
    """Los archivos de queries/ son los que se extrajeron del PDF (queries/README.md)."""

    def test_hashes_registrados(self):
        import hashlib
        readme = (ROOT / "queries" / "README.md").read_text()
        for path in ce.QUERY_FILES.values():
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            self.assertIn(digest, readme, path)

    def test_pipelines_son_json_valido(self):
        for (engine, _), path in ce.QUERY_FILES.items():
            if engine == "mongo":
                self.assertIsInstance(json.loads(path.read_text()), list)


if __name__ == "__main__":
    unittest.main()


class UnaPasadaTest(unittest.TestCase):
    """truths() en una pasada (G3) da lo mismo que las referencias por separado."""

    def test_misma_referencia(self):
        q1, q2 = ce.truths(iter(DOCS))
        self.assertEqual(q1, T1)
        self.assertEqual(q2, T2)

    def test_iter_exact_lee_decimales(self):
        import tempfile
        with tempfile.NamedTemporaryFile("wb", suffix=".jsonl", delete=False) as f:
            f.write(serialize(make_record(random.Random(42))))
        first = next(ce.iter_exact(Path(f.name)))
        Path(f.name).unlink()
        self.assertIsInstance(first["payment"]["final_total"], Decimal)


class TempBlocksTest(unittest.TestCase):
    """EXPLAIN informa los bloques de cada nodo incluyendo a sus hijos: no se suman."""

    PLAN = [{"Plan": {"Node Type": "Aggregate", "Temp Written Blocks": 100, "Plans": [
        {"Node Type": "Incremental Sort", "Temp Written Blocks": 100, "Plans": [
            {"Node Type": "Sort", "Temp Written Blocks": 80, "Plans": [{"Node Type": "Seq Scan"}]}]}]}}]

    def test_total_es_el_del_nodo_raiz(self):
        s = ce.pg_plan_summary(self.PLAN)
        self.assertEqual(s["temp_written_blocks"], 100)          # no 280
        self.assertEqual(s["temp_written_mib"], round(100 * 8192 / 2**20, 1))

    def test_bloques_propios_por_nodo(self):
        s = ce.pg_plan_summary(self.PLAN)
        self.assertEqual(s["temp_por_nodo"], [{"nodo": "Incremental Sort", "temp_written_blocks_propios": 20},
                                              {"nodo": "Sort", "temp_written_blocks_propios": 80}])
