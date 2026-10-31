"""Esquema del CSV (R-26): encabezado contra el PDF, escritor y validador (F5.2).

Correr:  python3 -m unittest discover -s tests -v     (también funciona con pytest)
"""

import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from benchmark_runner import csv_writer as S  # noqa: E402

sys.path.insert(0, str(ROOT / "scripts"))
import validate_csv as V  # noqa: E402


def good_row(**over):
    row = {"timestamp_epoch": 1793563200, "engine": "mongodb", "profile": "PROFILE_C_SEVERE",
           "query_id": "Q2_MEM_LOW", "concurrency": 1, "run_number": 1, "throughput_qps": 12.5,
           "latency_p50_ms": 70.1, "latency_p95_ms": 90.2, "latency_p99_ms": 99.9,
           "cpu_throttled_seconds": 3.25, "max_rss_mb": 410.0, "disk_spill": False, "status": "ok"}
    row.update(over)
    return row


class EncabezadoTest(unittest.TestCase):

    def test_igual_al_pdf_sin_espacios(self):
        """§8.2 de playbook.pdf, extraído con pdftotext, sin espacios (F5-h)."""
        if not shutil.which("pdftotext"):
            self.skipTest("pdftotext no instalado (poppler-utils)")
        text = subprocess.run(["pdftotext", "-layout", str(ROOT / "docs/manual/playbook.pdf"), "-"],
                              capture_output=True, text=True, check=True).stdout
        block = re.search(r"8\.2\..*?\n(.*?)\n\s*\n", text, re.S).group(1)
        self.assertEqual(re.sub(r"\s", "", block), S.header())

    def test_con_espacios_es_el_texto_del_pdf(self):
        if not shutil.which("pdftotext"):
            self.skipTest("pdftotext no instalado (poppler-utils)")
        text = subprocess.run(["pdftotext", "-layout", str(ROOT / "docs/manual/playbook.pdf"), "-"],
                              capture_output=True, text=True, check=True).stdout
        block = re.search(r"8\.2\..*?\n(.*?)\n\s*\n", text, re.S).group(1)
        self.assertEqual(re.sub(r"\s+", " ", block).strip(), S.header(header_spaces=True))

    def test_igual_a_spec(self):
        spec = re.search(r"^timestamp_epoch,[^\n]+", (ROOT / "SPEC.md").read_text(), re.M).group(0)
        self.assertEqual(spec, S.header())

    def test_14_columnas(self):
        self.assertEqual(len(S.COLUMNS), 14)
        self.assertEqual(len(set(S.COLUMNS)), 14)


class EscritorTest(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "m.csv"

    def tearDown(self):
        self.tmp.cleanup()

    def test_escribe_encabezado_una_vez_y_filas(self):
        w = S.CsvWriter(self.path)
        w.write(good_row())
        S.CsvWriter(self.path).write(good_row(run_number=2))   # reabrir no repite el encabezado
        lines = self.path.read_text().splitlines()
        self.assertEqual(lines[0], S.header())
        self.assertEqual(len(lines), 3)
        self.assertEqual(lines[1].split(",")[12:], ["false", "ok"])
        self.assertEqual(lines[1].split(",")[7], "70.100")      # latencias: 3 decimales
        self.assertEqual(lines[1].split(",")[6], "12.500000")   # throughput: 6

    def test_throughput_conserva_el_conteo_de_completadas(self):
        w = S.CsvWriter(self.path)
        for run, completed in ((1, 1), (2, 2), (3, 7)):
            w.write(good_row(run_number=run, throughput_qps=completed / 300))
        for line, completed in zip(self.path.read_text().splitlines()[1:], (1, 2, 7)):
            self.assertEqual(round(float(line.split(",")[6]) * 300), completed)
            self.assertAlmostEqual(float(line.split(",")[6]) * 300, completed, places=3)

    def test_rechaza_columna_de_mas(self):
        with self.assertRaises(S.SchemaError):
            S.CsvWriter(self.path).write(good_row(extra=1))

    def test_rechaza_columna_faltante(self):
        row = good_row()
        del row["max_rss_mb"]
        with self.assertRaises(S.SchemaError):
            S.CsvWriter(self.path).write(row)

    def test_no_mezcla_encabezados(self):
        self.path.write_text(S.header(header_spaces=True) + "\n")
        with self.assertRaises(S.SchemaError):
            S.CsvWriter(self.path)

    def test_con_espacios_si_se_pide(self):
        S.CsvWriter(self.path, header_spaces=True).write(good_row())
        self.assertEqual(self.path.read_text().splitlines()[0], S.header(header_spaces=True))


class ValidadorTest(unittest.TestCase):
    """El validador debe FALLAR ante cada defecto puesto a propósito (PLAN, sonda 5)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "m.csv"
        w = S.CsvWriter(self.path)
        for r in (1, 2, 3):
            w.write(good_row(run_number=r))

    def tearDown(self):
        self.tmp.cleanup()

    def tamper(self, fn):
        lines = self.path.read_text().splitlines()
        self.path.write_text("\n".join(fn(lines)) + "\n")
        return V.validate(self.path)

    def test_archivo_bueno_pasa(self):
        self.assertEqual(V.validate(self.path, expect_rows=3), [])

    def test_columna_extra_hace_fallar(self):
        problems = self.tamper(lambda ls: [ls[0] + ",variant"] + [l + ",x" for l in ls[1:]])
        self.assertTrue(problems)
        self.assertIn("encabezado", problems[0])

    def test_columna_renombrada_hace_fallar(self):
        self.assertTrue(self.tamper(lambda ls: [ls[0].replace("max_rss_mb", "rss_mb")] + ls[1:]))

    def test_columnas_reordenadas_hacen_fallar(self):
        def swap(ls):
            h = ls[0].split(",")
            h[0], h[1] = h[1], h[0]
            return [",".join(h)] + ls[1:]
        self.assertTrue(self.tamper(swap))

    def test_fila_con_columnas_de_menos(self):
        self.assertTrue(self.tamper(lambda ls: ls[:1] + [ls[1].rsplit(",", 1)[0]] + ls[2:]))

    def test_fila_duplicada(self):
        problems = self.tamper(lambda ls: ls + [ls[1]])
        self.assertTrue(any("duplicada" in p for p in problems))

    def test_conteo_de_filas(self):
        self.assertTrue(V.validate(self.path, expect_rows=162))

    def test_encabezado_con_espacios_solo_con_la_opcion(self):
        self.tamper(lambda ls: [S.header(header_spaces=True)] + ls[1:])
        self.assertTrue(V.validate(self.path))
        self.assertEqual(V.validate(self.path, header_spaces=True), [])

    def test_disk_spill_no_booleano(self):
        self.assertTrue(self.tamper(lambda ls: ls[:1] + [ls[1].replace(",false,", ",no,")] + ls[2:]))


if __name__ == "__main__":
    unittest.main()
