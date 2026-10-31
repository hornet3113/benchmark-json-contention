"""telemetry.py — comprobación previa del monitoreo y exportación de Prometheus por repetición (F6.4).

Jerarquía (SPEC §3, punto 3): las 14 columnas del CSV salen del cgroup y de los
motores, NUNCA de aquí. Prometheus da las curvas del reporte; si falta, las
tres figuras obligatorias salen del CSV y de `serie_cgroup_1s` del crudo.

Decisiones de Alix (docs/F6_TELEMETRIA.md):
  F6-f / F6-A1  Si la telemetría falla, la repetición CORRE igual y su fila se
                escribe; el fallo queda marcado aquí, en el crudo y en el log. La
                matriz no se detiene por fallos de telemetría.
  F6-f          En cada fallo se registran memoria y swap de la VM (vm_memory), para
                distinguir un fallo inocuo de uno por presión de memoria.
  F6-A4         Comprobación previa = up==1 de los 3 jobs Y ningún colector de
                node_exporter fallido en el último minuto. Si falla: registrar
                memoria, ejecutar scripts/up_monitoring.sh UNA vez, volver a
                comprobar y anotar. Tras el reinicio, la segunda comprobación
                mira solo el valor actual de los colectores: el último minuto
                aún contiene los fallos de antes del reinicio.

Exportación (F6-e): muestras CRUDAS de cada serie (selector de rango en una
consulta instantánea), no query_range. cAdvisor pone marca de tiempo propia y
Prometheus no vence esas series (F6.1): query_range rellenaría un hueco
repitiendo el último valor y lo escondería. Con las crudas, cada hueco se ve y
se anota con sus límites.
"""

from __future__ import annotations

import json
import subprocess
import time
import urllib.parse
import urllib.request
from collections.abc import Callable
from pathlib import Path

PROMETHEUS_URL = "http://127.0.0.1:9090"
JOBS = ("prometheus", "cadvisor", "node")
EXPORT_MARGIN_S = 5          # margen antes y después de la ventana
GAP_S = 1.5                  # con scrape de 1 s, un salto mayor es una muestra perdida
SCRAPE_SETTLE_S = 2          # que Prometheus haya hecho el scrape del último segundo
RECOVERY_TIMEOUT_S = 120

# Series del contenedor del motor (filtradas por id="/docker/<id>", F6.1: sin etiqueta name).
CONTAINER_METRICS = (
    "container_cpu_cfs_throttled_seconds_total", "container_cpu_cfs_throttled_periods_total",
    "container_cpu_cfs_periods_total", "container_cpu_usage_seconds_total",
    "container_memory_rss", "container_memory_working_set_bytes", "container_memory_usage_bytes",
)
# Las que, si vienen vacías, hacen la exportación "fallida": son las de las curvas (R-30).
REQUIRED_CONTAINER = ("container_cpu_cfs_throttled_seconds_total", "container_memory_rss")
# Host (VM de WSL2): memoria, swap, I/O, presión de memoria y carga (playbook §7).
NODE_METRICS = (
    "node_memory_MemAvailable_bytes", "node_memory_SwapFree_bytes", "node_vmstat_pswpin", "node_vmstat_pswpout",
    "node_disk_read_bytes_total", "node_disk_written_bytes_total",
    "node_pressure_memory_waiting_seconds_total", "node_pressure_memory_stalled_seconds_total", "node_load1",
)

Getter = Callable[[str, dict], dict]


def http_get(path: str, params: dict) -> dict:
    url = f"{PROMETHEUS_URL}{path}?{urllib.parse.urlencode(params)}"
    with urllib.request.urlopen(url, timeout=10) as r:
        body = json.load(r)
    if body.get("status") != "success":
        raise RuntimeError(f"Prometheus: {body.get('errorType')}: {body.get('error')}")
    return body["data"]


# --- memoria y swap de la VM (F6-f) -----------------------------------------

