#!/usr/bin/env python3
"""check_pilot_f7.py — criterios de aceptación de la celda piloto (PLAN F7).

Uso:  .venv/bin/python scripts/checks/check_pilot_f7.py     (después de scripts/run_pilot_f7.sh)

Comprueba, por motor, sobre results/f7/measurements.csv y results/f7/raw/:
  1. 3 filas con run_number 1, 2 y 3 (`validate_csv.py` valida el esquema aparte).
  2. **CV del throughput < 15 %** entre las 3 repeticiones (PLAN F7).
  3. **Sin tendencia monótona** (F7-b, pedido de Alix al cerrar F6): el CV no ve una
     degradación progresiva (100-110-120 da 9 % y pasa). Aquí hay tendencia si las 3
     repeticiones van en orden monótono Y r1→r3 cambia más del UMBRAL_TENDENCIA.
     Los dos a la vez: con 3 valores, el orden monótono sale por azar 1 de cada 3 veces
     (2 de los 6 órdenes posibles), así que por sí solo no distingue ruido de deriva.
     Se mira en throughput y en p50.
  4. Plan de ejecución capturado (R-31), que en c=1 debe existir.
  5. Tiempo real por repetición → estimación del costo de F8.
  6. **Primera consulta en frío frente al calentamiento** en PROFILE_C (PLAN F7): la
     primera consulta de cada worker, tomada del crudo, contra los 60 s de calentamiento.
  7. Gracia y enfriamiento: workers cortados al final (consultas huérfanas, pendiente F7/F8).
  8. Telemetría de F6, flush con efecto medido (A5), suspensión de la VM y censura (A4).
  9. Throttling de la fila junto a la línea base en reposo del mismo motor y perfil
     (F6.3): parte del throttling de Mongo en PROFILE_C no lo causa el benchmark.

Es una verificación, no una medición: no escribe en ningún CSV.
Salida: results/f7/check_pilot.json. Exit 0 si se cumplen los criterios exigibles.
"""

from __future__ import annotations

import csv
import json
import statistics
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from benchmark_runner.config import LOW_DENSITY_SAMPLES, WINDOWS  # noqa: E402

F7 = ROOT / "results" / "f7"
BASELINE_DIR = ROOT / "results" / "f6" / "f6_3" / "baseline"
CV_MAX = 0.15
UMBRAL_TENDENCIA = 0.10      # cambio relativo r1→r3 a partir del cual la monotonía cuenta (F7-b)
MATRIX_RUNS = {54: 162, 36: 108}


def cv(values: list[float]) -> float | None:
    """Coeficiente de variación (desviación típica muestral ÷ media)."""
    if len(values) < 2 or not statistics.fmean(values):
        return None
    return statistics.stdev(values) / abs(statistics.fmean(values))


def trend(values: list[float]) -> dict:
    """F7-b: monotonía Y tamaño. Sin las dos cosas no se declara tendencia."""
    if len(values) < 3 or not values[0]:
        return {"monotona": None, "cambio_rel": None, "hay_tendencia": False}
    up = all(a < b for a, b in zip(values, values[1:]))
    down = all(a > b for a, b in zip(values, values[1:]))
    rel = (values[-1] - values[0]) / abs(values[0])
    return {"monotona": "creciente" if up else "decreciente" if down else None,
            "cambio_rel": round(rel, 4), "umbral": UMBRAL_TENDENCIA,
            "hay_tendencia": (up or down) and abs(rel) > UMBRAL_TENDENCIA}


def baseline_throttling() -> dict:
    """Throttling en reposo por motor y perfil, normalizado a la ventana real (F6.3)."""
    files = sorted(BASELINE_DIR.glob("resumen_*.json"))
    if not files:
        return {}
    data = json.loads(files[-1].read_text())
    out = {}
    for row in data["combinaciones"]:
        if "error" in row:
            continue
        key = ("mongodb" if row["motor"] == "mongo" else "postgresql", row["perfil"])
        out[key] = {"s_por_minuto": row["ventana"]["throttled_s_por_minuto"],
                    "estimado_en_la_ventana_s": round(row["ventana"]["throttled_s_por_minuto"]
                                                      * WINDOWS.measure_s / 60, 2),
                    "archivo": str(files[-1].relative_to(ROOT))}
    return out


