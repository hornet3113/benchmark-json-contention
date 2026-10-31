"""runner.py — una repetición completa: preparar, cargar, medir, escribir la fila (F5.4).

  prepare()  →  run_load() con ganchos en los bordes de la ventana  →  assemble_row()  →  CSV + crudo

Reglas de la fila (assemble_row, función pura para poder probarla):
  throughput_qps         completadas con éxito en la ventana / segundos de la ventana (A4)
  latency_p50/p95/p99_ms percentiles de esas completadas; vacíos si hay < 2 (F5-b, ajuste 2)
  cpu_throttled_seconds  Δ throttled_usec del cgroup en la ventana ÷ 1e6
  max_rss_mb             máximo de `anon` muestreado cada 1 s en la ventana, en MiB
  (si una lectura no existe, la columna va VACÍA y la fila es error u oom; nunca 0)
  disk_spill             lo observado en la ventana: Δ temp_bytes (Postgres) / Δ contadores spill (Mongo)
  status                 oom > error > spill > ok (SPEC §4), con estos motivos:
      oom   : Δ oom_kill > 0, o Docker marca OOMKilled
      error : < 2 completadas · suspensión detectada · algún error de query (no timeout)
              · el contenedor dejó de correr · faltan datos de cgroup
              · fracción de timeouts ≥ 1 % (datos censurados: el P99 ya no es válido)
      spill : disk_spill y nada de lo anterior
Censura por la derecha (decisión de Alix, SPEC A4): un timeout es una latencia ≥ 300 s
de valor desconocido. Con una fracción f de timeouts entre las que terminaron en la
ventana, el percentil p solo vale si f < 1 − p. La fracción exacta y la validez de
cada percentil van al crudo, para que el reporte lo diga por celda. Las latencias del
CSV se calculan sobre las completadas y no se corrigen. Ningún valor se inventa.
"""

from __future__ import annotations

import json
import os
import platform
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from benchmark_runner import csv_writer
from benchmark_runner.config import (CENSORED_ERROR_FRACTION, PERCENTILE_VALID_BELOW, QUERY_TIMEOUT_S,
                                     RSS_SAMPLE_INTERVAL_S)
from benchmark_runner.matrix import Run
from benchmark_runner.metrics import percentiles, window
from benchmark_runner.metrics.cgroup import AnonSampler, Cgroup, delta
from benchmark_runner.metrics.concurrency import PeriodicReader


def censoring(w) -> dict:
    """Fracción de timeouts (datos censurados por la derecha) y validez de cada percentil."""
    f = w.timeout_fraction
    return {"timeouts_en_ventana": w.timeouts_in_window, "completadas_en_ventana": w.completed_ok,
            "errores_en_ventana": w.errors_in_window, "fraccion_timeouts": f,
            "limite_s": QUERY_TIMEOUT_S,
            "percentil_valido": {k: (f is not None and f < lim) for k, lim in PERCENTILE_VALID_BELOW.items()},
            "regla": "datos censurados por la derecha en el límite; el percentil p vale si fraccion_timeouts < 1 − p"}