def vm_memory(proc: Path = Path("/proc")) -> dict:
    """Lo que hace falta para saber si un fallo de telemetría vino con presión de memoria."""
    out: dict = {"t_wall": time.time()}
    try:
        mem = {l.split(":")[0]: int(l.split()[1]) for l in (proc / "meminfo").read_text().splitlines()}
        out.update({k + "_kib": mem.get(k) for k in ("MemTotal", "MemAvailable", "SwapTotal", "SwapFree", "Committed_AS")})
    except OSError as exc:
        out["meminfo_error"] = str(exc)
    try:
        vm = dict(l.split() for l in (proc / "vmstat").read_text().splitlines())
        out.update({k: int(vm[k]) for k in ("pswpin", "pswpout", "oom_kill") if k in vm})
    except OSError as exc:
        out["vmstat_error"] = str(exc)
    try:
        out["pressure_memory"] = (proc / "pressure" / "memory").read_text().strip().splitlines()
    except OSError as exc:
        out["pressure_error"] = str(exc)
    return out


# --- comprobación previa (F6-A4) ---------------------------------------------

def check(get: Getter, recent_window_s: int | None = 60) -> dict:
    """up==1 de los 3 jobs y colectores de node_exporter sin fallos.

    recent_window_s=None: solo el valor actual (para la segunda comprobación, tras un reinicio).
    """
    out: dict = {"t_wall": time.time()}
    try:
        up = {r["metric"].get("job"): float(r["value"][1]) for r in get("/api/v1/query", {"query": "up"})["result"]}
        out["up"] = up
        expr = ("node_scrape_collector_success == 0" if recent_window_s is None
                else f"min_over_time(node_scrape_collector_success[{recent_window_s}s]) == 0")
        out["colectores_con_fallos"] = sorted(r["metric"].get("collector") for r in
                                              get("/api/v1/query", {"query": expr})["result"])
        out["ok"] = all(up.get(j) == 1.0 for j in JOBS) and not out["colectores_con_fallos"]
        if not out["ok"]:
            out["motivo"] = ", ".join([f"up{{job={j}}}={up.get(j)}" for j in JOBS if up.get(j) != 1.0]
                                      + [f"colector {c} con fallos" for c in out["colectores_con_fallos"]])
    except Exception as exc:  # noqa: BLE001 — Prometheus caído o inalcanzable también es un fallo de telemetría
        out.update({"ok": False, "motivo": f"Prometheus no responde: {type(exc).__name__}: {exc}"[:300]})
    return out


def run_recovery(root: Path) -> dict:
    """scripts/up_monitoring.sh: idempotente, solo recrea lo que esté caído."""
    try:
        res = subprocess.run([str(root / "scripts" / "up_monitoring.sh")], capture_output=True, text=True,
                             timeout=RECOVERY_TIMEOUT_S)
        return {"exit": res.returncode, "salida": (res.stdout + res.stderr)[-600:]}
    except Exception as exc:  # noqa: BLE001
        return {"exit": None, "salida": f"{type(exc).__name__}: {exc}"[:300]}


def preflight(get: Getter, recover: Callable[[], dict], memory: Callable[[], dict] = vm_memory) -> dict:
    """F6-A4. Nunca lanza: devuelve qué pasó. `ok` dice si la repetición tendrá telemetría."""
    first = check(get)
    out: dict = {"primera": first, "ok": first["ok"]}
    if first["ok"]:
        return out
    out["memoria_vm_al_fallar"] = memory()
    out["recuperacion"] = recover()
    second = check(get, recent_window_s=None)
    out["segunda"] = second
    out["memoria_vm_tras_recuperar"] = memory()
    out["ok"] = second["ok"]
    out["recuperada"] = second["ok"]
    return out


# --- exportación de la ventana (F6-e) ----------------------------------------

