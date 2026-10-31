"""percentiles.py — P50/P95/P99 de las latencias completadas en la ventana (F5-b).

Método declarado (para el reporte, sección 2): interpolación lineal entre las
muestras ordenadas, `statistics.quantiles(method="inclusive")`. Es la misma que
`numpy.percentile(..., method="linear")`, la de numpy por defecto (tipo 7 de
Hyndman & Fan): para el percentil p con n muestras, h = (n − 1)·p y se
interpola entre x[⌊h⌋] y x[⌊h⌋+1]. P99 por "nearest-rank" daría otro número:
por eso se declara.

Con menos de 2 muestras no hay percentil posible (statistics.quantiles lanza
StatisticsError). Por A4 esto puede pasar en PROFILE_C con concurrencia 50:
aquí NO se lanza nada; se devuelven vacíos y el motivo, y la fila sale con
status=error (ajuste 2 de Alix, docs/F5_RUNNER.md).
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass

from benchmark_runner.config import LOW_DENSITY_SAMPLES, MIN_SAMPLES_FOR_PERCENTILES

METHOD = 'statistics.quantiles(n=100, method="inclusive") = interpolación lineal (numpy "linear")'


@dataclass(frozen=True)
class Percentiles:
    n: int
    p50: float | None
    p95: float | None
    p99: float | None
    low_density: bool          # n < LOW_DENSITY_SAMPLES: se marca en log y reporte (A4)
    reason: str | None         # por qué no hay percentiles, si no los hay

    @property
    def available(self) -> bool:
        return self.p50 is not None


def compute(latencies_ms: list[float]) -> Percentiles:
    n = len(latencies_ms)
    if n < MIN_SAMPLES_FOR_PERCENTILES:
        return Percentiles(n, None, None, None, low_density=True,
                           reason=f"{n} muestra(s) completada(s) en la ventana; se necesitan al menos "
                                  f"{MIN_SAMPLES_FOR_PERCENTILES} para un percentil (A4)")
    cuts = statistics.quantiles(latencies_ms, n=100, method="inclusive")
    # cuts[k-1] es el percentil k.
    return Percentiles(n, cuts[49], cuts[94], cuts[98], low_density=n < LOW_DENSITY_SAMPLES, reason=None)
