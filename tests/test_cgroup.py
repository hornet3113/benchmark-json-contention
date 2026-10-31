"""Pruebas del muestreo del cgroup (benchmark_runner/metrics/cgroup.py) con un cgroup falso en disco.

Lo que se protege (F6): el muestreador guarda la serie COMPLETA de 1 s para
results/raw/ (curva de RSS sin Prometheus), con shmem/file (F6-A3), y
max_rss_mb sigue saliendo solo de `anon`.
"""

from __future__ import annotations

import shutil
import tempfile
import time
import unittest
from pathlib import Path

from benchmark_runner.metrics.cgroup import SAMPLE_COLUMNS, AnonSampler, Cgroup, delta, parse_flat

CID = "abc123"


def write_cgroup(root: Path, anon: int, shmem: int = 7, file: int = 11, inactive_file: int = 1,
                 current: int = 100, throttled: int = 5, usage: int = 9) -> None:
    d = root / CID
    d.mkdir(parents=True, exist_ok=True)
    (d / "memory.stat").write_text(f"anon {anon}\nfile {file}\nshmem {shmem}\ninactive_file {inactive_file}\n")
    (d / "cpu.stat").write_text(f"usage_usec {usage}\nnr_periods 3\nnr_throttled 2\nthrottled_usec {throttled}\n")
    (d / "memory.events").write_text("low 0\nhigh 0\nmax 0\noom 0\noom_kill 0\n")
    (d / "memory.current").write_text(f"{current}\n")


class CgroupFake(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)


class SampleTest(CgroupFake):
    def test_row_follows_columns(self):
        write_cgroup(self.root, anon=2**20, shmem=3, file=4, inactive_file=2, current=50, throttled=60, usage=70)
        row = Cgroup(CID, root=self.root).sample()
        self.assertEqual(len(row), len(SAMPLE_COLUMNS) - 1)       # sin la marca de tiempo
        self.assertEqual(dict(zip(SAMPLE_COLUMNS[1:], row)),
                         {"anon": 2**20, "shmem": 3, "file": 4, "inactive_file": 2, "memory_current": 50,
                          "throttled_usec": 60, "usage_usec": 70})

    def test_missing_cgroup_is_an_error_not_a_fallback(self):
        with self.assertRaises(FileNotFoundError):
            Cgroup("no-existe", root=self.root)


class SamplerTest(CgroupFake):
    def test_keeps_every_sample_and_max_comes_from_anon(self):
        write_cgroup(self.root, anon=3 * 2**20, shmem=900 * 2**20)   # shmem grande NO cuenta para max_rss
        s = AnonSampler(Cgroup(CID, root=self.root), 0.02)
        s.start()
        time.sleep(0.05)
        write_cgroup(self.root, anon=5 * 2**20, shmem=900 * 2**20)
        time.sleep(0.05)
        s.stop()
        self.assertGreaterEqual(len(s.samples), 3)
        self.assertTrue(all(len(r) == len(SAMPLE_COLUMNS) for r in s.samples))
        self.assertEqual(s.max_mib, 5.0)
        anons = [r[SAMPLE_COLUMNS.index("anon")] for r in s.samples]
        self.assertIn(3 * 2**20, anons)                              # la serie, no solo el máximo
        ts = [r[0] for r in s.samples]
        self.assertEqual(ts, sorted(ts))

    def test_dead_container_is_recorded_and_sampling_goes_on(self):
        write_cgroup(self.root, anon=2**20)
        s = AnonSampler(Cgroup(CID, root=self.root), 0.02)
        s.start()
        time.sleep(0.05)
        shutil.rmtree(self.root / CID)                               # p. ej. OOM: el cgroup desaparece
        time.sleep(0.05)
        s.stop()
        self.assertTrue(s.errors)
        self.assertEqual(s.max_mib, 1.0)                              # lo leído antes se conserva

    def test_no_samples_gives_none_not_zero(self):
        write_cgroup(self.root, anon=2**20)
        self.assertIsNone(AnonSampler(Cgroup(CID, root=self.root), 1).max_mib)


class HelpersTest(unittest.TestCase):
    def test_parse_flat_and_delta(self):
        self.assertEqual(parse_flat("a 1\nb -2\nmalo x\n"), {"a": 1, "b": -2})
        self.assertEqual(delta({"k": 3}, {"k": 10}, "k"), 7)
        self.assertIsNone(delta({"k": None}, {"k": 10}, "k"))


if __name__ == "__main__":
    unittest.main()
