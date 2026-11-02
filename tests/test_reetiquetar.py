"""Pruebas de scripts/reetiquetar_q2.py (A2 resuelta con 36 celdas).

Lo que se protege:
  - sin --confirmo no se toca nada;
  - el CSV cambia SOLO la columna query_id, y las demás líneas quedan byte a byte;
  - los crudos, la telemetría y los planes se renombran, y cada crudo queda con su
    propio rastro (`reetiquetado`) y con `opciones` intacto, que es donde consta
    que la variante medida fue la restrictiva;
  - después, el CSV pasa el validador con --matrix 36;
  - correr dos veces no rompe nada.
"""

from __future__ import annotations

import csv
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from benchmark_runner import csv_writer

ROOT = Path(__file__).resolve().parent.parent


def row(query_id: str, conc: int, run: int, status: str = "ok") -> dict:
    r = {c: "" for c in csv_writer.COLUMNS}
    r.update({"timestamp_epoch": "1793600000", "engine": "mongodb", "profile": "PROFILE_C_SEVERE",
              "query_id": query_id, "concurrency": str(conc), "run_number": str(run),
              "throughput_qps": "0.053333", "latency_p50_ms": "19329.5", "latency_p95_ms": "20461.0",
              "latency_p99_ms": "20683.0", "cpu_throttled_seconds": "183.0", "max_rss_mb": "612.519531",
              "disk_spill": "false", "status": status})
    return r


