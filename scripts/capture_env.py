#!/usr/bin/env python3
"""capture_env.py — fotografía del entorno de un motor en marcha (R-28, diapo 5/13).

Uso:
    python3 scripts/capture_env.py --engine mongo|postgres [--out ARCHIVO.json]

Emite un JSON con:
    - versión real del motor y motor de almacenamiento
    - etiqueta, id y digest de la imagen
    - límites REALES del cgroup v2, leídos DENTRO del contenedor
    - lo que Docker cree haber aplicado (docker inspect)
    - datos del host: loadavg, memoria y swap de la VM, kernel, CPUs

Es el ÚNICO lugar del proyecto que lee estas fuentes. verify_limits.sh lo
llama y solo compara contra los valores esperados del perfil; el runner de F5
lo importará para dejar el entorno registrado en cada corrida. Así, si cambia
la forma de leer un dato, cambia en un solo sitio.

Nunca inventa un valor: si una lectura falla, el campo queda en null y el
motivo va a la lista "errores". Un null que llega a verify_limits.sh cuenta
como discrepancia, no como acierto.

Solo usa la biblioteca estándar, para poder correr sin entorno virtual.

Códigos de salida: 0 captura hecha · 2 contenedor no corriendo o uso incorrecto.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parent.parent
SCHEMA = "capture_env/1"

ENGINES = {
    # motor CLI -> (contenedor, variable de imagen en images.env, nombre en el CSV)
    "mongo": ("bench_mongo", "MONGO_IMAGE", "mongodb"),
    "postgres": ("bench_postgres", "PG_IMAGE", "postgresql"),
}

# Límites que se comparan contra el perfil (PLAN F1).
# cpuset.cpus.effective: las CPUs que el kernel aplica de verdad (F5-c).
LIMIT_FILES = ("cpu.max", "memory.max", "memory.swap.max", "cpuset.cpus.effective")
# Archivos de los que saldrán las columnas del CSV (SPEC §4).
METRIC_FILES = ("cpu.stat", "memory.stat", "memory.peak", "memory.events", "memory.swap.max")
# Control de cgroups v1; en v2 no existe (SPEC A7, V8). Se registra, no se exige.
SWAPPINESS_FILE = "memory.swappiness"

# Campos de /proc/meminfo que se publican, en kB tal como los da el kernel.
MEMINFO_KEYS = ("MemTotal", "MemFree", "MemAvailable", "Buffers", "Cached",
                "SReclaimable", "SwapTotal", "SwapFree")

Runner = Callable[[list[str]], "subprocess.CompletedProcess[str]"]


def run(cmd: list[str]) -> "subprocess.CompletedProcess[str]":
    """Ejecuta un comando sin lanzar excepción; el llamador mira returncode."""
    return subprocess.run(cmd, capture_output=True, text=True, timeout=60)


class Capture:
    """Acumula lecturas y errores. `runner` se sustituye en las pruebas."""

    def __init__(self, runner: Runner = run):
        self.runner = runner
        self.errors: list[str] = []

    def cmd(self, cmd: list[str], what: str) -> str | None:
        try:
            res = self.runner(cmd)
        except (OSError, subprocess.TimeoutExpired) as exc:
            self.errors.append(f"{what}: {exc}")
            return None
        if res.returncode != 0:
            detail = (res.stderr or res.stdout or "").strip().splitlines()
            self.errors.append(f"{what}: exit={res.returncode} {detail[-1] if detail else ''}".rstrip())
            return None
        return res.stdout.replace("\r", "").strip()

    # --- contenedor ---------------------------------------------------------

    def is_running(self, container: str) -> bool:
        out = self.cmd(["docker", "ps", "--format", "{{.Names}}"], "docker ps")
        return out is not None and container in out.splitlines()

    def cgroup_read(self, container: str, name: str) -> str | None:
        return self.cmd(["docker", "exec", container, "cat", f"/sys/fs/cgroup/{name}"],
                        f"cgroup {name}")

    def cgroup_exists(self, container: str, name: str) -> bool:
        # "test -e" sale con 1 si no existe: es una respuesta, no un error.
        try:
            res = self.runner(["docker", "exec", container, "test", "-e", f"/sys/fs/cgroup/{name}"])
        except (OSError, subprocess.TimeoutExpired) as exc:
            self.errors.append(f"test {name}: {exc}")
            return False
        return res.returncode == 0

    def inspect(self, target: list[str], what: str) -> dict | None:
        out = self.cmd(["docker", *target], what)
        if out is None:
            return None
        try:
            data = json.loads(out)
        except json.JSONDecodeError as exc:
            self.errors.append(f"{what}: JSON inválido ({exc})")
            return None
        return data[0] if isinstance(data, list) and data else None

    def engine_version(self, engine: str, container: str, env: dict[str, str]) -> tuple[str | None, str | None]:
        if engine == "mongo":
            version = self.cmd(["docker", "exec", container, "mongosh", "--quiet", "--eval", "db.version()"],
                               "version mongo")
            storage = self.cmd(["docker", "exec", container, "mongosh", "--quiet", "--eval",
                                "db.serverStatus().storageEngine.name"], "storage engine mongo")
            return version, storage
        version = self.cmd(["docker", "exec", container, "psql", "-U", env.get("POSTGRES_USER", ""),
                            "-d", env.get("POSTGRES_DB", ""), "-tAc", "SHOW server_version"],
                           "version postgres")
        return version, "n/a"


# --- host (la VM de WSL2) ---------------------------------------------------

def parse_loadavg(text: str) -> dict:
    """'/proc/loadavg' -> 1, 5 y 15 min más el texto crudo."""
    parts = text.split()
    return {"raw": text.strip(), "1m": float(parts[0]), "5m": float(parts[1]), "15m": float(parts[2])}


def parse_meminfo(text: str) -> dict:
    """'/proc/meminfo' -> campos de MEMINFO_KEYS en kB, más buff/cache y swap usado.

    buff/cache se calcula igual que `free`: Buffers + Cached + SReclaimable.
    """
    values: dict[str, int] = {}
    for line in text.splitlines():
        key, _, rest = line.partition(":")
        if key in MEMINFO_KEYS:
            values[key] = int(rest.split()[0])
    out = {f"{k}_kb": values.get(k) for k in MEMINFO_KEYS}
    if all(k in values for k in ("Buffers", "Cached", "SReclaimable")):
        out["buff_cache_kb"] = values["Buffers"] + values["Cached"] + values["SReclaimable"]
    if "SwapTotal" in values and "SwapFree" in values:
        out["swap_used_kb"] = values["SwapTotal"] - values["SwapFree"]
    return out


def host_info(proc: Path = Path("/proc")) -> dict:
    return {
        "kernel": platform.release(),
        "nproc": os.cpu_count(),
        "loadavg": parse_loadavg((proc / "loadavg").read_text()),
        "memory": parse_meminfo((proc / "meminfo").read_text()),
    }


# --- utilidades -------------------------------------------------------------

def load_env_file(path: Path) -> dict[str, str]:
    """Lee un .env simple (CLAVE=valor, comentarios con #), como `source` en Bash.

    Igual que Bash: un valor entre comillas se toma entero; uno sin comillas
    termina donde empieza un comentario (espacio seguido de #).
    """
    env: dict[str, str] = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.strip()
        if value[:1] in ('"', "'") and value[0] in value[1:]:
            value = value[1:value.index(value[0], 1)]
        else:
            value = value.split(" #")[0].split("\t#")[0].strip()
        env[key.strip()] = value
    return env


def capture(engine: str, env: dict[str, str], runner: Runner = run,
            proc: Path = Path("/proc")) -> dict:
    """Construye el JSON completo. Lanza LookupError si el contenedor no corre."""
    container, image_var, engine_name = ENGINES[engine]
    cap = Capture(runner)
    if not cap.is_running(container):
        raise LookupError(f"el contenedor {container} no está corriendo")

    image_tag = env.get(image_var)
    insp = cap.inspect(["inspect", container], "docker inspect") or {}
    host_cfg = insp.get("HostConfig", {})
    img = cap.inspect(["image", "inspect", image_tag], "docker image inspect") if image_tag else None
    version, storage = cap.engine_version(engine, container, env)

    swappiness_present = cap.cgroup_exists(container, SWAPPINESS_FILE)

    return {
        "schema": SCHEMA,
        "captured_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "engine": engine_name,
        "container": container,
        "profile_label": insp.get("Config", {}).get("Labels", {}).get("bench.profile"),
        "image": {
            "tag": image_tag,
            "id": insp.get("Image"),
            "repo_digests": (img or {}).get("RepoDigests"),
        },
        "engine_version": version,
        "storage_engine": storage,
        "cgroup": {
            "limits": {name: cap.cgroup_read(container, name) for name in LIMIT_FILES},
            "metric_files": {name: cap.cgroup_exists(container, name) for name in METRIC_FILES},
            "memory_swappiness": {
                "present": swappiness_present,
                "value": cap.cgroup_read(container, SWAPPINESS_FILE) if swappiness_present else None,
            },
        },
        "docker_inspect": {
            "NanoCpus": host_cfg.get("NanoCpus"),
            "CpuQuota": host_cfg.get("CpuQuota"),
            "CpuPeriod": host_cfg.get("CpuPeriod"),
            "Memory": host_cfg.get("Memory"),
            "MemorySwap": host_cfg.get("MemorySwap"),
            "MemorySwappiness": host_cfg.get("MemorySwappiness"),
            "CpusetCpus": host_cfg.get("CpusetCpus"),
            "OOMKilled": insp.get("State", {}).get("OOMKilled"),
        },
        "host": host_info(proc),
        "errores": cap.errors,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--engine", required=True, choices=sorted(ENGINES))
    parser.add_argument("--out", type=Path, help="archivo JSON de salida (por defecto, stdout)")
    args = parser.parse_args(argv)

    env = load_env_file(ROOT / "docker" / "images.env")
    try:
        data = capture(args.engine, env)
    except LookupError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    text = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    if args.out:
        args.out.write_text(text)
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
