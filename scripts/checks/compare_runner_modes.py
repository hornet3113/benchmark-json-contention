#!/usr/bin/env python3
"""compare_runner_modes.py — ¿mide lo mismo el runner con 50 procesos que con 10 × 5 hilos? (F5.5)

Uso:  .venv/bin/python scripts/checks/compare_runner_modes.py   (después de scripts/smoke_f55b.sh)

Diseño A-B-A por motor, celda Q2_MEM_LOW · PROFILE_A · c=50:
    r1 = A (50 procesos × 1 hilo) · r2 = B (10 procesos × 5 hilos) · r3 = A otra vez
Las dos A encierran a B en el tiempo: si el host cambia a mitad (pasó en F5.3),
las A lo delatan en vez de atribuírselo al modo del runner.

Historia del criterio 1 (no se borra):
  - v1 (F5.5b): 50 de 50 clientes activos en cada borde. Postgres: cumplió.
  - v2 (2026-11-01, Alix, antes de repetir Mongo): ≥ 48 de 50 en cada borde,
    porque una foto instantánea de un bucle cerrado puede atrapar a un worker
    entre consultas. Mongo (23:52 UTC): NO cumplió (47 al inicio de B). Queda
    registrado como incumplido en docs/F5_RUNNER.md.
  - v3 (esta versión): fotos con su intervalo exacto, en los bordes y cada
    S s dentro de la ventana, cruzadas con las marcas del runner
    (benchmark_runner/metrics/concurrency.py). Ver CRITERION_V3.

Criterio v3, por motor:
  1. El motor ve la concurrencia: en cada una de las 3 corridas, la mediana de
     "motor" sobre todas las fotos es ≥ MEDIAN_ENGINE_MIN, con al menos
     MIN_PHOTOS fotos válidas.
  2. B no pierde clientes más que A: media de "faltan" (cliente_seguro − motor)
     de B ≤ máx(media de A1, media de A2) + EXTRA_MISSING_MAX. Es la pregunta de
     fondo: si los hilos de un mismo proceso (GIL) no llegaran a enviar sus
     consultas, el runner las contaría en vuelo y el motor no: "faltan" crecería en B.
  3. p50, p95 y throughput de B dentro de [min(A1, A2) × 0.9, max(A1, A2) × 1.1].
Además se informa la memoria máxima del árbol del runner (monitor) en cada modo.

Salida: results/smoke/comparacion_modos.json. Exit 0 si se cumple para los motores corridos.
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from benchmark_runner.metrics.concurrency import cross, summarize  # noqa: E402

SMOKE = ROOT / "results" / "smoke"
TOL = 0.10
MEDIAN_ENGINE_MIN = 49        # de 50
MIN_PHOTOS = 10
EXTRA_MISSING_MAX = 1.0
# PROPUESTA: pasa a "fijado" solo cuando Alix lo confirme, ANTES de correr.
CRITERION_V3 = {
    # No se llegó a fijar: la corrida de las 00:24 UTC se hizo antes de confirmarlo y Alix
    # cerró F5 con la opción (b) (docs/F5_RUNNER.md, "Cierre de F5").
    "estado": "PROPUESTO, sin fijar",
    "fijado_por": None,
    "fecha": None,
    "motivo": ("La v2 (≥ 48 en cada borde) no cumplió con Mongo (47 al inicio de B), pero una sola foto por "
               "borde, sin su instante, no distingue entre 'el motor no ve al cliente' y 'la foto cayó mientras "
               "una respuesta iba de camino'. La v3 mide con fotos cronometradas y compara B con A. "
               "El resultado de la v2 se conserva como incumplido."),
}


def monitor_max(step: str) -> int | None:
    f = SMOKE / f"monitor_{step}.csv"
    if not f.exists():
        return None
    vals = [int(r["runner_rss_mb"]) for r in csv.DictReader(f.open()) if r["runner_rss_mb"].isdigit()]
    return max(vals) if vals else None


def photos_of(raw: dict) -> list[dict] | None:
    """Fotos con intervalo (bordes + serie). None si el crudo es anterior a F5.5b v3."""
    act = raw["actividad_del_motor"]
    if act.get("serie") is None:
        return None
    edges = [{"momento": k, **act[k]} for k in ("inicio", "fin") if act.get(k) and "t0_ns" in act[k]]
    return sorted(edges + act["serie"], key=lambda p: p["t0_ns"])


def evaluate(engine: str, runs_raw: dict[str, dict]) -> dict:
    runs, crossed = {}, {}
    for mode, raw in runs_raw.items():
        row = raw["fila_csv"]
        photos = photos_of(raw)
        samples = [(m[0], m[1], m[3]) for m in raw["muestras"]] if photos is not None else []
        rows = cross(photos, samples, raw["consultas"].get("workers_sin_terminar", []), engine) if photos else []
        crossed[mode] = rows
        runs[mode] = {"procesos_x_hilos": raw["procesos_x_hilos"], "status": row["status"],
                      "p50": row["latency_p50_ms"], "p95": row["latency_p95_ms"], "qps": row["throughput_qps"],
                      "completadas": raw["censura"]["completadas_en_ventana"],
                      "workers_terminados_al_final": raw["consultas"]["workers_terminados_al_final"],
                      "fotos": summarize(rows) if photos is not None else None,
                      "conexiones": [a.get("conexiones_actuales", a.get("clientes")) if a else None
                                     for a in (raw["actividad_del_motor"]["inicio"], raw["actividad_del_motor"]["fin"])],
                      "runner_rss_max_mib": monitor_max(f"{engine}_{mode}")}
    a1, b, a2 = runs["A1"], runs["B"], runs["A2"]
    comparable = all(r["fotos"] and r["fotos"]["fotos_validas"] >= MIN_PHOTOS for r in runs.values())
    checks: dict = {"fotos_suficientes": comparable}
    if comparable:
        checks["mediana_motor_>=49_en_las_3"] = all(r["fotos"]["mediana_motor"] >= MEDIAN_ENGINE_MIN
                                                    for r in runs.values())
        lim = max(a1["fotos"]["media_faltan"], a2["fotos"]["media_faltan"]) + EXTRA_MISSING_MAX
        checks["faltan_B_<=_A+1"] = b["fotos"]["media_faltan"] <= lim
        checks["faltan_limite"] = round(lim, 3)
    for metric in ("p50", "p95", "qps"):
        lo, hi = min(a1[metric], a2[metric]) * (1 - TOL), max(a1[metric], a2[metric]) * (1 + TOL)
        checks[f"{metric}_B_dentro_de_A"] = lo <= b[metric] <= hi
        checks[f"{metric}_rango_A_ampliado"] = [round(lo, 3), round(hi, 3)]
    passed = comparable and all(v for k, v in checks.items()
                                if not k.endswith(("_ampliado", "_limite")))
    return {"corridas": runs, "comprobaciones": checks, "coinciden": passed, "fotos_cruzadas": crossed}


def main() -> int:
    out = {"criterio": {"version": 3, **CRITERION_V3, "mediana_motor_minima": MEDIAN_ENGINE_MIN, "de": 50,
                        "fotos_minimas": MIN_PHOTOS, "faltan_extra_max": EXTRA_MISSING_MAX,
                        "tolerancia_latencias": TOL}, "motores": {}}
    if CRITERION_V3["fijado_por"] is None:
        print("AVISO: el criterio v3 está PROPUESTO, sin fijar. El resultado no cuenta como evaluación.")
    ok_all, ran = True, False
    for engine in ("postgresql", "mongodb"):
        files = {mode: SMOKE / "raw" / f"{engine}_PROFILE_A_BASELINE_Q2_MEM_LOW_c50_r{r}.json"
                 for r, mode in ((1, "A1"), (2, "B"), (3, "A2"))}
        if not all(f.exists() for f in files.values()):
            print(f"== {engine}: no se corrió en esta tanda (se omite)")
            continue
        ran = True
        res = evaluate(engine, {m: json.loads(f.read_text()) for m, f in files.items()})
        ok_all &= res["coinciden"]
        out["motores"][engine] = res
        print(f"== {engine}: {'COINCIDEN' if res['coinciden'] else 'NO COINCIDEN'}")
        for mode, r in res["corridas"].items():
            f = r["fotos"] or {}
            print(f"   {mode:<2} {r['procesos_x_hilos'][0]:>2}×{r['procesos_x_hilos'][1]}  p50={r['p50']:.0f} ms  "
                  f"p95={r['p95']:.0f} ms  qps={r['qps']:.4f}  completadas={r['completadas']}  "
                  f"fotos={f.get('fotos_validas')}  motor mediana/min={f.get('mediana_motor')}/{f.get('min_motor')}  "
                  f"faltan media/max={f.get('media_faltan')}/{f.get('max_faltan')}  conexiones={r['conexiones']}  "
                  f"cortados={r['workers_terminados_al_final']}  runner={r['runner_rss_max_mib']} MiB")
        for k, v in res["comprobaciones"].items():
            print(f"   {k}: {v}")
    ok_all &= ran
    out["coinciden_en_los_motores_corridos"] = ok_all
    (SMOKE / "comparacion_modos.json").write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n")
    print(f"-> results/smoke/comparacion_modos.json · {'ADELANTE con 10×5' if ok_all else 'NO coinciden: revisar antes de seguir'}")
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())