class ReetiquetarTest(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.base = self.dir / "results"
        for sub in ("raw", "telemetry", "explains"):
            (self.base / sub).mkdir(parents=True)
        self.csv = self.base / "measurements.csv"
        self.rows = [row("Q1", 1, 1), row("Q2_MEM_LOW", 1, 1), row("Q2_MEM_LOW", 50, 2, "error")]
        with self.csv.open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=csv_writer.COLUMNS)
            w.writeheader()
            for r in self.rows:
                w.writerow(r)
        self.antes = self.csv.read_text()
        self.rid = "mongodb_PROFILE_C_SEVERE_Q2_MEM_LOW_c1_r1"
        (self.base / "raw" / f"{self.rid}.json").write_text(json.dumps({
            "run_id": self.rid, "fila_csv": {"query_id": "Q2_MEM_LOW", "engine": "mongodb"},
            "opciones": {"allowDiskUse": False}, "muestras": [[1, 2, 1, 0]]}))
        (self.base / "telemetry" / f"{self.rid}.json").write_text('{"run_id": "x"}')
        (self.base / "explains" / "mongodb_PROFILE_C_SEVERE_Q2_MEM_LOW_c1.json").write_text("{}")

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def run_script(self, *args):
        code = (f"import sys; sys.argv = ['x', *{list(args)!r}];"
                f"sys.path.insert(0, {str(ROOT / 'scripts')!r});"
                f"import reetiquetar_q2 as r;"
                f"from pathlib import Path; r.ROOT = Path({str(self.dir)!r});"
                f"sys.exit(r.main())")
        return subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                              env={"PYTHONPATH": str(ROOT)})

    def test_sin_confirmo_no_cambia_nada(self):
        res = self.run_script()
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("54" if False else "2", res.stdout)          # 2 filas a cambiar
        self.assertEqual(self.csv.read_text(), self.antes)
        self.assertTrue((self.base / "raw" / f"{self.rid}.json").exists())

    def test_cambia_solo_la_columna_query_id(self):
        self.assertEqual(self.run_script("--confirmo").returncode, 0)
        lineas = self.csv.read_text().splitlines()
        self.assertEqual(lineas[0], self.antes.splitlines()[0])     # encabezado intacto
        self.assertEqual(lineas[1], self.antes.splitlines()[1])     # la fila Q1, byte a byte
        with self.csv.open(newline="") as f:
            nuevas = list(csv.DictReader(f))
        self.assertEqual([r["query_id"] for r in nuevas], ["Q1", "Q2", "Q2"])
        # Todo lo demás de las filas cambiadas sigue igual.
        for antes, ahora in zip(self.rows[1:], nuevas[1:]):
            self.assertEqual({k: v for k, v in antes.items() if k != "query_id"},
                             {k: v for k, v in ahora.items() if k != "query_id"})

    def test_renombra_y_deja_rastro_en_cada_crudo(self):
        self.run_script("--confirmo")
        nuevo = self.base / "raw" / "mongodb_PROFILE_C_SEVERE_Q2_c1_r1.json"
        self.assertTrue(nuevo.exists())
        self.assertFalse((self.base / "raw" / f"{self.rid}.json").exists())
        d = json.loads(nuevo.read_text())
        self.assertEqual(d["run_id"], "mongodb_PROFILE_C_SEVERE_Q2_c1_r1")
        self.assertEqual(d["fila_csv"]["query_id"], "Q2")
        self.assertEqual(d["reetiquetado"]["de"], "Q2_MEM_LOW")
        self.assertEqual(d["reetiquetado"]["a"], "Q2")
        self.assertIn("36 celdas", d["reetiquetado"]["motivo"])
        # La configuración real de la variante NO se toca: es lo que prueba qué se midió.
        self.assertEqual(d["opciones"], {"allowDiskUse": False})
        self.assertEqual(d["muestras"], [[1, 2, 1, 0]])
        self.assertTrue((self.base / "telemetry" / "mongodb_PROFILE_C_SEVERE_Q2_c1_r1.json").exists())
        self.assertTrue((self.base / "explains" / "mongodb_PROFILE_C_SEVERE_Q2_c1.json").exists())

    def test_copia_de_seguridad_y_registro(self):
        self.run_script("--confirmo")
        copias = list(self.base.glob("measurements.csv.bak-*"))
        self.assertEqual(len(copias), 1)
        self.assertEqual(copias[0].read_text(), self.antes)         # la copia es el original exacto
        registros = list(self.base.glob("reetiquetado_*.json"))
        self.assertEqual(len(registros), 1)
        reg = json.loads(registros[0].read_text())
        self.assertEqual(reg["filas_cambiadas"], 2)
        self.assertEqual(len(reg["archivos_renombrados"]["raw"]), 1)

    def test_el_csv_pasa_el_validador_con_36(self):
        self.run_script("--confirmo")
        res = subprocess.run([sys.executable, str(ROOT / "scripts" / "validate_csv.py"), str(self.csv),
                              "--matrix", "36"], capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)

    def test_se_puede_revertir(self):
        """Que sea reversible es la condición para aplicarlo sobre evidencia ya medida."""
        self.run_script("--confirmo")
        registro = next(self.base.glob("reetiquetado_*.json"))
        res = self.run_script("--revertir", str(registro))
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertEqual(self.csv.read_text(), self.antes)
        viejo = self.base / "raw" / f"{self.rid}.json"
        self.assertTrue(viejo.exists())
        self.assertFalse((self.base / "raw" / "mongodb_PROFILE_C_SEVERE_Q2_c1_r1.json").exists())
        d = json.loads(viejo.read_text())
        self.assertEqual(d["run_id"], self.rid)
        self.assertEqual(d["fila_csv"]["query_id"], "Q2_MEM_LOW")
        self.assertNotIn("reetiquetado", d)
        self.assertEqual(d["opciones"], {"allowDiskUse": False})
        self.assertTrue(registro.exists())                          # el rastro se conserva

    def test_dos_veces_no_rompe(self):
        self.run_script("--confirmo")
        despues = self.csv.read_text()
        res = self.run_script("--confirmo")
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("nada que hacer", res.stdout)
        self.assertEqual(self.csv.read_text(), despues)
        self.assertEqual(len(list(self.base.glob("reetiquetado_*.json"))), 1)


if __name__ == "__main__":
    unittest.main()