def assemble_row(run: Run, *, load, start: dict, end: dict, max_rss_mib: float | None,
                 spill_observed: bool, oom_killed_flag: bool,
                 container_running: bool) -> tuple[dict, list[str], dict]:
    """Fila del CSV + motivos (para el log) + censura (para el crudo). No lanza: lo que falta se marca."""
    cell = run.cell
    reasons: list[str] = []
    w = window.classify(load.samples, load.window_start_ns, load.window_end_ns)
    p = percentiles.compute(w.latencies_ms)
    if not p.available:
        reasons.append(p.reason)
    elif p.low_density:
        reasons.append(f"baja densidad muestral: {p.n} completadas en la ventana (A4)")

    susp = window.check_suspension(start["clock"], end["clock"])
    if susp.suspended:
        reasons.append(susp.reason)
    if w.failed_in_window:
        reasons.append(f"{w.failed_in_window} consulta(s) fallidas o con timeout dentro de la ventana")
    cens = censoring(w)
    censored = cens["fraccion_timeouts"] is not None and cens["fraccion_timeouts"] >= CENSORED_ERROR_FRACTION
    if censored:
        valid = [k for k, v in cens["percentil_valido"].items() if v] or ["ninguno"]
        reasons.append(f"datos censurados por la derecha: {cens['fraccion_timeouts']:.1%} de timeouts a "
                       f"{QUERY_TIMEOUT_S} s (≥ {CENSORED_ERROR_FRACTION:.0%}); percentiles válidos: {', '.join(valid)}")
    errors = load.kinds.get("error", 0)
    if errors:
        reasons.append(f"{errors} consulta(s) con error (no timeout) en toda la repetición")

    throttled = delta(start["cgroup"], end["cgroup"], "throttled_usec")
    oom_kills = delta(start["cgroup"], end["cgroup"], "oom_kill") or 0
    missing = throttled is None or max_rss_mib is None
    if missing:
        reasons.append("faltan lecturas del cgroup (contenedor caído o inaccesible)")
    if not container_running:
        reasons.append("el contenedor no seguía corriendo al terminar")
    oom = oom_kills > 0 or oom_killed_flag
    if oom:
        reasons.append(f"OOM: oom_kill +{oom_kills}, OOMKilled={oom_killed_flag}")

    is_error = (not p.available) or susp.suspended or errors > 0 or missing or not container_running or censored
    status = csv_writer.resolve_status(oom=oom, error=is_error, spill=spill_observed)
    row = {
        "timestamp_epoch": start["clock"].wall_ns // 1_000_000_000,
        "engine": cell.engine, "profile": cell.profile, "query_id": cell.query_id,
        "concurrency": cell.concurrency, "run_number": run.run_number,
        "throughput_qps": w.throughput_qps,
        "latency_p50_ms": p.p50, "latency_p95_ms": p.p95, "latency_p99_ms": p.p99,
        # Sin lectura → vacío (y la fila es error u oom). Nunca 0: sería un dato inventado.
        "cpu_throttled_seconds": None if throttled is None else throttled / 1e6,
        "max_rss_mb": max_rss_mib,
        "disk_spill": spill_observed, "status": status,
    }
    return row, reasons, cens


# --- la repetición real ------------------------------------------------------

# Conexiones y consultas que el MOTOR ve en los bordes de la ventana (comprobación de
# Alix, F5.5): con c workers deben verse c clientes y c consultas activas. En
# Postgres también los workers paralelos activos: bajo carga se agotan
# (max_parallel_workers), y por eso el plan de c=1 no es el de c=50.
PG_ACTIVITY_SQL = """SELECT
    count(*) FILTER (WHERE backend_type = 'client backend' AND pid <> pg_backend_pid()) AS clientes,
    count(*) FILTER (WHERE backend_type = 'client backend' AND state = 'active' AND pid <> pg_backend_pid()) AS consultas_activas,
    count(*) FILTER (WHERE backend_type = 'parallel worker') AS workers_paralelos,
    current_setting('max_parallel_workers')::int AS max_parallel_workers
  FROM pg_stat_activity WHERE datname = current_database()"""


def mongo_activity(admin, db_name: str) -> dict:
    """Consultas que Mongo ejecuta sobre <db>.orders en este instante.

    El filtro de currentOp va como CAMPOS DEL COMANDO ({currentOp: 1, active: true,
    ns: ...}). Pasarlo como valor (command("currentOp", {...})) hace que el
    servidor lo ignore y devuelva todo: pasó en F5.5 y contó también los `hello`
    de los monitores del driver.

    Las conexiones de serverStatus incluyen, por cada MongoClient, la de trabajo
    más 2 de monitoreo de pymongo (streaming y RTT): con 50 workers, ~150. Por
    eso la concurrencia real se mide con las consultas activas, no con las conexiones.

    Una consulta de Q2 devuelve 1000 documentos: el `aggregate` entrega el primer
    lote y el resto llega con `getMore` sobre el mismo cursor. Un cliente en
    `getMore` sigue ejecutando su consulta, así que también cuenta (F5.5b).

    t0_ns / t1_ns encierran SOLO la llamada a currentOp (reloj monotónico, el
    mismo de los workers): es el intervalo en que se tomó la foto (F5.5b).
    """
    conns = admin.command("serverStatus")["connections"]
    t0 = time.monotonic_ns()
    ops = admin.command("currentOp", 1, active=True, ns=f"{db_name}.orders")["inprog"]
    t1 = time.monotonic_ns()
    aggs = [o for o in ops if "aggregate" in (o.get("command") or {})]
    gms = [o for o in ops if "getMore" in (o.get("command") or {})]
    return {"t0_ns": t0, "t1_ns": t1, "consultas_activas": len(aggs), "getmore_activos": len(gms),
            "clientes_con_consulta_activa": len({o.get("client") for o in aggs + gms}),
            "conexiones_actuales": conns.get("current"), "conexiones_activas": conns.get("active")}


