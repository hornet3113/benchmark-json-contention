"""env.py — acceso al entorno compartido con F1–F3, sin duplicar código.

Reutiliza scripts/capture_env.py, que es el único lugar que lee docker/images.env,
el cgroup y `docker inspect` (CLAUDE.md: "no dupliques esa lógica: impórtalo").
"""

from __future__ import annotations

import importlib.util
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
QUERIES_DIR = ROOT / "queries"


@lru_cache(maxsize=1)
def capture_env():
    spec = importlib.util.spec_from_file_location("capture_env", ROOT / "scripts" / "capture_env.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_env() -> dict[str, str]:
    """Variables de docker/images.env (base de datos, credenciales, cpusets)."""
    return capture_env().load_env_file(ROOT / "docker" / "images.env")
