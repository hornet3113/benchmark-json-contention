"""lifecycle.py — preparación de cada repetición: bajar, limpiar caché, levantar, verificar (A5, F5-e).

Orden por repetición (F5-e):
  1. bajar el motor (scripts/down_profile.sh; conserva los volúmenes)
  2. sync + drop_caches con el efecto medido (scripts/flush_caches.sh); si no
     hace efecto, la repetición se ABORTA: no se mide sobre un estado distinto
  3. levantar el motor con el perfil de la celda (scripts/up_profile.sh): el
     reinicio también vacía el caché interno del motor y pone a cero sus
     contadores de cgroup
  4. verificar los límites REALES contra el perfil (capture_env.py): si no
     coinciden, se aborta
Reutiliza los scripts de F1: no hay una segunda forma de levantar un motor.
"""

from __future__ import annotations

import json
import subprocess
import threading
from pathlib import Path

from benchmark_runner.config import PROFILES
from benchmark_runner.env import ROOT, capture_env, load_env

CLI_ENGINE = {"mongodb": "mongo", "postgresql": "postgres"}
CONTAINER = {"mongodb": "bench_mongo", "postgresql": "bench_postgres"}


class RunAborted(RuntimeError):
    """La repetición no se puede medir (caché sin limpiar, límites distintos…). No produce fila."""


def _run(cmd: list[str], what: str, timeout: int = 300) -> subprocess.CompletedProcess:
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if res.returncode != 0:
        raise RunAborted(f"{what} falló (exit {res.returncode}): {(res.stdout + res.stderr).strip()[-400:]}")
    return res


def stop_engines() -> None:
    _run([str(ROOT / "scripts" / "down_profile.sh")], "down_profile.sh")


def flush_caches() -> dict:
    res = subprocess.run([str(ROOT / "scripts" / "flush_caches.sh")], capture_output=True, text=True, timeout=120)
    try:
        out = json.loads(res.stdout.strip().splitlines()[-1])
    except (IndexError, json.JSONDecodeError):
        raise RunAborted(f"flush_caches.sh no devolvió JSON: {res.stdout!r} {res.stderr!r}") from None
    if res.returncode != 0 or not out.get("ok"):
        raise RunAborted(f"limpieza de caché sin efecto: {out}")
    return out


def start_engine(engine: str, profile: str) -> None:
    _run([str(ROOT / "scripts" / "up_profile.sh"), PROFILES[profile], CLI_ENGINE[engine]], "up_profile.sh", timeout=300)


def profile_expectations(profile: str) -> dict:
    ce = capture_env()
    prof = ce.load_env_file(ROOT / "docker" / "profiles" / f"{PROFILES[profile]}.env")
    env = load_env()
    return {"cpu.max": prof["EXPECT_CPU_MAX"], "memory.max": prof["EXPECT_MEMORY_MAX"],
            "memory.swap.max": prof["EXPECT_SWAP_MAX"], "cpuset.cpus.effective": env["EXPECT_CPUSET"]}


def verify_limits(engine: str, profile: str) -> dict:
    """capture_env.py completo + comparación con el perfil. Lanza RunAborted si no coinciden."""
    capture = capture_env().capture(CLI_ENGINE[engine], load_env())
    expected = profile_expectations(profile)
    actual = capture["cgroup"]["limits"]
    mismatched = {k: {"esperado": v, "obtenido": actual.get(k)} for k, v in expected.items() if actual.get(k) != v}
    if capture.get("profile_label") != profile:
        mismatched["profile_label"] = {"esperado": profile, "obtenido": capture.get("profile_label")}
    if mismatched:
        raise RunAborted(f"límites reales distintos del perfil {profile}: {mismatched}")
    return capture


def container_id(engine: str) -> str:
    return _run(["docker", "inspect", "-f", "{{.Id}}", CONTAINER[engine]], "docker inspect").stdout.strip()


def container_state(engine: str) -> dict:
    res = subprocess.run(["docker", "inspect", "-f", "{{json .State}}", CONTAINER[engine]],
                         capture_output=True, text=True, timeout=60)
    if res.returncode != 0:
        return {"error": res.stderr.strip()}
    s = json.loads(res.stdout)
    return {k: s.get(k) for k in ("Status", "Running", "OOMKilled", "ExitCode", "Error")}


def prepare(engine: str, profile: str) -> dict:
    """Pasos 1–4. Devuelve lo que se registra en el archivo crudo de la repetición."""
    stop_engines()
    flush = flush_caches()
    start_engine(engine, profile)
    capture = verify_limits(engine, profile)
    return {"flush": flush, "capture_env": capture, "container_id": container_id(engine)}


# V7, opción 3 (aprobada por Alix el 2026-11-02, docs/V7_SUDOERS.md): ayudante de root
# con una regla NOPASSWD solo para él. Si está instalado, el flush no necesita que haya
# credenciales en caché; si no, se sigue usando `sudo -v` como hasta ahora.
V7_HELPER = "/usr/local/sbin/bench-drop-caches"


def v7_helper_allowed() -> bool:
    """¿Está instalada la regla de V7 para este usuario? `sudo -n -l` NO ejecuta el ayudante."""
    if not Path(V7_HELPER).exists():
        return False
    return subprocess.run(["sudo", "-n", "-l", V7_HELPER], capture_output=True).returncode == 0


def sudo_ready() -> bool:
    """¿Se podrá limpiar la caché sin pedir contraseña? (V7: nunca en mitad de una corrida).

    Vale con credenciales en caché (`sudo -v`) o con la regla de V7 instalada.
    """
    if subprocess.run(["sudo", "-n", "true"], capture_output=True).returncode == 0:
        return True
    return v7_helper_allowed()


class SudoKeepAlive(threading.Thread):
    """Renueva las credenciales de sudo cada 60 s mientras dura la corrida (V7, opción 1 de A5).

    No configura nada permanente. Si la renovación falla, la siguiente limpieza
    de caché fallará y la repetición se abortará: nunca se queda esperando.

    Con la regla de V7 instalada no hay nada que renovar: el hilo no arranca, para no
    acumular fallos de `sudo -n -v` (que con esa regla falla siempre, porque el
    NOPASSWD cubre solo el ayudante).
    """

    def __init__(self, every_s: int = 60):
        super().__init__(daemon=True)
        self.every_s = every_s
        self.failures = 0
        self.innecesario = v7_helper_allowed()
        self._stop = threading.Event()

    def run(self) -> None:
        if self.innecesario:
            return
        while not self._stop.wait(self.every_s):
            if subprocess.run(["sudo", "-n", "-v"], capture_output=True).returncode != 0:
                self.failures += 1

    def stop(self) -> None:
        self._stop.set()