class EngineProbe:
    """Lecturas del motor en los bordes de la ventana, por una conexión aparte de los workers.

    Desde F5.5b también la usa la serie de fotos (PeriodicReader) desde otro
    hilo: el candado impide que dos lecturas compartan la conexión a la vez.
    """

    def __init__(self, engine: str, env: dict):
        self.engine, self.env = engine, env
        self.lock = threading.Lock()
        if engine == "postgresql":
            import psycopg
            self.conn = psycopg.connect(host="127.0.0.1", port=5432, dbname=env["POSTGRES_DB"],
                                        user=env["POSTGRES_USER"], password=env["POSTGRES_PASSWORD"], autocommit=True)
        else:
            from pymongo import MongoClient
            self.client = MongoClient("mongodb://127.0.0.1:27017", maxPoolSize=1)

    def read(self) -> dict:
        from benchmark_runner.metrics import spill
        with self.lock:
            if self.engine == "postgresql":
                return spill.pg_temp_counters(self.conn)
            return spill.mongo_spill_counters(self.client.admin.command("serverStatus"))

    def activity(self) -> dict:
        """Foto de la actividad del motor con su intervalo t0_ns / t1_ns (F5.5b)."""
        with self.lock:
            if self.engine == "postgresql":
                cols = ("clientes", "consultas_activas", "workers_paralelos", "max_parallel_workers")
                t0 = time.monotonic_ns()
                vals = self.conn.execute(PG_ACTIVITY_SQL).fetchone()
                t1 = time.monotonic_ns()
                return {"t0_ns": t0, "t1_ns": t1, **dict(zip(cols, vals))}
            return mongo_activity(self.client.admin, self.env["MONGO_DB"])

    def close(self) -> None:
        (self.conn if self.engine == "postgresql" else self.client).close()


