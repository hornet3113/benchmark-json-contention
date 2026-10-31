"""Pruebas de scripts/capture_env.py sin Docker: el runner de comandos se simula.

Correr:  python3 -m unittest discover -s tests -v     (también funciona con pytest)
"""

import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("capture_env", ROOT / "scripts" / "capture_env.py")
capture_env = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(capture_env)

MEMINFO = """MemTotal:        7507156 kB
MemFree:         3000000 kB
MemAvailable:    5400000 kB
Buffers:           10000 kB
Cached:          1400000 kB
SwapCached:            0 kB
SReclaimable:      90000 kB
SwapTotal:       2097152 kB
SwapFree:        2097152 kB
"""
LOADAVG = "0.42 0.12 0.17 1/661 9355\n"

INSPECT = [{
    "Image": "sha256:e0ce",
    "Config": {"Labels": {"bench.profile": "PROFILE_C_SEVERE"}},
    "State": {"OOMKilled": False},
    "HostConfig": {"NanoCpus": 1000000000, "CpuQuota": 0, "CpuPeriod": 0,
                   "Memory": 1073741824, "MemorySwap": 1073741824, "MemorySwappiness": None,
                   "CpusetCpus": "0-7"},
}]


def done(stdout="", code=0, stderr=""):
    return subprocess.CompletedProcess([], code, stdout=stdout, stderr=stderr)


class FakeDocker:
    """Responde como un contenedor bench_mongo en PROFILE_C bajo cgroups v2."""

    def __init__(self, running=True, broken=()):
        self.running = running
        self.broken = set(broken)        # archivos del cgroup cuya lectura falla
        self.files = {
            "cpu.max": "100000 100000\r\n",   # \r: docker exec a veces lo añade
            "memory.max": "1073741824",
            "memory.swap.max": "0",
            "cpuset.cpus.effective": "0-7",
            "cpu.stat": "", "memory.stat": "", "memory.peak": "", "memory.events": "",
        }                                # memory.swappiness NO está: es cgroups v2

    def __call__(self, cmd):
        if cmd[:2] == ["docker", "ps"]:
            return done("otro\nbench_mongo\n" if self.running else "otro\n")
        if cmd[:2] == ["docker", "inspect"]:
            return done(json.dumps(INSPECT))
        if cmd[:3] == ["docker", "image", "inspect"]:
            return done(json.dumps([{"RepoDigests": ["mongo@sha256:e0ce"]}]))
        if cmd[:2] == ["docker", "exec"] and cmd[3] in ("cat", "test"):
            name = cmd[-1].removeprefix("/sys/fs/cgroup/")
            if name not in self.files:
                return done(code=1, stderr=f"cat: {cmd[-1]}: No such file or directory")
            if cmd[3] == "cat" and name in self.broken:
                return done(code=126, stderr="OCI runtime exec failed")
            return done(self.files[name])
        if cmd[:2] == ["docker", "exec"] and "mongosh" in cmd:
            return done("wiredTiger\n" if "storageEngine" in cmd[-1] else "8.2.12\n")
        raise AssertionError(f"comando no previsto: {cmd}")


class CaptureEnvTest(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.proc = Path(self.tmp.name)
        (self.proc / "meminfo").write_text(MEMINFO)
        (self.proc / "loadavg").write_text(LOADAVG)
        self.env = {"MONGO_IMAGE": "mongo:8.2", "PG_IMAGE": "postgres:18"}

    def tearDown(self):
        self.tmp.cleanup()

    def capture(self, fake):
        return capture_env.capture("mongo", self.env, runner=fake, proc=self.proc)

    def test_lee_limites_reales_del_cgroup(self):
        data = self.capture(FakeDocker())
        self.assertEqual(data["cgroup"]["limits"], {
            "cpu.max": "100000 100000", "memory.max": "1073741824", "memory.swap.max": "0",
            "cpuset.cpus.effective": "0-7"})
        self.assertEqual(data["errores"], [])

    def test_version_digest_y_perfil(self):
        data = self.capture(FakeDocker())
        self.assertEqual(data["engine"], "mongodb")
        self.assertEqual(data["engine_version"], "8.2.12")
        self.assertEqual(data["storage_engine"], "wiredTiger")
        self.assertEqual(data["image"]["repo_digests"], ["mongo@sha256:e0ce"])
        self.assertEqual(data["profile_label"], "PROFILE_C_SEVERE")

    def test_swappiness_ausente_no_es_error(self):
        data = self.capture(FakeDocker())
        self.assertEqual(data["cgroup"]["memory_swappiness"], {"present": False, "value": None})
        self.assertIsNone(data["docker_inspect"]["MemorySwappiness"])
        self.assertEqual(data["errores"], [])

    def test_archivos_de_metricas(self):
        fake = FakeDocker()
        del fake.files["memory.peak"]
        files = self.capture(fake)["cgroup"]["metric_files"]
        self.assertFalse(files["memory.peak"])
        self.assertTrue(files["cpu.stat"])

    def test_lectura_fallida_queda_null_y_se_registra(self):
        data = self.capture(FakeDocker(broken={"memory.max"}))
        self.assertIsNone(data["cgroup"]["limits"]["memory.max"])
        self.assertTrue(any("memory.max" in e for e in data["errores"]))

    def test_contenedor_parado(self):
        with self.assertRaises(LookupError):
            self.capture(FakeDocker(running=False))

    def test_datos_del_host(self):
        host = self.capture(FakeDocker())["host"]
        self.assertEqual(host["loadavg"]["1m"], 0.42)
        self.assertEqual(host["loadavg"]["raw"], "0.42 0.12 0.17 1/661 9355")
        mem = host["memory"]
        self.assertEqual(mem["MemTotal_kb"], 7507156)
        self.assertEqual(mem["buff_cache_kb"], 10000 + 1400000 + 90000)   # como `free`
        self.assertEqual(mem["swap_used_kb"], 0)

    def test_salida_es_json_serializable(self):
        json.dumps(self.capture(FakeDocker()))


class EnvFileTest(unittest.TestCase):

    def test_comillas_y_comentarios(self):
        with tempfile.NamedTemporaryFile("w", suffix=".env", delete=False) as f:
            f.write('# comentario\nPROFILE_ID=PROFILE_A_BASELINE\nEXPECT_CPU_MAX="400000 100000"\n\n')
        env = capture_env.load_env_file(Path(f.name))
        Path(f.name).unlink()
        self.assertEqual(env, {"PROFILE_ID": "PROFILE_A_BASELINE", "EXPECT_CPU_MAX": "400000 100000"})

    def test_comentario_al_final_de_la_linea(self):
        with tempfile.NamedTemporaryFile("w", suffix=".env", delete=False) as f:
            f.write('A=mongo@sha256:abc  # mongo:8.2\nB="x # no es comentario"  # si\n')
        env = capture_env.load_env_file(Path(f.name))
        Path(f.name).unlink()
        self.assertEqual(env, {"A": "mongo@sha256:abc", "B": "x # no es comentario"})

    def test_images_env_fijado_por_digest(self):
        env = capture_env.load_env_file(ROOT / "docker" / "images.env")
        self.assertRegex(env["MONGO_IMAGE"], r"^mongo@sha256:[0-9a-f]{64}$")
        self.assertRegex(env["PG_IMAGE"], r"^postgres@sha256:[0-9a-f]{64}$")


if __name__ == "__main__":
    unittest.main()