def cold_first_queries(raw: dict) -> dict:
    """Primera consulta de cada worker (en frío, tras el flush) frente al calentamiento."""
    w0 = raw["ventana_ns"]["inicio"]
    first: dict[int, list] = {}
    for start, end, ok, wid in raw["muestras"]:
        if wid not in first or start < first[wid][0]:
            first[wid] = [start, end, ok]
    ms = sorted(round((e - s) / 1e6, 1) for s, e, _ in first.values())
    warm = raw["ventanas_s"]["warmup_s"]
    # Un worker cortado al FINAL de la ventana no dice nada de su primera consulta: lo
    # que importa aquí es un worker que no terminó NINGUNA (su primera no cabe ni medida).
    sin_ninguna = sorted(set(raw["consultas"].get("workers_sin_terminar", [])) - set(first))
    return {"workers_con_muestra": len(ms), "primera_consulta_ms": ms,
            "max_s": round(max(ms) / 1000, 2) if ms else None,
            "calentamiento_s": warm,
            "cabe_en_el_calentamiento": bool(ms) and max(ms) / 1000 <= warm and not sin_ninguna,
            "primera_consulta_dentro_de_la_ventana": sum(1 for _, (s, _, _) in first.items() if s >= w0),
            "workers_sin_ninguna_consulta_terminada": sin_ninguna}


def per_run(raw: dict) -> dict:
    row = raw["fila_csv"]
    flush = raw["preparacion"]["flush"]
    tele = raw.get("telemetria") or {}
    rel = raw["relojes"]
    drift = ((rel["fin"]["wall_ns"] - rel["inicio"]["wall_ns"])
             - (rel["fin"]["mono_ns"] - rel["inicio"]["mono_ns"])) / 1e9
    s = raw.get("serie_cgroup_1s") or {}
    return {"run_number": row["run_number"], "status": row["status"],
            "throughput_qps": row["throughput_qps"], "p50": row["latency_p50_ms"],
            "p95": row["latency_p95_ms"], "p99": row["latency_p99_ms"],
            "cpu_throttled_seconds": row["cpu_throttled_seconds"], "max_rss_mb": row["max_rss_mb"],
            "completadas_en_ventana": raw["censura"]["completadas_en_ventana"],
            "fraccion_timeouts": raw["censura"]["fraccion_timeouts"],
            "percentil_valido": raw["censura"]["percentil_valido"],
            "motivos": raw["motivos"],
            "flush_liberado_kb": flush.get("liberado_kb"), "flush_ok": flush.get("ok"),
            "deriva_reloj_s": round(drift, 3),
            "workers_cortados_al_final": raw["consultas"]["workers_terminados_al_final"],
            "workers_sin_terminar": raw["consultas"]["workers_sin_terminar"],
            "plan": raw["plan"], "plan_error": raw["plan_error"],
            "telemetria": {k: tele.get(k) for k in ("fallo", "estado_exportacion", "motivos")} or None,
            "serie_cgroup_1s_filas": len(s.get("filas", [])),
            "frio": cold_first_queries(raw)}


def evaluate(engine: str, raws: list[dict], base: dict) -> dict:
    runs = sorted((per_run(r) for r in raws), key=lambda r: r["run_number"])
    profile = raws[0]["fila_csv"]["profile"]
    qps = [r["throughput_qps"] for r in runs]
    p50 = [r["p50"] for r in runs if r["p50"] is not None]
    out: dict = {"repeticiones": runs,
                 "cv_throughput": round(c, 4) if (c := cv(qps)) is not None else None,
                 "cv_p50": round(c2, 4) if (c2 := cv(p50)) is not None else None,
                 "tendencia_throughput": trend(qps), "tendencia_p50": trend(p50),
                 "perfil": profile,
                 "linea_base_throttling_en_reposo": base.get((engine, profile))}
    out["checks"] = {
        "3_filas_r1_r2_r3": [r["run_number"] for r in runs] == [1, 2, 3],
        "cv_throughput_<15%": out["cv_throughput"] is not None and out["cv_throughput"] < CV_MAX,
        "sin_tendencia_throughput": not out["tendencia_throughput"]["hay_tendencia"],
        "sin_tendencia_p50": not out["tendencia_p50"]["hay_tendencia"],
        # R-31, tal como lo diseñó F5: UN plan por celda, en la repetición 1 de c=1 y
        # fuera de la ventana. No se exige en las 3 repeticiones; sería el mismo plan.
        "plan_capturado": any(r["plan"] and Path(r["plan"]).exists() for r in runs)
                          and not any(r["plan_error"] for r in runs),
        "flush_con_efecto": all(r["flush_ok"] and (r["flush_liberado_kb"] or 0) > 0 for r in runs),
        "sin_suspension": all(abs(r["deriva_reloj_s"]) < 2 for r in runs),
        "telemetria_sin_fallo": all((r["telemetria"] or {}).get("fallo") is not True for r in runs),
    }
    # Informativos, no criterios: se declaran, no bloquean (A4, F7).
    out["avisos"] = []
    for r in runs:
        if r["completadas_en_ventana"] < LOW_DENSITY_SAMPLES:
            out["avisos"].append(f"r{r['run_number']}: baja densidad muestral "
                                 f"({r['completadas_en_ventana']} < {LOW_DENSITY_SAMPLES}; A4)")
        if not r["frio"]["cabe_en_el_calentamiento"]:
            out["avisos"].append(f"r{r['run_number']}: la primera consulta en frío ({r['frio']['max_s']} s) "
                                 f"NO cabe en el calentamiento de {r['frio']['calentamiento_s']} s "
                                 f"→ P95/P99 contaminados (limitación del protocolo)")
        if r["workers_cortados_al_final"]:
            out["avisos"].append(f"r{r['run_number']}: {r['workers_cortados_al_final']} worker(s) cortados al "
                                 f"final (consulta huérfana en el servidor hasta bajar el contenedor)")
    return out


