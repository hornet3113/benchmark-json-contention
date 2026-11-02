#!/usr/bin/env python3
"""build_report_data.py — datos y tablas del reporte, generados del CSV (F9).

Uso:
    .venv/bin/python scripts/build_report_data.py

Criterio de aceptación de PLAN F9: *"cada número del reporte es trazable a una
fila del CSV o a un archivo de `results/`. **Ningún valor escrito a mano**"*. Por
eso el reporte de LaTeX no lleva números: lee los archivos que escribe este
script. Si cambian los datos, se vuelve a correr y el reporte queda al día.

Qué escribe, todo bajo `report/`:

  `datos/*.dat`    tablas de columnas para pgfplots (las figuras las dibuja LaTeX,
                   así el revisor ve de dónde sale cada punto).
  `tablas/*.tex`   tablas ya formateadas (`tabular`), para `\\input`.
  `cifras/*.tex`   cifras suel­tas como macros (`\\cifraFilasCsv`, …), para citarlas
                   en el texto sin teclearlas.

Decisiones que este script aplica, no inventa:
  - **R-30.1** (Alix): la figura de P99 contra concurrencia lleva **dos series**,
    la del CSV y la recalculada **sin la primera consulta de cada worker**, y
    marca los puntos contaminados. La segunda se recalcula de `results/raw/`.
  - **A4**: las celdas con percentiles invalidados por censura no se grafican como
    si valieran; se marcan y se listan aparte.
  - **R-29.1**: los OOM se cuentan distinguiendo si el `oom_kill` del cgroup se
    movió **dentro** de la ventana o si ya venía del calentamiento.
  - **R-29.2**: la celda colapsada (`postgresql · C · Q1 · c=50`) se marca en los
    datos con una columna `nota`, para que toda tabla pueda poner su nota al pie.
  - **F6-A3 / A11**: M3 se calcula con `working_set`, y también con `max_rss_mb`
    para mostrar el sesgo.
"""

from __future__ import annotations

import csv
import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from benchmark_runner.config import LOW_DENSITY_SAMPLES  # noqa: E402
from benchmark_runner.metrics import percentiles  # noqa: E402

RESULTS = ROOT / "results"
REPORT = ROOT / "report"
PERFIL_CORTO = {"PROFILE_A_BASELINE": "A", "PROFILE_B_MEDIUM": "B", "PROFILE_C_SEVERE": "C"}
MOTOR_CORTO = {"mongodb": "MongoDB", "postgresql": "PostgreSQL"}
# R-29.2: celda cuyo motor estaba colapsado durante la ventana. Toda tabla donde
# aparezca lleva nota al pie; aquí se marca en los datos para no olvidarlo.
CELDA_COLAPSADA = ("postgresql", "PROFILE_C_SEVERE", "Q1", "50")


def num(x):
    return None if x in (None, "") else float(x)


def tex(x, dec=2, vacio="---"):
    if x is None:
        return vacio
    return f"{x:.{dec}f}" if isinstance(x, float) else str(x)


def cargar() -> tuple[list[dict], dict]:
    with (RESULTS / "measurements.csv").open(newline="") as f:
        filas = list(csv.DictReader(f))
    crudos = {}
    for r in filas:
        rid = f"{r['engine']}_{r['profile']}_{r['query_id']}_c{r['concurrency']}_r{r['run_number']}"
        p = RESULTS / "raw" / f"{rid}.json"
        if p.exists():
            crudos[rid] = json.loads(p.read_text())
    return filas, crudos


def clave(r: dict) -> tuple:
    return (r["engine"], r["profile"], r["query_id"], r["concurrency"])


def rid_de(r: dict) -> str:
    return f"{r['engine']}_{r['profile']}_{r['query_id']}_c{r['concurrency']}_r{r['run_number']}"


