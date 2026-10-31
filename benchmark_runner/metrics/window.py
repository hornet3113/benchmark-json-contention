"""window.py — qué consultas cuentan en la ventana de medición (A4) y detección de suspensión (F5-d).

A4 (decidido): solo cuentan las consultas COMPLETADAS dentro de la ventana de
medición. Las que siguen en vuelo al cerrarla se descartan. Las que fallaron
(error o timeout) no son latencias válidas: se cuentan aparte.

Throughput = completadas con éxito dentro de la ventana / duración de la ventana.

Suspensión (F5-d): si la VM de WSL2 se congela, el reloj monotónico se detiene
y el de pared sigue (lo mismo con CLOCK_BOOTTIME). Una divergencia mayor que
el umbral entre el inicio y el fin de la ventana invalida la repetición: se
marca, no se corrige (CLAUDE.md, trampas conocidas).
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from benchmark_runner.config import SUSPEND_DRIFT_THRESHOLD_S


@dataclass(frozen=True)
class Sample:
    """Una consulta ejecutada por un worker. Tiempos en ns del reloj monotónico.

    kind: "ok" | "timeout" (dato censurado por la derecha en el límite) | "error".
    wid: worker que la ejecutó (-1 si no se sabe); sirve para cruzar las fotos del motor (F5.5b).
    """
    start_ns: int
    end_ns: int
    ok: bool
    kind: str = "ok"
    wid: int = -1

    @property
    def latency_ms(self) -> float:
        return (self.end_ns - self.start_ns) / 1e6


@dataclass(frozen=True)
class WindowResult:
    latencies_ms: list[float]
    completed_ok: int
    failed_in_window: int        # timeouts + errores
    started_before_window: int   # completadas en la ventana pero iniciadas en el calentamiento
    duration_s: float
    timeouts_in_window: int = 0
    errors_in_window: int = 0

    @property
    def throughput_qps(self) -> float:
        return self.completed_ok / self.duration_s

    @property
    def timeout_fraction(self) -> float | None:
        """Timeouts / (completadas + timeouts) entre las que TERMINARON en la ventana."""
        n = self.completed_ok + self.timeouts_in_window
        return self.timeouts_in_window / n if n else None


def classify(samples: list[Sample], window_start_ns: int, window_end_ns: int) -> WindowResult:
    """Aplica A4. Una muestra cuenta si TERMINA dentro de [inicio, fin] de la ventana."""
    lat, ok, timeouts, errors, before = [], 0, 0, 0, 0
    for s in samples:
        if not (window_start_ns <= s.end_ns <= window_end_ns):
            continue                    # terminó fuera de la ventana (o seguía en vuelo)
        if not s.ok:
            if s.kind == "timeout":
                timeouts += 1
            else:
                errors += 1
            continue
        ok += 1
        lat.append(s.latency_ms)
        before += s.start_ns < window_start_ns
    return WindowResult(lat, ok, timeouts + errors, before, (window_end_ns - window_start_ns) / 1e9,
                        timeouts, errors)


# --- relojes y suspensión -----------------------------------------------------

@dataclass(frozen=True)
class ClockSnapshot:
    wall_ns: int      # time.time_ns(): avanza aunque la VM esté congelada
    mono_ns: int      # time.monotonic_ns(): se detiene mientras la VM está congelada
    boot_ns: int      # CLOCK_BOOTTIME: cuenta el tiempo suspendido en Linux


def snapshot() -> ClockSnapshot:
    return ClockSnapshot(time.time_ns(), time.monotonic_ns(), time.clock_gettime_ns(time.CLOCK_BOOTTIME))


@dataclass(frozen=True)
class SuspendCheck:
    suspended: bool
    drift_wall_s: float
    drift_boot_s: float
    reason: str | None


def check_suspension(start: ClockSnapshot, end: ClockSnapshot,
                     threshold_s: float = SUSPEND_DRIFT_THRESHOLD_S) -> SuspendCheck:
    mono = (end.mono_ns - start.mono_ns) / 1e9
    drift_wall = (end.wall_ns - start.wall_ns) / 1e9 - mono
    drift_boot = (end.boot_ns - start.boot_ns) / 1e9 - mono
    # Se usa el valor absoluto: un salto del reloj de pared hacia atrás (ajuste
    # NTP grande) también invalida la ventana.
    worst = max(abs(drift_wall), abs(drift_boot))
    suspended = worst > threshold_s
    reason = (f"posible suspensión: el reloj de pared se desvió {drift_wall:+.1f} s y CLOCK_BOOTTIME "
              f"{drift_boot:+.1f} s respecto del monotónico en la ventana (umbral {threshold_s} s)"
              if suspended else None)
    return SuspendCheck(suspended, round(drift_wall, 3), round(drift_boot, 3), reason)