def gaps(timestamps: list[float], t_from: float, t_to: float, gap_s: float = GAP_S) -> list[list[float]]:
    """Intervalos dentro de [t_from, t_to] sin muestras durante más de gap_s, incluidos los bordes."""
    ts = sorted(t for t in timestamps if t_from - gap_s <= t <= t_to + gap_s)
    if not ts:
        return [[t_from, t_to]]
    out = []
    if ts[0] - t_from > gap_s:
        out.append([t_from, ts[0]])
    out += [[a, b] for a, b in zip(ts, ts[1:]) if b - a > gap_s]
    if t_to - ts[-1] > gap_s:
        out.append([ts[-1], t_to])
    return [[round(a, 3), round(b, 3)] for a, b in out]


def raw_series(get: Getter, selector: str, t_from: float, t_to: float) -> list[dict]:
    span = int(t_to - t_from) + 1
    res = get("/api/v1/query", {"query": f"{selector}[{span}s]", "time": f"{t_to:.3f}"})["result"]
    return [{"etiquetas": r["metric"], "muestras": [[float(t), float(v)] for t, v in r["values"]
                                                    if t_from <= float(t) <= t_to]} for r in res]


def export(get: Getter, container_id: str, w_from: float, w_to: float, *,
           margin_s: float = EXPORT_MARGIN_S, now: Callable[[], float] = time.time,
           sleep: Callable[[float], None] = time.sleep) -> dict:
    """Series de la ventana [w_from, w_to] (reloj de pared, s) más un margen. Nunca lanza."""
    t_from, t_to = w_from - margin_s, w_to + margin_s
    wait = t_to + SCRAPE_SETTLE_S - now()
    if wait > 0:
        sleep(wait)
    out: dict = {"ventana_wall_s": [w_from, w_to], "margen_s": margin_s, "container_id": container_id,
                 "series": {}, "huecos_en_ventana": {}}
    try:
        for m in CONTAINER_METRICS:
            out["series"][m] = raw_series(get, f'{m}{{id="/docker/{container_id}"}}', t_from, t_to)
        for m in NODE_METRICS:
            out["series"][m] = raw_series(get, m, t_from, t_to)
        out["series"]["up"] = raw_series(get, "up", t_from, t_to)
    except Exception as exc:  # noqa: BLE001
        out.update({"estado": "fallida", "motivo": f"{type(exc).__name__}: {exc}"[:300]})
        return out

    empty = [m for m in REQUIRED_CONTAINER if not any(s["muestras"] for s in out["series"][m])]
    for m, series in out["series"].items():
        for s in series:
            g = gaps([t for t, _ in s["muestras"]], w_from, w_to)
            if g:
                key = m if len(series) == 1 else f"{m}{json.dumps(s['etiquetas'], sort_keys=True)}"
                out["huecos_en_ventana"][key] = g
    if empty:
        out.update({"estado": "fallida", "motivo": f"sin muestras del motor en: {', '.join(empty)}"})
    else:
        out["estado"] = "con_huecos" if out["huecos_en_ventana"] else "completa"
    out["segundos_sin_muestra_max"] = max((b - a for g in out["huecos_en_ventana"].values() for a, b in g),
                                          default=0.0)
    return out


def summary(pre: dict, exp: dict | None) -> dict:
    """Lo que va al crudo y al log. `fallo` = sin telemetría útil en esta repetición (F6-A1: no detiene nada)."""
    failed = (not pre["ok"]) or exp is None or exp.get("estado") == "fallida"
    reasons = []
    if not pre["primera"]["ok"]:
        reasons.append(f"comprobación previa: {pre['primera'].get('motivo')}"
                       + (" → recuperada" if pre.get("recuperada") else " → NO recuperada"))
    if exp is not None and exp.get("estado") == "fallida":
        reasons.append(f"exportación fallida: {exp.get('motivo')}")
    if exp is not None and exp.get("estado") == "con_huecos":
        reasons.append(f"huecos en {len(exp['huecos_en_ventana'])} serie(s); el mayor de "
                       f"{exp['segundos_sin_muestra_max']:.1f} s")
    return {"fallo": failed, "estado_exportacion": None if exp is None else exp.get("estado"), "motivos": reasons}