def percentiles_sin_frias(raw: dict) -> tuple[object, int, int]:
    """P99 recalculado sin la primera consulta de cada worker (R-30.1, F7-e).

    Devuelve (percentiles, cuántas primeras consultas caían en la ventana, total en ventana).
    """
    w0, w1 = raw["ventana_ns"]["inicio"], raw["ventana_ns"]["fin"]
    primera: dict[int, int] = {}
    for s, _e, _ok, wid in raw["muestras"]:
        if wid not in primera or s < primera[wid]:
            primera[wid] = s
    en_ventana = [(s, e, wid) for s, e, ok, wid in raw["muestras"] if ok and w0 <= e <= w1]
    frias = [1 for s, _e, wid in en_ventana if primera.get(wid) == s]
    sin = [(e - s) / 1e6 for s, e, wid in en_ventana if primera.get(wid) != s]
    return percentiles.compute(sin), len(frias), len(en_ventana)


def celdas(filas: list[dict], crudos: dict) -> list[dict]:
    """Una entrada por celda, con las 3 repeticiones resumidas y lo que el reporte necesita."""
    porcelda: dict[tuple, list[dict]] = {}
    for r in filas:
        porcelda.setdefault(clave(r), []).append(r)
    out = []
    for k, rs in sorted(porcelda.items(), key=lambda kv: (kv[0][0], kv[0][1], kv[0][2], int(kv[0][3]))):
        rs = sorted(rs, key=lambda r: int(r["run_number"]))
        med = lambda col: [num(r[col]) for r in rs]  # noqa: E731
        vals = lambda col: [v for v in med(col) if v is not None]  # noqa: E731
        qps = vals("throughput_qps")
        # A4: si algún percentil quedó invalidado por censura, la celda se marca.
        censurada, completas, frias, total_vent = False, [], 0, 0
        p99_sin = []
        for r in rs:
            raw = crudos.get(rid_de(r))
            if not raw:
                continue
            cens = raw.get("censura", {})
            completas.append(cens.get("completadas_en_ventana") or 0)
            if any(not v for v in (cens.get("percentil_valido") or {}).values()):
                censurada = True
            p, f, t = percentiles_sin_frias(raw)
            frias += f
            total_vent += t
            if p.p99 is not None:
                p99_sin.append(p.p99)
        out.append({
            "engine": k[0], "profile": k[1], "query_id": k[2], "concurrency": int(k[3]),
            "motor": MOTOR_CORTO[k[0]], "perfil": PERFIL_CORTO[k[1]],
            "status": [r["status"] for r in rs],
            "medible": all(r["status"] in ("ok", "spill") for r in rs),
            "qps": statistics.fmean(qps) if qps else None,
            "p50": statistics.fmean(v) if (v := vals("latency_p50_ms")) else None,
            "p95": statistics.fmean(v) if (v := vals("latency_p95_ms")) else None,
            "p99": statistics.fmean(v) if (v := vals("latency_p99_ms")) else None,
            "p99_sin_frias": statistics.fmean(p99_sin) if p99_sin else None,
            "frias_en_ventana": frias, "completadas_en_ventana": total_vent,
            "throttling": statistics.fmean(v) if (v := vals("cpu_throttled_seconds")) else None,
            "rss": statistics.fmean(v) if (v := vals("max_rss_mb")) else None,
            "spill": any(r["disk_spill"] == "true" for r in rs),
            "censurada": censurada,
            "baja_densidad": bool(completas) and min(completas) < LOW_DENSITY_SAMPLES,
            "colapsada": k == CELDA_COLAPSADA,
        })
    return out


# Documentos que examina CADA consulta, tomados de los planes de results/explains/
# (SPEC A11). La asimetría de Q2 es el hallazgo R14: Mongo usa su índice de
# timestamp y examina la mitad; Postgres hace Seq Scan y examina la tabla entera.
DOCS_EXAMINADOS = {
    ("mongodb", "Q1"): 500_000,      # COLLSCAN: totalDocsExamined
    ("mongodb", "Q2"): 250_207,      # IXSCAN sobre timestamp: totalDocsExamined
    ("postgresql", "Q1"): 500_000,   # Seq Scan sobre la tabla entera
    ("postgresql", "Q2"): 500_000,   # Seq Scan: el planner no usa el índice de expresión
}