def run_one(run: Run, *, windows, csv_path: Path, raw_dir: Path, explain_dir: Path | None,
            header_spaces: bool = False, matrix: int = 54, cpus=None, grace_s: float = 15.0,
            processes: int | None = None, activity_every_s: float | None = None) -> dict:
    from benchmark_runner import lifecycle
    from benchmark_runner.env import load_env
    from benchmark_runner.metrics import spill
    from benchmark_runner.workload import build_engine, run_load

    cell = run.cell
    started = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    prep = lifecycle.prepare(cell.engine, cell.profile)          # puede lanzar RunAborted
    cg = Cgroup(prep["container_id"])
    env = load_env()
    probe = EngineProbe(cell.engine, env)
    sampler = AnonSampler(cg, RSS_SAMPLE_INTERVAL_S)
    # Fotos de la actividad del motor DENTRO de la ventana (F5.5b), además de las de los bordes.
    series = PeriodicReader(probe.activity, activity_every_s) if activity_every_s else None

    def edge() -> dict:
        # El reloj primero: es lo que marca el borde. Después el cgroup (lectura de
        # archivos del host, microsegundos: es columna del CSV) y enseguida la foto
        # de actividad, que lleva su propio intervalo; el spill al final (F5.5b).
        # Una lectura que falla (el contenedor murió) se registra y la repetición
        # sigue: assemble_row la marca.
        snap = {"clock": window.snapshot(), "errores": []}
        for name, read in (("cgroup", cg.snapshot), ("actividad", probe.activity), ("spill", probe.read)):
            try:
                snap[name] = read()
            except Exception as exc:  # noqa: BLE001
                snap[name] = {}
                snap["errores"].append(f"{name}: {type(exc).__name__}: {exc}"[:300])
        return snap

    def on_start():
        snap = edge()
        sampler.start()
        if series:
            series.start()
        return snap

    def on_end():
        snap = edge()
        sampler.stop()
        if series:
            series.stop()
        return snap

    load = run_load(cell, windows, ("real", {}), concurrency=cell.concurrency, timeout_s=QUERY_TIMEOUT_S,
                    on_window_start=on_start, on_window_end=on_end, grace_s=grace_s, cpus=cpus,
                    processes=processes)
    state = lifecycle.container_state(cell.engine)
    spill_delta = spill.counter_delta(load.start_hook["spill"], load.end_hook["spill"])

    plan_file, plan_error = None, None
    if explain_dir is not None and run.run_number == 1 and cell.concurrency == 1 and state.get("Running"):
        # R-31: un plan por motor × query × perfil, FUERA de la ventana, y solo en la
        # celda de concurrencia 1 (decisión de Alix, F5.5): con c > 1 quedan consultas
        # huérfanas en el servidor al cortar los workers y el plan saldría distorsionado.
        # OJO para el reporte: el plan de c=1 NO es el que se ejecuta con c=50, porque
        # los workers paralelos de Postgres se agotan bajo carga (ver "actividad").
        try:
            with build_engine(("real", {}), cell, QUERY_TIMEOUT_S) as e:
                plan = e.explain()
            explain_dir.mkdir(parents=True, exist_ok=True)
            plan_file = explain_dir / f"{cell.cell_id}.json"
            plan_file.write_text(json.dumps(plan, ensure_ascii=False, indent=2, default=str) + "\n")
        except Exception as exc:  # noqa: BLE001 — un plan fallido no invalida la medición
            plan_error = f"{type(exc).__name__}: {exc}"[:400]
    probe.close()

    row, reasons, cens = assemble_row(run, load=load, start=load.start_hook, end=load.end_hook,
                                max_rss_mib=sampler.max_mib, spill_observed=bool(spill_delta),
                                oom_killed_flag=bool(state.get("OOMKilled")),
                                container_running=bool(state.get("Running")))
    csv_writer.CsvWriter(csv_path, header_spaces=header_spaces, matrix=matrix).write(row)

    raw = {
        "run_id": run.run_id, "inicio_utc": started, "fila_csv": row, "motivos": reasons,
        "ventanas_s": vars(windows), "concurrencia": cell.concurrency, "opciones": dict(cell.options),
        "preparacion": {"flush": prep["flush"], "container_id": prep["container_id"],
                        "limites": prep["capture_env"]["cgroup"]["limits"],
                        "engine_version": prep["capture_env"]["engine_version"],
                        "image": prep["capture_env"]["image"], "host_antes": prep["capture_env"]["host"]},
        "ventana_ns": {"inicio": load.window_start_ns, "fin": load.window_end_ns},
        "relojes": {"inicio": vars(load.start_hook["clock"]), "fin": vars(load.end_hook["clock"])},
        "errores_de_lectura": {"inicio": load.start_hook["errores"], "fin": load.end_hook["errores"]},
        "cgroup": {"inicio": load.start_hook["cgroup"], "fin": load.end_hook["cgroup"]},
        "spill": {"inicio": load.start_hook["spill"], "fin": load.end_hook["spill"], "delta": spill_delta},
        "memoria_anon": {"muestras": len(sampler.samples), "max_mib": sampler.max_mib, "errores": sampler.errors[:5]},
        "censura": cens,
        "actividad_del_motor": {"inicio": load.start_hook.get("actividad"), "fin": load.end_hook.get("actividad"),
                                "serie_cada_s": activity_every_s,
                                "serie": series.samples if series else None,
                                "serie_errores": series.errors[:5] if series else None},
        "procesos_x_hilos": [load.processes, load.threads_per_process],
        "consultas": {"por_tipo": load.kinds, "ejemplos_de_error": load.error_examples,
                      "por_worker": load.per_worker, "workers_terminados_al_final": load.workers_terminated,
                      "workers_sin_terminar": load.unfinished_workers},
        "estado_contenedor_final": state, "plan": str(plan_file) if plan_file else None, "plan_error": plan_error,
        "runner": {"python": platform.python_version(), "pid": os.getpid(),
                   "cpus": sorted(os.sched_getaffinity(0))},
        # Muestras crudas: permiten recalcular percentiles con otro método (SPEC §7).
        # [inicio_ns, fin_ns, ok, worker]; el worker se añadió en F5.5b para cruzar las fotos del motor.
        "muestras": [[s.start_ns, s.end_ns, int(s.ok), s.wid] for s in load.samples],
    }
    raw_dir.mkdir(parents=True, exist_ok=True)
    (raw_dir / f"{run.run_id}.json").write_text(json.dumps(raw, ensure_ascii=False, default=str) + "\n")
    return {"row": row, "reasons": reasons, "raw": str(raw_dir / f"{run.run_id}.json"), "wall_s": load.wall_s}
