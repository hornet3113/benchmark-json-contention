"""concurrency.py — ¿cuántos clientes tenían una consulta en vuelo cuando se tomó cada foto del motor? (F5.5b)

Por qué existe: en la repetición de Mongo de F5.5b la foto del motor vio 47 de
50 clientes al inicio de la ventana, mientras las marcas del runner decían
que había 50 consultas en vuelo. Una sola foto por borde, sin su instante
exacto, no distingue entre "el motor no ve al cliente" y "la foto cayó
mientras una respuesta iba de camino". Este módulo cruza CADA foto (con su
intervalo [t0, t1] en el reloj monotónico, el mismo que usan los workers)
con las marcas (inicio, fin, worker) de cada consulta.

Definiciones (fijadas antes de repetir):
  - cliente_seguro: workers con una consulta en vuelo durante TODO [t0, t1]
    según el runner. El motor debería verlos a todos, salvo los que ya
    terminaron en el servidor y aún reciben o decodifican la respuesta.
  - motor: clientes con una consulta activa según la foto del motor.
  - faltan = cliente_seguro − motor.
Un worker cortado al final (no envió "done") tenía una consulta en vuelo
desde que terminó la anterior (el hueco entre consultas es < 1 ms, F5.5b).
"""

from __future__ import annotations

import statistics
import threading
import time
from bisect import bisect_left, bisect_right
from collections.abc import Callable, Iterable

AFTER_PHOTO_NS = 250_000_000   # ventana de "terminan poco después" (solo informativa)


def engine_clients(act: dict | None, engine: str) -> int | None:
    """Clientes con una consulta activa en una foto del motor. None si la foto no lo permite saber."""
    if not act:
        return None
    if engine == "postgresql":
        return act.get("consultas_activas")
    return act.get("clientes_con_consulta_activa")


def in_flight(samples: Iterable[tuple[int, int, int]], unfinished: Iterable[int], t_from: int, t_to: int) -> int:
    """Workers con una consulta en vuelo durante todo [t_from, t_to]. samples: (inicio_ns, fin_ns, worker)."""
    samples = list(samples)
    n = sum(1 for s, e, _ in samples if s <= t_from and e >= t_to)
    last_end: dict[int, int] = {}
    for _, e, w in samples:
        last_end[w] = max(e, last_end.get(w, e))
    # Un worker cortado: su última consulta (sin muestra) empezó al terminar la anterior.
    n += sum(1 for w in set(unfinished) if last_end.get(w, 0) <= t_from)
    return n


def cross(photos: list[dict], samples: list[tuple[int, int, int]], unfinished: list[int], engine: str) -> list[dict]:
    """Una fila por foto con su intervalo: lo que vio el motor frente a lo que tenía en vuelo el runner."""
    ends = sorted(e for _, e, _ in samples)
    out = []
    for p in photos:
        t0, t1 = p["t0_ns"], p["t1_ns"]
        motor, seguro = engine_clients(p, engine), in_flight(samples, unfinished, t0, t1)
        out.append({
            "momento": p.get("momento"), "t0_ns": t0, "duracion_ms": round((t1 - t0) / 1e6, 3),
            "motor": motor, "cliente_seguro": seguro,
            "cliente_en_t0": in_flight(samples, unfinished, t0, t0),
            "faltan": None if motor is None else seguro - motor,
            # Consultas que el runner vio terminar poco después de la foto (posible respuesta en camino).
            "terminan_<=250ms_despues": bisect_right(ends, t1 + AFTER_PHOTO_NS) - bisect_left(ends, t1),
        })
    return out


def summarize(rows: list[dict]) -> dict:
    motor = [r["motor"] for r in rows if r["motor"] is not None]
    faltan = [r["faltan"] for r in rows if r["faltan"] is not None]
    return {"fotos": len(rows), "fotos_validas": len(motor),
            "mediana_motor": statistics.median(motor) if motor else None,
            "min_motor": min(motor) if motor else None,
            "media_faltan": round(statistics.fmean(faltan), 3) if faltan else None,
            "max_faltan": max(faltan) if faltan else None}


class PeriodicReader(threading.Thread):
    """Llama a `read()` cada `interval` s hasta stop(). La primera lectura es a los `interval` s.

    `read()` debe devolver un dict con t0_ns y t1_ns (EngineProbe.timed_activity).
    """

    def __init__(self, read: Callable[[], dict], interval: float):
        super().__init__(daemon=True)
        self.read, self.interval = read, interval
        self.samples: list[dict] = []
        self.errors: list[str] = []
        self._stop = threading.Event()

    def run(self) -> None:
        while not self._stop.wait(self.interval):
            try:
                self.samples.append({"momento": "serie", **self.read()})
            except Exception as exc:  # noqa: BLE001 — una foto fallida se registra; la ventana sigue
                self.errors.append(f"{time.monotonic_ns()}: {type(exc).__name__}: {exc}"[:300])

    def stop(self) -> None:
        self._stop.set()
        self.join(timeout=10)