def docs_examinados(engine: str, query_id: str) -> int:
    return DOCS_EXAMINADOS[(engine, query_id)]


def dat(nombre: str, columnas: list[str], filas: list[list], comentario: str) -> None:
    d = REPORT / "datos"
    d.mkdir(parents=True, exist_ok=True)
    # El comentario va con '%', no con '#': pgfplots lee el archivo con TeX y '%' es
    # su carácter de comentario. Con '#' intentaría leer esa línea como datos.
    cuerpo = [f"% {comentario}", "% generado por scripts/build_report_data.py — no editar a mano",
              " ".join(columnas)]
    cuerpo += [" ".join("nan" if c is None else str(c) for c in f) for f in filas]
    (d / nombre).write_text("\n".join(cuerpo) + "\n")


def tabla(nombre: str, cuerpo: str) -> None:
    d = REPORT / "tablas"
    d.mkdir(parents=True, exist_ok=True)
    (d / nombre).write_text("% generado por scripts/build_report_data.py — no editar a mano\n" + cuerpo)


def cifras(valores: dict) -> None:
    d = REPORT / "cifras"
    d.mkdir(parents=True, exist_ok=True)
    lineas = ["% generado por scripts/build_report_data.py — no editar a mano"]
    for k, v in valores.items():
        lineas.append(f"\\newcommand{{\\{k}}}{{{v}}}")
    (d / "cifras.tex").write_text("\n".join(lineas) + "\n")


