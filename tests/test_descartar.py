"""Pruebas de scripts/descartar_repeticion.py (F8-b).

Lo que se protege, con la condición de Alix (2026-11-02): descartar una
repetición tiene que ser **visible y auditable**, nunca silencioso.
  - el motivo es obligatorio y no puede estar vacío;
  - la fila descartada queda registrada con su motivo (es la tabla del reporte, R-27.1);
  - el crudo y la telemetría se MUEVEN, no se borran;
  - el CSV conserva su encabezado y las demás filas byte a byte;
  - después, la repetición vuelve a verse como pendiente (schedule);
  - descartar algo que no existe no toca nada.
"""

from __future__ import annotations

import csv
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from benchmark_runner import csv_writer, schedule

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "descartar_repeticion.py"
KEY = ("mongodb", "PROFILE_C_SEVERE", "Q2_MEM_LOW", 50, 2)


def row_for(engine, profile, query_id, conc, run, status="ok", qps="1.5"):
    row = {c: "" for c in csv_writer.COLUMNS}
    row.update({"timestamp_epoch": "1793600000", "engine": engine, "profile": profile, "query_id": query_id,
                "concurrency": str(conc), "run_number": str(run), "throughput_qps": qps,
                "latency_p50_ms": "1.0", "latency_p95_ms": "2.0", "latency_p99_ms": "3.0",
                "cpu_throttled_seconds": "4.0", "max_rss_mb": "5.0", "disk_spill": "false", "status": status})
    return row


class DescartarTest(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.base = self.dir / "results" / "f8prueba"
        (self.base / "raw").mkdir(parents=True)
        (self.base / "telemetry").mkdir(parents=True)
        self.csv = self.base / "measurements.csv"
        self.rows = [row_for("mongodb", "PROFILE_C_SEVERE", "Q2_MEM_LOW", 50, 1),
                     row_for(*KEY, status="error", qps="0.001"),
                     row_for("postgresql", "PROFILE_A_BASELINE", "Q1", 1, 1)]
        with self.csv.open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=csv_writer.COLUMNS)
            w.writeheader()
            for r in self.rows:
                w.writerow(r)
        self.rid = "mongodb_PROFILE_C_SEVERE_Q2_MEM_LOW_c50_r2"
        (self.base / "raw" / f"{self.rid}.json").write_text('{"run_id": "x"}')
        (self.base / "telemetry" / f"{self.rid}.json").write_text('{"t": 1}')
        self.before = self.csv.read_text()

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def run_script(self, *args):
        """El script trabaja sobre ROOT/results, así que se le pasa un ROOT falso."""
        env = {"PYTHONPATH": str(ROOT)}
        code = (f"import sys; sys.argv = ['x', *{list(args)!r}];"
                f"sys.path.insert(0, {str(ROOT / 'scripts')!r});"
                f"import descartar_repeticion as d;"
                f"d.ROOT = {str(self.dir)!r};"
                f"from pathlib import Path; d.ROOT = Path(d.ROOT);"
                f"sys.exit(d.main())")
        return subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env)

    def discard_ok(self, motivo="el equipo se suspendió 4 min dentro de la ventana"):
        return self.run_script("--salida", "f8prueba", "--engine", KEY[0], "--profile", KEY[1],
                               "--query-id", KEY[2], "--concurrency", str(KEY[3]),
                               "--run-number", str(KEY[4]), "--motivo", motivo)

    def test_motivo_es_obligatorio(self):
        res = self.run_script("--salida", "f8prueba", "--engine", KEY[0], "--profile", KEY[1],
                              "--query-id", KEY[2], "--concurrency", str(KEY[3]), "--run-number", str(KEY[4]))
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("--motivo", res.stderr)
        self.assertEqual(self.csv.read_text(), self.before)          # no tocó nada

    def test_motivo_vacio_se_rechaza(self):
        res = self.discard_ok(motivo="   ")
        self.assertNotEqual(res.returncode, 0)
        self.assertEqual(self.csv.read_text(), self.before)

    def test_descarta_y_deja_rastro(self):
        res = self.discard_ok()
        self.assertEqual(res.returncode, 0, res.stderr)

        # El CSV pierde solo esa fila, y el resto queda byte a byte.
        quedan = self.csv.read_text().splitlines()
        self.assertEqual(quedan[0], self.before.splitlines()[0])      # encabezado intacto
        self.assertEqual(len(quedan), 3)                              # encabezado + 2 filas
        self.assertNotIn(",error,", self.csv.read_text())
        for original in (self.before.splitlines()[1], self.before.splitlines()[3]):
            self.assertIn(original, self.csv.read_text())

        # Queda registrada con su motivo: es la tabla del reporte (R-27.1).
        with (self.base / "descartadas.csv").open() as f:
            reg = list(csv.DictReader(f))
        self.assertEqual(len(reg), 1)
        self.assertEqual(reg[0]["run_id"], self.rid)
        self.assertEqual(reg[0]["status"], "error")
        self.assertIn("suspendió", reg[0]["motivo"])
        self.assertTrue(reg[0]["descartada_utc"])

        # El crudo y la telemetría se MUEVEN, no se borran.
        self.assertFalse((self.base / "raw" / f"{self.rid}.json").exists())
        self.assertEqual(len(list((self.base / "raw" / "descartadas").glob("*.json"))), 1)
        self.assertEqual(len(list((self.base / "telemetry" / "descartadas").glob("*.json"))), 1)

        # Y hay copia de seguridad del CSV anterior.
        self.assertEqual(len(list(self.base.glob("measurements.csv.bak-*"))), 1)

    def test_vuelve_a_estar_pendiente(self):
        self.discard_ok()
        pend = {(c.engine, c.profile, c.query_id, c.concurrency): r
                for c, r in schedule.pending(self.csv, 54)}
        self.assertIn(2, pend[(KEY[0], KEY[1], KEY[2], KEY[3])])
        self.assertNotIn(1, pend[(KEY[0], KEY[1], KEY[2], KEY[3])])   # la 1 sigue hecha

    def test_descartar_dos_veces_la_segunda_no_encuentra_nada(self):
        self.assertEqual(self.discard_ok().returncode, 0)
        antes = self.csv.read_text()
        res = self.discard_ok(motivo="otra vez")
        self.assertNotEqual(res.returncode, 0)
        self.assertEqual(self.csv.read_text(), antes)
        with (self.base / "descartadas.csv").open() as f:
            self.assertEqual(len(list(csv.DictReader(f))), 1)

    def test_clave_inexistente_no_toca_nada(self):
        res = self.run_script("--salida", "f8prueba", "--engine", "mongodb", "--profile", "PROFILE_A_BASELINE",
                              "--query-id", "Q1", "--concurrency", "10", "--run-number", "3",
                              "--motivo", "prueba")
        self.assertNotEqual(res.returncode, 0)
        self.assertEqual(self.csv.read_text(), self.before)
        self.assertFalse((self.base / "descartadas.csv").exists())

    def test_listar_con_cero_descartes_lo_dice(self):
        res = self.run_script("--salida", "f8prueba", "--listar")
        self.assertEqual(res.returncode, 0)
        self.assertIn("descartadas: 0", res.stdout)


if __name__ == "__main__":
    unittest.main()
