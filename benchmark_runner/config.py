"""config.py — parámetros del protocolo (playbook.pdf §3 y §6; docs/F5_RUNNER.md).

Todo lo que define CÓMO se mide vive aquí con nombre, para que el reporte
(sección 2) pueda citarlo. Cambiar un valor cambia el experimento.
"""

from __future__ import annotations

from dataclasses import dataclass

from benchmark_runner import csv_writer as schema

# --- ventanas (playbook.pdf §6, p.3) ----------------------------------------


@dataclass(frozen=True)
class Windows:
    warmup_s: int
    measure_s: int
    cooldown_s: int


WINDOWS = Windows(warmup_s=60, measure_s=300, cooldown_s=60)
# --smoke (PLAN F5): solo para comprobar que el circuito funciona. Sus filas
# van a results/smoke/ y NO son resultados (F5-g).
SMOKE_WINDOWS = Windows(warmup_s=5, measure_s=20, cooldown_s=5)

# Dominios del CSV: se toman del esquema, que es la única fuente (R-26).
CONCURRENCIES = schema.CONCURRENCIES   # §6: 1, 10, 50
REPETITIONS = schema.RUN_NUMBERS       # §6: 3 por escenario
ENGINES = schema.ENGINES

# --- perfiles (playbook.pdf §3): id literal del CSV → archivo docker/profiles/*.env
PROFILES = {
    "PROFILE_A_BASELINE": "a_baseline",
    "PROFILE_B_MEDIUM": "b_medium",
    "PROFILE_C_SEVERE": "c_severe",
}
assert tuple(PROFILES) == schema.PROFILES, "perfiles de config distintos a los del esquema del CSV"

# --- límites por query (A4, F5-f) -------------------------------------------
QUERY_TIMEOUT_S = 300

# --- política de muestras (A4, F5-b) ----------------------------------------
# Con menos de MIN_SAMPLES_FOR_PERCENTILES no se pueden calcular percentiles
# (statistics.quantiles lo exige): la fila sale con status=error.
MIN_SAMPLES_FOR_PERCENTILES = 2
# Por debajo de esto la celda se marca "baja densidad muestral" en el log y en
# el reporte (el CSV no tiene columna para ello).
LOW_DENSITY_SAMPLES = 20

# --- censura por la derecha (decisión de Alix, 2026-11-01; SPEC A4) ----------
# Una consulta que llega al límite de 300 s es un dato CENSURADO por la derecha:
# se sabe que habría tardado ≥ 300 s, no cuánto. Con una fracción f de
# timeouts entre las consultas que terminaron en la ventana, el percentil p
# solo es válido si f < 1 − p (el percentil cae fuera de la zona censurada).
# Con f ≥ 1 % el P99 ya no vale: la fila sale status=error.
CENSORED_ERROR_FRACTION = 0.01
PERCENTILE_VALID_BELOW = {"p50": 0.50, "p95": 0.05, "p99": 0.01}

# --- detección de suspensión (F5-d) -----------------------------------------
# Si el reloj de pared o CLOCK_BOOTTIME avanzan más que el monotónico por
# encima de esto durante la ventana, la VM se congeló: la repetición no vale.
SUSPEND_DRIFT_THRESHOLD_S = 2.0

# --- muestreo de memoria (F5-a) ---------------------------------------------
RSS_SAMPLE_INTERVAL_S = 1.0
