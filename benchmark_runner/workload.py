"""workload.py — bucle cerrado con N procesos y ventanas de calentamiento / medición / enfriamiento (F5.4).

Cómo funciona una repetición (playbook.pdf §6; SPEC §2):

  1. La concurrencia c se reparte en P procesos (`spawn`) × T hilos (decisión
     de Alix, F5.5): cada HILO es un worker independiente con SU PROPIA
     conexión, así que el motor ve c clientes simultáneos igual que con c
     procesos. Lo que cambia es la memoria del runner: con 50 procesos ocupaba
     ~2 GB y la VM entraba en swap (F5.5, hallazgo 2). Por defecto
     P = min(c, 10) y T = c / P → 1×1, 10×1, 10×5. Los drivers liberan el GIL
     mientras esperan la red; la comparación 50×1 frente a 10×5 lo comprueba.
  2. Cada worker conecta y avisa "listo". Solo cuando están TODOS listos el
     principal fija un instante de arranque común: la ventana no empieza con
     la mitad de los workers todavía conectándose.
  3. Bucle cerrado sin pausa entre consultas: cada worker ejecuta la query,
     anota (inicio, fin, resultado) con el reloj monotónico, que es el mismo
     para todos los procesos en Linux, y la envía al principal AL TERMINARLA.
     Así, si al final hay que cortar un worker atascado, solo se pierde la
     consulta en vuelo, que de todas formas acaba fuera de la ventana (A4).
  4. El principal ejecuta los ganchos `window_start` y `window_end` en los
     instantes exactos de inicio y fin de la ventana de medición (relojes,
     cgroup, contadores de spill, muestreo de memoria).
  5. Al terminar el enfriamiento los workers dejan de lanzar consultas. Los
     que siguen en vuelo tienen `grace_s` para acabar; después se terminan.
  6. Si una consulta falla, el worker espera ERROR_BACKOFF_S antes de reintentar
     (F8-a, Alix 2026-11-02). Cuando el motor muere —en F7.3 el OOM de Postgres
     en PROFILE_C con Q1 y c=50— la conexión queda rota y cada reintento falla
     al instante: sin pausa fueron 455 504 reintentos en 110 s. El problema no
     es el crudo de 19 MB, sino que esos reintentos son **CPU del runner
     compitiendo con el motor dentro de la misma VM**, justo cuando el motor
     está en apuros. Con la pausa el bucle sigue vivo (si el motor se recupera,
     se ve), y la pausa no toca ninguna columna: los errores no cuentan para el
     throughput ni para los percentiles (A4).

Este módulo no sabe de motores ni de CSV: recibe una especificación del
motor y unos ganchos. Por eso se prueba con el motor falso.
"""

from __future__ import annotations

import multiprocessing as mp
import queue as queue_mod
import time
from dataclasses import dataclass, field

from benchmark_runner.metrics.window import Sample

READY_TIMEOUT_S = 120
MAX_PROCESSES = 10                # F5.5: 50 procesos llevaban la VM a swap
ERROR_BACKOFF_S = 1.0             # F8-a: pausa tras un fallo (ver punto 6 de arriba)
START_DELAY_NS = 300_000_000      # margen entre "todos listos" y el arranque común


def build_engine(spec: tuple, cell, timeout_s: float):
    """spec = ("real", {}) o ("fake", {...opciones del motor falso...})."""
    kind, opts = spec
    if kind == "fake":
        from benchmark_runner.engines.fake import FakeEngine
        return FakeEngine(cell, **opts)
    from benchmark_runner.engines.base import make_engine
    return make_engine(cell, timeout_s=timeout_s)


def plan_workers(concurrency: int, processes: int | None = None) -> tuple[int, int]:
    """(procesos, hilos por proceso) con procesos × hilos = concurrencia."""
    p = processes or min(concurrency, MAX_PROCESSES)
    if p < 1 or concurrency % p:
        raise ValueError(f"concurrencia {concurrency} no se reparte en {p} procesos iguales")
    return p, concurrency // p


def _thread_loop(wid, cell, spec, timeout_s, go, stop_at, q, backoff_s: float = ERROR_BACKOFF_S) -> None:
    from benchmark_runner.engines.base import QueryFailed, QueryTimeout
    try:
        engine = build_engine(spec, cell, timeout_s)
        engine.connect()
    except Exception as exc:                 # noqa: BLE001 — se informa al principal, que aborta
        q.put(("fatal", wid, f"{type(exc).__name__}: {exc}"))
        return
    q.put(("ready", wid, None))
    go.wait()
    stop = stop_at.value
    while time.monotonic_ns() < stop:
        detail = None
        t0 = time.monotonic_ns()
        try:
            engine.execute()
            kind = "ok"
        except QueryTimeout as exc:
            kind, detail = "timeout", str(exc)[:300]
        except QueryFailed as exc:
            kind, detail = "error", str(exc)[:300]
        except Exception as exc:             # noqa: BLE001 — cualquier otra cosa también es un fallo
            kind, detail = "error", f"{type(exc).__name__}: {exc}"[:300]
        t1 = time.monotonic_ns()
        q.put(("sample", wid, (t0, t1, kind, detail)))
        if kind == "error":
            # F8-a: pausa tras un fallo, para no quemar CPU del runner con reintentos
            # instantáneos mientras el motor agoniza. Un timeout NO pausa: ya tardó
            # lo suyo, y la pausa falsearía el bucle cerrado.
            time.sleep(min(backoff_s, max(0.0, (stop - time.monotonic_ns()) / 1e9)))
    try:
        engine.close()
    finally:
        q.put(("done", wid, None))