def main() -> int:
    csv_file = F7 / "measurements.csv"
    if not csv_file.exists():
        sys.exit(f"no existe {csv_file.relative_to(ROOT)}: ¿corriste scripts/run_pilot_f7.sh?")
    rows = list(csv.DictReader(csv_file.open()))
    raws = [json.loads(f.read_text()) for f in sorted((F7 / "raw").glob("*.json"))]
    base = baseline_throttling()
    engines = sorted({r["engine"] for r in rows})
    out = {"descripcion": "criterios de la celda piloto (PLAN F7); verificación, no medición",
           "filas_en_el_csv": len(rows), "motores": {}}
    for engine in engines:
        rs = [r for r in raws if r["fila_csv"]["engine"] == engine]
        out["motores"][engine] = evaluate(engine, rs, base)

    # Coste de F8 con el tiempo REAL por repetición: las repeticiones de un motor corren
    # seguidas, así que la diferencia entre dos `inicio_utc` consecutivos es lo que tardó
    # la anterior completa (flush + arranque + healthcheck + ventanas + plan). Se miden
    # DENTRO de cada motor: el salto de un motor a otro incluye además el monitor del host.
    gaps = []
    for engine in engines:
        starts = sorted(datetime.strptime(r["inicio_utc"], "%Y-%m-%dT%H:%M:%SZ")
                        for r in raws if r["fila_csv"]["engine"] == engine)
        gaps += [(b - a).total_seconds() for a, b in zip(starts, starts[1:])]
    # La última no tiene siguiente: se usa la mediana de las demás, y se dice.
    ventanas_s = WINDOWS.warmup_s + WINDOWS.measure_s + WINDOWS.cooldown_s
    por_repeticion = round(statistics.median(gaps), 1) if gaps else None
    out["tiempo_real"] = {"segundos_por_repeticion_mediana": por_repeticion,
                          "sobrecosto_sobre_las_ventanas_s": (None if por_repeticion is None
                                                              else round(por_repeticion - ventanas_s, 1)),
                          "muestras": len(gaps), "ventanas_s": ventanas_s,
                          "nota": "diferencia entre inicio_utc consecutivos; la última repetición no cuenta"}
    for mode, runs in MATRIX_RUNS.items():
        out.setdefault("estimacion_f8", {})[f"{mode}_celdas"] = {
            "corridas": runs, "horas_solo_ventanas": round(runs * ventanas_s / 3600, 1),
            "horas_con_tiempo_real_del_piloto": (None if por_repeticion is None
                                                 else round(runs * por_repeticion / 3600, 1)),
            "nota": "el tiempo real del piloto es de PROFILE_C con c=1; con c=50 el corte de workers y el "
                    "arranque pueden cambiarlo"}
    ok = all(all(m["checks"].values()) for m in out["motores"].values()) and bool(engines)
    out["todo_cumple"] = ok
    dest = F7 / "check_pilot.json"
    dest.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n")
    for engine, m in out["motores"].items():
        print(f"== {engine}")
        for r in m["repeticiones"]:
            print(f"   r{r['run_number']} status={r['status']} qps={r['throughput_qps']} "
                  f"p50/p95/p99={r['p50']}/{r['p95']}/{r['p99']} ms throttled={r['cpu_throttled_seconds']} s "
                  f"rss={r['max_rss_mb']} MiB · completadas={r['completadas_en_ventana']} · "
                  f"1ª en frío={r['frio']['max_s']} s (calentamiento {r['frio']['calentamiento_s']} s) · "
                  f"flush -{r['flush_liberado_kb']} kB · telemetría={(r['telemetria'] or {}).get('estado_exportacion')}")
        print(f"   CV qps={m['cv_throughput']} p50={m['cv_p50']} · tendencia qps={m['tendencia_throughput']} "
              f"p50={m['tendencia_p50']}")
        print(f"   línea base de throttling en reposo: {m['linea_base_throttling_en_reposo']}")
        for a in m["avisos"]:
            print(f"   AVISO {a}")
        print(f"   {m['checks']}")
    print(f"   tiempo real: {out['tiempo_real']}")
    print(f"   estimación de F8: {out['estimacion_f8']}")
    print(f"-> {dest} · {'CUMPLE' if ok else 'REVISAR'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
