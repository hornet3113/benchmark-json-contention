"""fake.py — motor FALSO, solo para probar el runner sin contenedores (F5.4).

Nunca produce filas de results/: el runner lo rechaza fuera de las pruebas.
Simula una query que tarda `delay_s` y, opcionalmente, falla cada `fail_every`
ejecuciones o se pasa del límite cada `timeout_every`.
"""

from __future__ import annotations

import time

from benchmark_runner.engines.base import QueryFailed, QueryTimeout


class FakeEngine:
    engine = "fake"

    def __init__(self, cell, *, delay_s: float = 0.01, fail_every: int = 0, timeout_every: int = 0,
                 fail_connect: bool = False, **_):
        self.cell, self.delay_s = cell, delay_s
        self.fail_every, self.timeout_every, self.fail_connect = fail_every, timeout_every, fail_connect
        self.n = 0

    def connect(self) -> None:
        if self.fail_connect:
            raise ConnectionError("conexión rechazada (simulada)")

    def close(self) -> None:
        pass

    def execute(self) -> int:
        self.n += 1
        time.sleep(self.delay_s)
        if self.timeout_every and self.n % self.timeout_every == 0:
            raise QueryTimeout("límite de tiempo (simulado)")
        if self.fail_every and self.n % self.fail_every == 0:
            raise QueryFailed("error (simulado)")
        return 1