def _worker(first_wid, threads, cell, spec, timeout_s, cpus, go, stop_at, q) -> None:
    """Un proceso con `threads` workers (hilos), cada uno con su conexión."""
    import os
    import threading
    if cpus:
        os.sched_setaffinity(0, cpus)        # el proceso y sus hilos no comparten núcleo con el motor (F5-c)
    ts = [threading.Thread(target=_thread_loop, args=(first_wid + i, cell, spec, timeout_s, go, stop_at, q),
                           daemon=True) for i in range(threads)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()


class LoadAborted(RuntimeError):
    """Un worker no pudo conectar: no hay repetición que medir."""


@dataclass
class LoadResult:
    samples: list[Sample]
    kinds: dict[str, int]
    error_examples: list[str]
    t0_ns: int
    window_start_ns: int
    window_end_ns: int
    stop_ns: int
    start_hook: object
    end_hook: object
    workers: int
    workers_terminated: int
    wall_s: float
    per_worker: dict[int, int] = field(default_factory=dict)
    processes: int = 0
    threads_per_process: int = 0
    unfinished_workers: list[int] = field(default_factory=list)   # cortados al final, con una consulta en vuelo


def run_load(cell, windows, spec: tuple, *, concurrency: int, timeout_s: float,
             on_window_start, on_window_end, grace_s: float = 10.0, cpus=None,
             processes: int | None = None) -> LoadResult:
    n_proc, n_thr = plan_workers(concurrency, processes)
    ctx = mp.get_context("spawn")
    q = ctx.Queue()
    go = ctx.Event()
    stop_at = ctx.Value("q", 0)
    procs = [ctx.Process(target=_worker, args=(i * n_thr, n_thr, cell, spec, timeout_s, cpus, go, stop_at, q),
                         daemon=True) for i in range(n_proc)]
    t_begin = time.monotonic()
    for p in procs:
        p.start()

    samples: list[Sample] = []
    kinds = {"ok": 0, "timeout": 0, "error": 0}
    examples: list[str] = []
    per_worker: dict[int, int] = {}
    done: set[int] = set()

    def handle(msg) -> None:
        tag, wid, payload = msg
        if tag == "sample":
            t0, t1, kind, detail = payload
            samples.append(Sample(t0, t1, kind == "ok", kind, wid))
            kinds[kind] += 1
            per_worker[wid] = per_worker.get(wid, 0) + 1
            if detail and len(examples) < 5:
                examples.append(f"worker {wid}: {kind}: {detail}")
        elif tag == "done":
            done.add(wid)

    def drain_until(deadline_ns: int, stop_when_all_done: bool = False) -> None:
        while True:
            left = deadline_ns - time.monotonic_ns()
            if left <= 0 or (stop_when_all_done and len(done) == concurrency):
                return
            try:
                handle(q.get(timeout=min(left / 1e9, 0.2)))
            except queue_mod.Empty:
                pass

    try:
        # 1-2. Todos conectados antes de empezar.
        ready = 0
        deadline = time.monotonic() + READY_TIMEOUT_S
        while ready < concurrency:
            try:
                tag, wid, payload = q.get(timeout=max(0.1, deadline - time.monotonic()))
            except queue_mod.Empty:
                raise LoadAborted(f"solo {ready}/{concurrency} workers listos en {READY_TIMEOUT_S} s") from None
            if tag == "fatal":
                raise LoadAborted(f"worker {wid} no pudo conectar: {payload}")
            ready += tag == "ready"

        t0 = time.monotonic_ns() + START_DELAY_NS
        ws = t0 + windows.warmup_s * 1_000_000_000
        we = ws + windows.measure_s * 1_000_000_000
        stop = we + windows.cooldown_s * 1_000_000_000
        stop_at.value = stop
        go.set()

        # 3-4. Calentamiento → inicio de ventana → medición → fin de ventana → enfriamiento.
        drain_until(ws)
        start_hook = on_window_start()
        drain_until(we)
        end_hook = on_window_end()
        drain_until(stop)
        # 5. Gracia para las consultas en vuelo.
        drain_until(stop + int(grace_s * 1e9), stop_when_all_done=True)
    finally:
        # Un proceso cuyos hilos ya enviaron "done" sigue vivo unos instantes
        # mientras cierra su intérprete: se le espera. Solo se termina a los que
        # tenían hilos sin acabar, y se cuentan esos HILOS (consultas en vuelo).
        wids = lambda i: range(i * n_thr, (i + 1) * n_thr)  # noqa: E731
        for i, p in enumerate(procs):
            if all(w in done for w in wids(i)):
                p.join(timeout=5)
        terminated = 0
        for i, p in enumerate(procs):
            if p.is_alive():
                p.terminate()
                terminated += sum(w not in done for w in wids(i))
        for p in procs:
            p.join(timeout=10)
        # Lo que quede en la cola ya llegó: se recoge (son muestras terminadas).
        # Terminar un proceso mientras escribe puede dejar la cola dañada (lo
        # advierte la documentación de multiprocessing): lo que no se pueda leer
        # pertenece a consultas en vuelo, fuera de la ventana.
        while True:
            try:
                handle(q.get_nowait())
            except Exception:  # noqa: BLE001
                break
        q.close()

    return LoadResult(samples, kinds, examples, t0, ws, we, stop, start_hook, end_hook,
                      concurrency, terminated, round(time.monotonic() - t_begin, 2), per_worker, n_proc, n_thr,
                      sorted(w for w in range(concurrency) if w not in done))
