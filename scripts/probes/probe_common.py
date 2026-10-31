"""probe_common.py — piezas compartidas por las sondas de F6.3.

Las sondas demuestran que el instrumento PUEDE ver throttling, spill y OOM
(PLAN F6, "capacidad de detección"). Para que eso valga, usan exactamente las
piezas del runner, no copias:
  - Cgroup / AnonSampler (benchmark_runner/metrics/cgroup.py): lectura desde fuera;
  - EngineProbe.read (benchmark_runner/runner.py): los detectores de spill de A6;
  - assemble_row (benchmark_runner/runner.py): el clasificador de `status`;
  - lifecycle.container_state: OOMKilled y si el contenedor sigue corriendo.

NINGUNA SONDA ESCRIBE EN EL CSV. La fila que produciría el clasificador se
guarda en results/f6/probes/ bajo "fila_del_clasificador_NO_ES_DEL_CSV", con
query_id = "SONDA_…", que el validador del CSV rechazaría a propósito.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from benchmark_runner import lifecycle  # noqa: E402
from benchmark_runner.matrix import Cell, Run  # noqa: E402
from benchmark_runner.metrics import window  # noqa: E402
from benchmark_runner.metrics.cgroup import AnonSampler, Cgroup  # noqa: E402
from benchmark_runner.runner import assemble_row  # noqa: E402

OUT_DIR = ROOT / "results" / "f6" / "probes"
SHORT = {"postgresql": "postgres", "mongodb": "mongo"}
PROFILE_ID = {"a_baseline": "PROFILE_A_BASELINE", "b_medium": "PROFILE_B_MEDIUM", "c_severe": "PROFILE_C_SEVERE"}


def stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def engine_up(profile: str, engine: str) -> Cgroup:
    """up_profile.sh (baja cualquier otro motor) y devuelve su cgroup, leído desde fuera."""
    res = subprocess.run([str(ROOT / "scripts" / "up_profile.sh"), profile, SHORT[engine]],
                         capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"up_profile.sh falló:\n{res.stdout[-600:]}\n{res.stderr[-600:]}")
    return Cgroup(lifecycle.container_id(engine))


def edge(cg: Cgroup, spill_read=None) -> dict:
    """Mismo orden que el runner: reloj, cgroup y, si hay, contadores de spill."""
    snap = {"clock": window.snapshot(), "cgroup": cg.snapshot()}
    if spill_read is not None:
        snap["spill"] = spill_read()
    return snap


def timed(fn) -> window.Sample:
    t0 = time.monotonic_ns()
    try:
        fn()
        return window.Sample(t0, time.monotonic_ns(), True, "ok")
    except Exception:  # noqa: BLE001 — una consulta fallida es un dato, como en el runner
        return window.Sample(t0, time.monotonic_ns(), False, "error")


def classify(engine: str, profile: str, label: str, start: dict, end: dict, samples: list,
             sampler: AnonSampler, spill_observed: bool) -> tuple[dict, list[str], dict]:
    """Fila que produciría el clasificador del runner con estas observaciones. NO se escribe en el CSV."""
    cell = Cell(engine=engine, profile=PROFILE_ID[profile], query_id=f"SONDA_{label}", query="-",
                options=(), concurrency=1)
    kinds: dict[str, int] = {}
    for s in samples:
        kinds[s.kind] = kinds.get(s.kind, 0) + 1
    load = SimpleNamespace(samples=samples, window_start_ns=start["clock"].mono_ns,
                           window_end_ns=end["clock"].mono_ns, kinds=kinds)
    state = lifecycle.container_state(engine)
    row, reasons, _ = assemble_row(Run(cell, 1), load=load, start=start, end=end, max_rss_mib=sampler.max_mib,
                                   spill_observed=spill_observed, oom_killed_flag=bool(state.get("OOMKilled")),
                                   container_running=bool(state.get("Running")))
    return row, reasons, state


def save(name: str, data: dict) -> Path:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    dest = OUT_DIR / f"{name}.json"
    dest.write_text(json.dumps(data, ensure_ascii=False, indent=1, default=str) + "\n")
    return dest