def main() -> int:
    filas, crudos = cargar()
    cs = celdas(filas, crudos)

    # --- figura 1: P99 contra concurrencia, dos series (R-30.1) --------------
    for motor in ("mongodb", "postgresql"):
        for q in sorted({c["query_id"] for c in cs}):
            sel = [c for c in cs if c["engine"] == motor and c["query_id"] == q]
            for perfil in ("PROFILE_A_BASELINE", "PROFILE_B_MEDIUM", "PROFILE_C_SEVERE"):
                p = [c for c in sel if c["profile"] == perfil]
                if not p:
                    continue
                dat(f"p99_{motor}_{q}_{PERFIL_CORTO[perfil]}.dat",
                    ["concurrencia", "p99_csv", "p99_sin_frias", "frias", "censurada", "colapsada"],
                    [[c["concurrency"], c["p99"], c["p99_sin_frias"], c["frias_en_ventana"],
                      int(c["censurada"]), int(c["colapsada"])] for c in sorted(p, key=lambda c: c["concurrency"])],
                    f"P99 (ms) de {MOTOR_CORTO[motor]} · {q} · {PERFIL_CORTO[perfil]}. "
                    "p99_csv = columna del CSV; p99_sin_frias = recalculado sin la primera consulta "
                    "de cada worker (R-30.1). censurada=1: percentiles invalidados por A4.")

    # --- figura 2: throttling contra throughput ------------------------------
    # Un archivo por motor y concurrencia: así la figura no necesita filtros de
    # pgfplots (`discard if not`), que son frágiles y fáciles de romper.
    for motor in ("mongodb", "postgresql"):
        for conc in (1, 10, 50):
            sel = [c for c in cs if c["engine"] == motor and c["concurrency"] == conc
                   and c["throttling"] is not None and c["qps"] is not None]
            dat(f"throttling_{motor}_c{conc}.dat",
                ["throttling_s", "qps", "perfil_num", "medible", "colapsada"],
                [[round(c["throttling"], 1), round(c["qps"], 4), "ABC".index(c["perfil"]) + 1,
                  int(c["medible"]), int(c["colapsada"])]
                 for c in sorted(sel, key=lambda c: c["perfil"])],
                f"Throttling (s por ventana de 300 s) contra throughput (qps) de "
                f"{MOTOR_CORTO[motor]} con c={conc}. perfil_num 1=A 2=B 3=C; "
                "medible=0 son celdas con filas error u oom.")

    # --- figura 3: curva de RSS de la serie de 1 s ---------------------------
    for c in cs:
        if c["concurrency"] != 50 or c["query_id"] != "Q2":
            continue
        rid = f"{c['engine']}_{c['profile']}_{c['query_id']}_c50_r1"
        raw = crudos.get(rid)
        if not raw or not (raw.get("serie_cgroup_1s") or {}).get("filas"):
            continue
        s = raw["serie_cgroup_1s"]
        col = s["columnas"]
        i0 = s["filas"][0][0]
        dat(f"rss_{c['engine']}_{c['perfil']}_Q2_c50.dat",
            ["t_s", "anon_mib", "working_set_mib", "shmem_mib"],
            [[round((f[0] - i0) / 1e9, 1), round(f[col.index("anon")] / 2**20, 1),
              round((f[col.index("memory_current")] - f[col.index("inactive_file")]) / 2**20, 1),
              round(f[col.index("shmem")] / 2**20, 1)] for f in s["filas"]],
            f"Curva de memoria de {MOTOR_CORTO[c['engine']]} · {c['perfil']} · Q2 · c=50 · r1, "
            "de la serie de 1 s del cgroup. anon es lo que mide max_rss_mb; working_set incluye "
            "la memoria compartida de Postgres (F6-A3, A11).")

    # --- tabla de resultados consolidados (sección 3) ------------------------
    lineas = []
    for c in cs:
        marca = ""
        if c["colapsada"]:
            marca = r"\tnotaColapsada{}"
        elif c["censurada"]:
            marca = r"\tnotaCensurada{}"
        elif c["baja_densidad"]:
            marca = r"\tnotaBajaDensidad{}"
        lineas.append(" & ".join([
            c["motor"], c["perfil"], c["query_id"].replace("_", r"\_"), str(c["concurrency"]),
            tex(c["qps"], 4), tex(c["p50"], 0), tex(c["p95"], 0), tex(c["p99"], 0),
            tex(c["throttling"], 1), tex(c["rss"], 1),
            "sí" if c["spill"] else "no",
            "/".join(sorted(set(c["status"]))) + marca]) + r" \\")
    tabla("resultados.tex", "\n".join(lineas) + "\n")

    # --- tabla de OOM con la distinción de R-29.1 ----------------------------
    oom_dentro, oom_calentamiento, oom_filas = 0, 0, []
    for r in filas:
        if r["status"] != "oom":
            continue
        raw = crudos.get(rid_de(r), {})
        cg = raw.get("cgroup", {})
        d = (cg.get("fin", {}).get("oom_kill") or 0) - (cg.get("inicio", {}).get("oom_kill") or 0)
        dentro = d > 0
        oom_dentro += dentro
        oom_calentamiento += not dentro
        oom_filas.append(" & ".join([
            MOTOR_CORTO[r["engine"]], PERFIL_CORTO[r["profile"]], r["query_id"].replace("_", r"\_"),
            r["concurrency"], r["run_number"], str(d),
            "en la ventana" if dentro else "en el calentamiento",
            str((raw.get("censura", {}) or {}).get("completadas_en_ventana")),
            "sí" if raw.get("estado_contenedor_final", {}).get("OOMKilled") else "no"]) + r" \\")
    tabla("oom.tex", "\n".join(oom_filas) + "\n")

    # --- M3: huella por 1 000 documentos examinados (A11) --------------------
    # El denominador sale de los PLANES, como pide SPEC A11, no de una suposición:
    #   MongoDB  → `totalDocsExamined` del explain;
    #   PostgreSQL → las filas que recorre el Seq Scan (la tabla entera).
    # Y ahí está la asimetría de R14: en Q2, Mongo examina 250 207 documentos porque
    # usa su índice de timestamp, y Postgres 500 000 porque hace Seq Scan. Comparar
    # "por documento" sin esto compararía dos trabajos distintos.
    m3 = []
    for c in cs:
        if not c["medible"] or not c["completadas_en_ventana"]:
            continue
        docs = docs_examinados(c["engine"], c["query_id"])
        rid = f"{c['engine']}_{c['profile']}_{c['query_id']}_c{c['concurrency']}_r1"
        raw = crudos.get(rid)
        ws, cpu_s = None, None
        if raw and (raw.get("serie_cgroup_1s") or {}).get("filas"):
            serie = raw["serie_cgroup_1s"]
            col, fls = serie["columnas"], serie["filas"]
            ws = max(f[col.index("memory_current")] - f[col.index("inactive_file")] for f in fls) / 2**20
            cpu_s = (fls[-1][col.index("usage_usec")] - fls[0][col.index("usage_usec")]) / 1e6
        completadas_r1 = (raw or {}).get("censura", {}).get("completadas_en_ventana") or 0
        miles = completadas_r1 * docs / 1000
        m3.append([c["motor"], c["perfil"], c["query_id"], c["concurrency"], docs, completadas_r1,
                   round(cpu_s, 1) if cpu_s else None,
                   round(cpu_s / miles * 1000, 4) if (cpu_s and miles) else None,
                   round(c["rss"], 1) if c["rss"] else None, round(ws, 1) if ws else None])
    dat("m3_huella.dat",
        ["motor", "perfil", "query", "concurrencia", "docs_examinados_por_consulta",
         "consultas_r1", "cpu_s_r1", "cpu_ms_por_mil_docs", "max_rss_mb", "working_set_mib"],
        [[v if not isinstance(v, str) else v.replace(" ", "") for v in f] for f in m3],
        "M3: huella por 1 000 documentos EXAMINADOS, con el denominador tomado de los planes "
        "(A11): Mongo Q1 500000, Mongo Q2 250207 (usa el índice), Postgres 500000 en las dos "
        "(Seq Scan). cpu_s_r1 es el tiempo de CPU del cgroup en la ventana de la repetición 1. "
        "Se dan las DOS memorias: max_rss_mb (anon, excluye los shared_buffers de Postgres) y "
        "working_set, que es con el que se interpreta la memoria (A11, F6-A3).")

    # --- cifras sueltas para el texto ---------------------------------------
    estados = {}
    for r in filas:
        estados[r["status"]] = estados.get(r["status"], 0) + 1
    spill_filas = [r for r in filas if r["disk_spill"] == "true"]
    temp_total = sum((crudos.get(rid_de(r), {}).get("spill", {}).get("delta", {}) or {}).get("temp_bytes", 0)
                     for r in spill_filas)
    cifras({
        "cifraFilasCsv": len(filas),
        "cifraCeldas": len(cs),
        "cifraFilasOk": estados.get("ok", 0),
        "cifraFilasSpill": estados.get("spill", 0),
        "cifraFilasError": estados.get("error", 0),
        "cifraFilasOom": estados.get("oom", 0),
        "cifraOomEnVentana": oom_dentro,
        "cifraOomEnCalentamiento": oom_calentamiento,
        "cifraFilasConSpill": len(spill_filas),
        "cifraTempTotalTB": f"{temp_total / 1e12:.2f}",
        "cifraCeldasMedibles": sum(1 for c in cs if c["medible"]),
        "cifraCeldasCensuradas": sum(1 for c in cs if c["censurada"]),
        "cifraDescartadas": 0 if not (RESULTS / "descartadas.csv").exists()
                            else sum(1 for _ in csv.DictReader((RESULTS / "descartadas.csv").open())),
    })

    print(f"celdas: {len(cs)} · filas: {len(filas)} · OOM en ventana: {oom_dentro}, "
          f"en calentamiento: {oom_calentamiento}")
    for sub in ("datos", "tablas", "cifras"):
        n = len(list((REPORT / sub).glob("*")))
        print(f"   report/{sub}/: {n} archivo(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
