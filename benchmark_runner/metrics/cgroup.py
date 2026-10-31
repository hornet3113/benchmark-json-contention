"""cgroup.py — contadores del cgroup del motor, leídos DESDE FUERA del contenedor (F5-a).

Dónde se lee y por qué (medido en F5.4, docs/F5_RUNNER.md):
  - `docker exec … cat` arranca un proceso DENTRO del contenedor: cuesta ~250 ms y
    gasta ~83 ms de CPU del propio motor por lectura. Con PROFILE_C (1 CPU),
    muestrear cada segundo así se comería ~8 % de su cuota: mediríamos la medición.
  - La VM de WSL2 tiene un solo kernel: el cgroup del contenedor está visible en
    /sys/fs/cgroup/docker/<id completo>/ desde la distro Ubuntu. Los valores son
    los mismos que dentro (verificado) y leerlos no consume CPU del motor.

Qué se usa para cada columna del CSV:
  cpu_throttled_seconds = Δ throttled_usec de cpu.stat entre inicio y fin de la ventana ÷ 1e6
  max_rss_mb            = máximo de `anon` de memory.stat muestreado cada 1 s DURANTE la ventana,
                          en MiB (2^20). No se usa memory.peak: incluye caché de archivos y
                          cuenta desde el arranque del contenedor (también el calentamiento).
  OOM                   = Δ oom_kill de memory.events
"""

from __future__ import annotations

import threading
import time
from pathlib import Path

CGROUP_ROOT = Path("/sys/fs/cgroup/docker")


def parse_flat(text: str) -> dict[str, int]:
    """Archivos 'clave valor' de cgroup v2 (cpu.stat, memory.stat, memory.events)."""
    out = {}
    for line in text.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[1].lstrip("-").isdigit():
            out[parts[0]] = int(parts[1])
    return out


class Cgroup:
    def __init__(self, container_id: str, root: Path = CGROUP_ROOT):
        self.path = root / container_id
        if not (self.path / "cpu.stat").exists():
            # Sin acceso desde fuera no se mide: nunca se cae silenciosamente a docker exec.
            raise FileNotFoundError(f"no se ve el cgroup del contenedor en {self.path}")

    def read(self, name: str) -> str:
        return (self.path / name).read_text()

    def flat(self, name: str) -> dict[str, int]:
        return parse_flat(self.read(name))

    def snapshot(self) -> dict:
        cpu = self.flat("cpu.stat")
        events = self.flat("memory.events")
        return {"throttled_usec": cpu.get("throttled_usec"), "nr_throttled": cpu.get("nr_throttled"),
                "nr_periods": cpu.get("nr_periods"), "usage_usec": cpu.get("usage_usec"),
                "oom": events.get("oom"), "oom_kill": events.get("oom_kill"),
                "memory_current": int(self.read("memory.current").strip())}

    def anon_bytes(self) -> int:
        return self.flat("memory.stat")["anon"]


def delta(start: dict, end: dict, key: str) -> int | None:
    if start.get(key) is None or end.get(key) is None:
        return None
    return end[key] - start[key]


class AnonSampler(threading.Thread):
    """Muestrea `anon` cada `interval` segundos hasta stop(). Guarda todas las muestras."""

    def __init__(self, cgroup: Cgroup, interval: float):
        super().__init__(daemon=True)
        self.cgroup, self.interval = cgroup, interval
        self.samples: list[tuple[int, int]] = []     # (monotonic_ns, bytes)
        self.errors: list[str] = []
        self._stop = threading.Event()

    def run(self) -> None:
        while True:
            try:
                self.samples.append((time.monotonic_ns(), self.cgroup.anon_bytes()))
            except OSError as exc:        # el contenedor murió (p. ej. OOM): se registra y se sigue
                self.errors.append(str(exc))
            if self._stop.wait(self.interval):
                break

    def stop(self) -> None:
        self._stop.set()
        self.join(timeout=5)

    @property
    def max_mib(self) -> float | None:
        return max(b for _, b in self.samples) / 2**20 if self.samples else None
