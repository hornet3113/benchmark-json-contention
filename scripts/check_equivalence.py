#!/usr/bin/env python3
"""check_equivalence.py — equivalencia de Q1 y Q2 entre motores (F4, dentro de F3-G2).

Uso:
    python3 scripts/check_equivalence.py run     --gate g2 --engine mongo|postgres   (con el motor arriba)
    python3 scripts/check_equivalence.py compare --gate g2                           (sin motores)

`run` ejecuta las queries LEÍDAS DE queries/ (nunca embebidas aquí) en un motor,
con las variantes de Q2 del manual (§5.2):
    Mongo     Q1 · Q2 allowDiskUse:false · Q2 allowDiskUse:true
    Postgres  Q1 · Q2 work_mem='4MB'     · Q2 work_mem='64MB'   (con SHOW work_mem, R-17)
y captura sus planes (R-31) en results/explains/<gate>/, crudos.

`compare` calcula una REFERENCIA EXACTA en Python desde el archivo fuente
(Decimal, sin punto flotante) y compara contra ella a cada motor y cada variante
(G2-b). Criterios de PLAN F4:
    Q1  mismos grupos (country, category) · count exacto · totales y medias con
        diferencia relativa < 1e-6
    Q2  mismos 1 000 order_id como CONJUNTO (hay final_total repetidos dentro
        del Top-1000: el orden interno no es determinista) · vector ordenado de
        final_total con diferencia < 1e-6 · mismo customer_id por order_id
    Además, las dos variantes de cada motor deben devolver lo mismo (G2-d).

Salida: results/f3/<gate>/queries_<motor>.json, equivalence.json, y los planes.
Código de salida: 0 si todo cuadra; 1 si algo no; 2 si no se pudo ejecutar.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import subprocess
import sys
from datetime import datetime, timezone
from decimal import Decimal, getcontext
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import importlib.util  # noqa: E402

_spec = importlib.util.spec_from_file_location("capture_env", ROOT / "scripts" / "capture_env.py")
capture_env = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(capture_env)

getcontext().prec = 40
GATES = {"g1": 1_000, "g2": 10_000, "g3": 500_000}
TOLERANCE = Decimal("1e-6")  # PLAN F4
Q = ROOT / "queries"
QUERY_FILES = {
    ("mongo", "q1"): Q / "mongo" / "q1_unwind_group.json",
    ("mongo", "q2"): Q / "mongo" / "q2_sort_topk.json",
    ("postgres", "q1"): Q / "postgres" / "q1_unwind_group.sql",
    ("postgres", "q2"): Q / "postgres" / "q2_sort_topk.sql",
}
# Variantes de §5.2. Q1 no tiene variantes: se corre con la configuración por defecto.
VARIANTS = {
    "mongo": {"q1": [None], "q2": [False, True]},             # allowDiskUse
    "postgres": {"q1": [None], "q2": ["4MB", "64MB"]},        # work_mem
}
# Filtro de Q2 para la referencia: el mismo literal en sus dos formas, como lo usa
# cada motor (texto en Mongo, timestamptz en Postgres).
Q2_TS_TEXT = "2026-01-01T00:00:00Z"
Q2_TS = datetime(2026, 1, 1, tzinfo=timezone.utc)
Q2_LIMIT = 1000


def variant_name(engine: str, v) -> str:
    if v is None:
        return "default"
    return f"allowDiskUse_{str(v).lower()}" if engine == "mongo" else f"work_mem_{v}"


# --- referencia exacta (funciones puras) -------------------------------------

def iter_exact(path: Path):
    """Documentos uno a uno, con los números como Decimal exacto del texto JSON.

    Generador: con 500 000 documentos (G3) no se carga el archivo en memoria.
    """
    with path.open() as f:
        for line in f:
            yield json.loads(line, parse_float=Decimal)


def truths(docs) -> tuple[dict, dict]:
    """Referencia de Q1 y Q2 en UNA pasada sobre `docs` (cualquier iterable)."""
    acc: dict[tuple, list] = {}
    q2_rows = []
    for d in docs:
        country = d["customer"]["geo"]["country"]
        for it in d["items"]:
            if Decimal(it["price"]) > 50:
                g = acc.setdefault((country, it["category"]), [Decimal(0), 0])
                g[0] += Decimal(it["qty"]) * Decimal(it["price"])
                g[1] += 1
        if q2_filter(d):
            q2_rows.append(_q2_row(d))
    q1 = {k: {"total": t, "avg": t / n, "count": n} for k, (t, n) in acc.items()}
    return q1, _q2_from_rows(q2_rows)


def _q2_row(d: dict) -> tuple:
    return d["order_id"], d["customer"]["id"], Decimal(d["payment"]["final_total"])


def truth_q1(docs) -> dict:
    """{(country, category): {"total": Decimal, "avg": Decimal, "count": int}}"""
    return truths(docs)[0]


def q2_filter(d: dict) -> bool:
    """Filtro de Q2. Se evalúa de las dos formas y deben coincidir (trampa 1 de F2)."""
    if d["payment"]["status"] != "completed":
        return False
    as_text = d["timestamp"] >= Q2_TS_TEXT
    as_time = datetime.fromisoformat(d["timestamp"].replace("Z", "+00:00")) >= Q2_TS
    if as_text != as_time:
        raise ValueError(f"filtro de texto y de tiempo discrepan en {d['order_id']}: {d['timestamp']}")
    return as_text


def truth_q2(docs) -> dict:
    """Solo Q2: no depende de los campos que usa Q1."""
    return _q2_from_rows([_q2_row(d) for d in docs if q2_filter(d)])


def _q2_from_rows(rows: list[tuple]) -> dict:
    rows = sorted(rows, key=lambda r: r[2], reverse=True)
    top = rows[:Q2_LIMIT]
    boundary = None
    if len(rows) > Q2_LIMIT:
        boundary = {"fila_k": str(rows[Q2_LIMIT - 1][2]), "fila_k_mas_1": str(rows[Q2_LIMIT][2]),
                    "empate": rows[Q2_LIMIT - 1][2] == rows[Q2_LIMIT][2]}
    return {"filas_filtro": len(rows), "top": top, "frontera": boundary,
            "repetidos_dentro_del_top": len(top) - len({r[2] for r in top})}


def rel_diff(value, truth: Decimal) -> Decimal:
    """|valor − verdad| / |verdad|. Un float se convierte a su valor binario exacto.

    Se muestra con float(...): un cero Decimal formateado con .3e da "0.000e+3",
    que parece 1000 y es 0.
    """
    v = Decimal(value) if not isinstance(value, Decimal) else value
    return abs(v - truth) / abs(truth) if truth else abs(v)


def compare_q1(truth: dict, rows: dict) -> dict:
    missing = sorted(set(truth) - set(rows))
    extra = sorted(set(rows) - set(truth))
    common = set(truth) & set(rows)
    count_bad = sorted(k for k in common if rows[k]["count"] != truth[k]["count"])
    max_total = max((rel_diff(rows[k]["total"], truth[k]["total"]) for k in common), default=Decimal(0))
    max_avg = max((rel_diff(rows[k]["avg"], truth[k]["avg"]) for k in common), default=Decimal(0))
    ok = not missing and not extra and not count_bad and max_total < TOLERANCE and max_avg < TOLERANCE
    return {"grupos_referencia": len(truth), "grupos_motor": len(rows),
            "faltan": [list(k) for k in missing], "sobran": [list(k) for k in extra],
            "count_distinto": [list(k) for k in count_bad],
            "max_dif_rel_total_revenue": f"{float(max_total):.3e}", "max_dif_rel_avg_revenue": f"{float(max_avg):.3e}",
            "ok": ok}


def compare_q2(truth_top: list[tuple], rows: list[tuple]) -> dict:
    t_ids = {r[0] for r in truth_top}
    e_ids = {r[0] for r in rows}
    t_cust = {r[0]: r[1] for r in truth_top}
    cust_bad = sum(1 for oid, cust, _ in rows if oid in t_cust and t_cust[oid] != cust)
    t_vec = sorted((r[2] for r in truth_top), reverse=True)
    e_vec = sorted((r[2] for r in rows), reverse=True)
    max_vec = (max((rel_diff(e, t) for e, t in zip(e_vec, t_vec)), default=Decimal(0))
               if len(e_vec) == len(t_vec) else None)
    ok = (len(rows) == len(truth_top) and e_ids == t_ids and cust_bad == 0
          and max_vec is not None and max_vec < TOLERANCE)
    return {"filas": len(rows), "filas_referencia": len(truth_top),
            "conjunto_igual": e_ids == t_ids, "faltan": len(t_ids - e_ids), "sobran": len(e_ids - t_ids),
            "customer_id_distinto": cust_bad,
            "max_dif_rel_vector_final_total": None if max_vec is None else f"{float(max_vec):.3e}",
            "ok": ok}


def same_result(a, b) -> bool:
    """¿Devuelven dos variantes lo mismo? Q2 como conjunto de filas; Q1 como dict."""
    if isinstance(a, list):
        return sorted(map(tuple, a)) == sorted(map(tuple, b))
    return a == b


# --- resúmenes de planes (funciones puras) ------------------------------------

def _walk(node):
    if isinstance(node, dict):
        yield node
        for v in node.values():
            yield from _walk(v)
    elif isinstance(node, list):
        for v in node:
            yield from _walk(v)


def mongo_plan_summary(explain: dict) -> dict:
    stages, indexes, used_disk = [], set(), False
    docs = keys = 0
    for n in _walk(explain):
        if isinstance(n.get("stage"), str) and n["stage"] not in stages:
            stages.append(n["stage"])
        if isinstance(n.get("indexName"), str):
            indexes.add(n["indexName"])
        used_disk |= n.get("usedDisk") is True
        docs = max(docs, n.get("totalDocsExamined", 0) if isinstance(n.get("totalDocsExamined"), int) else 0)
        keys = max(keys, n.get("totalKeysExamined", 0) if isinstance(n.get("totalKeysExamined"), int) else 0)
    pipeline = [next(iter(s)) for s in explain.get("stages", []) if isinstance(s, dict) and s]
    return {"etapas_plan": stages, "etapas_pipeline": pipeline, "indices_usados": sorted(indexes),
            "usa_indice": bool(indexes), "usedDisk": used_disk,
            "totalDocsExamined": docs, "totalKeysExamined": keys}


def _own_temp(node: dict, out: list) -> None:
    """Bloques temporales que escribe cada nodo POR SÍ MISMO.

    En EXPLAIN (BUFFERS) cada nodo informa sus contadores INCLUYENDO los de sus
    hijos. El propio es el suyo menos la suma de los de sus hijos directos.
    """
    children = node.get("Plans", [])
    own = (node.get("Temp Written Blocks", 0) or 0) - sum(c.get("Temp Written Blocks", 0) or 0 for c in children)
    if own:
        out.append({"nodo": node["Node Type"], "temp_written_blocks_propios": own})
    for c in children:
        _own_temp(c, out)


def pg_plan_summary(explain: list) -> dict:
    root = explain[0]
    plan = root["Plan"]
    nodes, indexes, sorts = [], set(), []
    for n in _walk(plan):
        if "Node Type" in n and n["Node Type"] not in nodes:
            nodes.append(n["Node Type"])
        if "Index Name" in n:
            indexes.add(n["Index Name"])
        if "Sort Method" in n:
            sorts.append({k: n.get(k) for k in ("Sort Method", "Sort Space Used", "Sort Space Type")})
    own: list[dict] = []
    _own_temp(plan, own)
    # Total = el del nodo raíz, que ya incluye a todos sus descendientes. Hasta el
    # 2026-11-01 aquí se SUMABAN todos los nodos, y eso contaba varias veces lo mismo.
    temp = plan.get("Temp Written Blocks", 0) or 0
    return {"nodos": nodes, "indices_usados": sorted(indexes), "usa_indice": bool(indexes),
            "ordenamientos": sorts, "temp_written_blocks": temp,
            "temp_written_mib": round(temp * 8192 / 2**20, 1),
            "temp_por_nodo": own,
            "execution_time_ms": root.get("Execution Time")}


def summarize(gate: str) -> dict:
    """Recalcula los resúmenes desde los planes crudos guardados, sin tocar los motores."""
    explains = ROOT / "results" / "explains" / gate
    out = {"gate": gate, "fecha_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
           "fuente": str(explains.relative_to(ROOT)), "planes": {}}
    for f in sorted(explains.glob("*.json")):
        plan = json.loads(f.read_text())
        engine = f.stem.split("_", 1)[0]
        out["planes"][f.stem] = mongo_plan_summary(plan) if engine == "mongo" else pg_plan_summary(plan)
    return out


def parse_pg_csv(text: str) -> tuple[str | None, list[dict]]:
    """Salida de `psql --csv` con SHOW work_mem delante: (work_mem, filas)."""
    lines = text.splitlines()
    work_mem = None
    if lines and lines[0] == "work_mem":
        work_mem, lines = lines[1], lines[2:]
    return work_mem, list(csv.DictReader(io.StringIO("\n".join(lines))))


# --- ejecución en los motores ------------------------------------------------

def sh(cmd: list[str], what: str, stdin: str | None = None) -> str:
    res = subprocess.run(cmd, input=stdin, capture_output=True, text=True, timeout=3600)
    if res.returncode != 0:
        raise RuntimeError(f"{what}: exit={res.returncode} {res.stderr.strip()[-500:]}")
    return res.stdout.replace("\r", "")


def run_mongo(env: dict, query: str, text: str, allow_disk) -> tuple[object, dict]:
    opts = "{}" if allow_disk is None else "{allowDiskUse: %s}" % str(allow_disk).lower()
    base = ["docker", "exec", "bench_mongo", "mongosh", "--quiet", env["MONGO_DB"], "--eval"]
    # El pipeline es el texto del archivo tal cual: JSON es JS válido.
    res = json.loads(sh([*base, f"print(EJSON.stringify(db.orders.aggregate({text}, {opts}).toArray()))"],
                        f"mongo {query}").strip().splitlines()[-1])
    plan = json.loads(sh([*base, f'print(EJSON.stringify(db.orders.explain("executionStats").aggregate({text}, {opts})))'],
                         f"explain mongo {query}").strip().splitlines()[-1])
    if query == "q1":
        rows = {f"{r['_id']['country']}|{r['_id']['category']}":
                {"total": r["total_revenue"], "avg": r["avg_revenue"], "count": r["count"]} for r in res}
    else:
        rows = [[r["order_id"], r["customer"]["id"], r["payment"]["final_total"]] for r in res]
    return rows, plan


def run_pg(env: dict, query: str, text: str, work_mem) -> tuple[object, dict, str]:
    base = ["docker", "exec", "-i", "bench_postgres", "psql", "-X", "-q", "-v", "ON_ERROR_STOP=1",
            "-U", env["POSTGRES_USER"], "-d", env["POSTGRES_DB"]]
    pre = [] if work_mem is None else ["-c", f"SET work_mem = '{work_mem}'"]
    # La query se pasa por stdin tal cual está en el archivo (-f -).
    out = sh([*base, "--csv", *pre, "-c", "SHOW work_mem", "-f", "-"], f"postgres {query}", stdin=text)
    shown, rows_raw = parse_pg_csv(out)
    plan = json.loads(sh([*base, "-tA", *pre, "-c", "EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + text],
                         f"explain postgres {query}"))
    if query == "q1":
        rows = {f"{r['country']}|{r['category']}":
                {"total": r["total_revenue"], "avg": r["avg_revenue"], "count": int(r["count"])} for r in rows_raw}
    else:
        rows = [[r["order_id"], r["customer_id"], r["final_total"]] for r in rows_raw]
    return rows, plan, shown


def run_engine(gate: str, engine: str) -> dict:
    env = capture_env.load_env_file(ROOT / "docker" / "images.env")
    explains = ROOT / "results" / "explains" / gate
    explains.mkdir(parents=True, exist_ok=True)
    out = {"gate": gate, "engine": engine, "fecha_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
           "queries": {}}
    for query in ("q1", "q2"):
        path = QUERY_FILES[(engine, query)]
        text = path.read_text()
        for v in VARIANTS[engine][query]:
            name = f"{query}_{variant_name(engine, v)}"
            if engine == "mongo":
                rows, plan = run_mongo(env, query, text, v)
                shown, summary = None, mongo_plan_summary(plan)
            else:
                rows, plan, shown = run_pg(env, query, text, v)
                summary = pg_plan_summary(plan)
            plan_file = explains / f"{engine}_{name}.json"
            plan_file.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n")
            out["queries"][name] = {"archivo_query": str(path.relative_to(ROOT)), "work_mem_mostrado": shown,
                                    "filas": len(rows), "resultado": rows,
                                    "plan": str(plan_file.relative_to(ROOT)), "plan_resumen": summary}
    try:
        out["entorno"] = capture_env.capture(engine, env)
    except LookupError as exc:
        out["entorno"] = {"error": str(exc)}
    return out


def _as_q1(rows: dict) -> dict:
    return {tuple(k.split("|")): {"total": Decimal(str(v["total"])) if isinstance(v["total"], str) else v["total"],
                                  "avg": Decimal(v["avg"]) if isinstance(v["avg"], str) else v["avg"],
                                  "count": v["count"]} for k, v in rows.items()}


def _as_q2(rows: list) -> list[tuple]:
    return [(oid, cust, Decimal(ft) if isinstance(ft, str) else ft) for oid, cust, ft in rows]


def compare(gate: str) -> dict:
    t1, t2 = truths(iter_exact(ROOT / "data" / f"orders_{GATES[gate]}_seed42.jsonl"))
    d = ROOT / "results" / "f3" / gate
    engines = {e: json.loads((d / f"queries_{e}.json").read_text()) for e in ("mongo", "postgres")}

    result = {"gate": gate, "fecha_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
              "referencia": {"q1_grupos": len(t1), "q2_filas_filtro": t2["filas_filtro"],
                             "q2_frontera_top_k": t2["frontera"],
                             "q2_valores_repetidos_dentro_del_top": t2["repetidos_dentro_del_top"]},
              "q1": {}, "q2": {}, "variantes_iguales": {}, "planes": {}}
    for engine, data in engines.items():
        qs = data["queries"]
        for name, q in qs.items():
            if name.startswith("q1"):
                result["q1"][f"{engine}:{name}"] = compare_q1(t1, _as_q1(q["resultado"]))
            else:
                result["q2"][f"{engine}:{name}"] = compare_q2(t2["top"], _as_q2(q["resultado"]))
            result["planes"][f"{engine}:{name}"] = {**q["plan_resumen"], "work_mem_mostrado": q["work_mem_mostrado"]}
        q2s = [qs[n]["resultado"] for n in qs if n.startswith("q2")]
        result["variantes_iguales"][engine] = all(same_result(q2s[0], x) for x in q2s[1:])
    result["ok"] = (all(v["ok"] for v in result["q1"].values()) and all(v["ok"] for v in result["q2"].values())
                    and all(result["variantes_iguales"].values()))
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--gate", required=True, choices=GATES)
    r.add_argument("--engine", required=True, choices=VARIANTS)
    c = sub.add_parser("compare")
    c.add_argument("--gate", required=True, choices=GATES)
    c.add_argument("--out", type=Path, help="archivo de salida (por defecto results/f3/<gate>/equivalence.json)")
    m = sub.add_parser("summarize", help="recalcula los resúmenes de planes desde results/explains/<gate>/")
    m.add_argument("--gate", required=True, choices=GATES)
    args = parser.parse_args(argv)

    outdir = ROOT / "results" / "f3" / args.gate
    outdir.mkdir(parents=True, exist_ok=True)
    try:
        if args.cmd == "summarize":
            data = summarize(args.gate)
            out = outdir / "plan_summary.json"
            out.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
            for name, sm in data["planes"].items():
                extra = (f"temp={sm['temp_written_blocks']} bloques ({sm['temp_written_mib']} MiB) por nodo={sm['temp_por_nodo']}"
                         if "temp_written_blocks" in sm else f"usedDisk={sm['usedDisk']} índices={sm['indices_usados']}")
                print(f"   {name:<34} {extra}")
            print(f"   -> {out.relative_to(ROOT)}")
            return 0
        if args.cmd == "run":
            data = run_engine(args.gate, args.engine)
            out = outdir / f"queries_{args.engine}.json"
            out.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str) + "\n")
            print(f"== queries {args.gate} / {args.engine}")
            for name, q in data["queries"].items():
                print(f"   {name:<24} filas={q['filas']:<5} work_mem={q['work_mem_mostrado']}  plan={json.dumps(q['plan_resumen'], ensure_ascii=False)}")
            print(f"   -> {out.relative_to(ROOT)}")
            return 0
        data = compare(args.gate)
    except (RuntimeError, FileNotFoundError, KeyError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    out = (args.out or outdir / "equivalence.json").resolve()
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str) + "\n")
    ref = data["referencia"]
    print(f"== equivalencia {args.gate}: referencia Q1={ref['q1_grupos']} grupos · Q2 filtro={ref['q2_filas_filtro']} filas"
          f" · frontera={ref['q2_frontera_top_k']} · repetidos en el top={ref['q2_valores_repetidos_dentro_del_top']}")
    for k, v in data["q1"].items():
        print(f"   {'OK   ' if v['ok'] else 'FALLA'} {k:<34} grupos={v['grupos_motor']}/{v['grupos_referencia']}"
              f" faltan={len(v['faltan'])} sobran={len(v['sobran'])} count≠={len(v['count_distinto'])}"
              f" maxrel(total)={v['max_dif_rel_total_revenue']} maxrel(avg)={v['max_dif_rel_avg_revenue']}")
    for k, v in data["q2"].items():
        print(f"   {'OK   ' if v['ok'] else 'FALLA'} {k:<34} filas={v['filas']} conjunto_igual={v['conjunto_igual']}"
              f" faltan={v['faltan']} sobran={v['sobran']} customer≠={v['customer_id_distinto']}"
              f" maxrel(vector)={v['max_dif_rel_vector_final_total']}")
    print(f"   variantes de Q2 con el mismo resultado: {data['variantes_iguales']}")
    shown = out.relative_to(ROOT) if out.is_relative_to(ROOT) else out
    print(f"   {'RESULTADO: OK' if data['ok'] else 'RESULTADO: FALLA'}  ->  {shown}")
    return 0 if data["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
