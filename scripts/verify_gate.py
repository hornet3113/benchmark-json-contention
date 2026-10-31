#!/usr/bin/env python3
"""verify_gate.py — verificaciones de una compuerta de carga de F3 (G1/G2/G3).

Uso:
    python3 scripts/verify_gate.py export  --gate g1 --engine mongo|postgres   (con el motor arriba)
    python3 scripts/verify_gate.py compare --gate g1                           (sin motores)

`export` lee DESDE EL MOTOR: conteo, tipos con $type / jsonb_typeof, id = order_id
(Postgres), order_id repetidos, índices, evidencia de R-01/R-03 y el entorno
(capture_env.py). Exporta además todos los documentos a data/exports/ para comparar.

`compare` valida el 100 % de lo exportado con generator/schema.py y compara en
TRES DIRECCIONES, documento por documento: archivo fuente = Mongo = Postgres (F3-e).
No necesita ningún motor arriba: solo un motor corre a la vez (CLAUDE.md).

Salida: results/f3/<gate>/export_<motor>.json y compare.json.
Código de salida: 0 si todo cuadra; 1 si algo no; 2 si no se pudo ejecutar.
Solo biblioteca estándar: no hacen falta drivers en el host.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import subprocess
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from generator import schema  # noqa: E402

_spec = importlib.util.spec_from_file_location("capture_env", ROOT / "scripts" / "capture_env.py")
capture_env = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(capture_env)

GATES = {"g1": 1_000, "g2": 10_000, "g3": 500_000}
CONTAINERS = {"mongo": "bench_mongo", "postgres": "bench_postgres"}
MAX_EXAMPLES = 5


# --- funciones puras (probadas en tests/test_verify_gate.py) ----------------

def strip_mongo_id(doc: dict) -> dict:
    """mongoimport agrega _id (ObjectId); no es parte del documento del manual."""
    return {k: v for k, v in doc.items() if k != "_id"}


def first_difference(a, b, path: str = "$") -> str | None:
    """Ruta de la primera diferencia entre dos valores JSON, o None si son iguales.

    Ignora el orden de claves (JSONB reordena), pero NO el tipo: 31.16 frente a
    "31.16" es una diferencia. 12 frente a 12.0 se considera igual, como en JSON;
    el tipo exacto del motor se revisa aparte con $type / jsonb_typeof.
    """
    if isinstance(a, bool) or isinstance(b, bool):
        return None if (type(a) is type(b) and a == b) else path
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return None if a == b else path
    if type(a) is not type(b):
        return path
    if isinstance(a, dict):
        for k in sorted(set(a) | set(b)):
            if k not in a or k not in b:
                return f"{path}.{k}"
            d = first_difference(a[k], b[k], f"{path}.{k}")
            if d:
                return d
        return None
    if isinstance(a, list):
        if len(a) != len(b):
            return f"{path}[len]"
        for i, (x, y) in enumerate(zip(a, b)):
            d = first_difference(x, y, f"{path}[{i}]")
            if d:
                return d
        return None
    return None if a == b else path


def three_way(source: dict, mongo: dict, pg: dict) -> dict:
    """Compara tres {order_id: documento} en memoria. Es la versión con la que se
    produjo la evidencia de G1 y G2; desde G3, compare() usa canonical_digest()
    en streaming con la misma regla de igualdad (y se probó que da lo mismo)."""
    ids = set(source) | set(mongo) | set(pg)
    result = {"fuente": len(source), "mongo": len(mongo), "postgres": len(pg),
              "iguales_en_los_tres": 0, "faltan_en": {"fuente": 0, "mongo": 0, "postgres": 0},
              "distintos": {"mongo": 0, "postgres": 0}, "ejemplos": []}
    for oid in sorted(ids):
        present = {"fuente": oid in source, "mongo": oid in mongo, "postgres": oid in pg}
        for name, ok in present.items():
            result["faltan_en"][name] += not ok
        if not all(present.values()):
            if len(result["ejemplos"]) < MAX_EXAMPLES:
                result["ejemplos"].append({"order_id": oid, "falta_en": [n for n, ok in present.items() if not ok]})
            continue
        diffs = {name: first_difference(source[oid], doc[oid]) for name, doc in (("mongo", mongo), ("postgres", pg))}
        for name, d in diffs.items():
            result["distintos"][name] += d is not None
        if not any(diffs.values()):
            result["iguales_en_los_tres"] += 1
        elif len(result["ejemplos"]) < MAX_EXAMPLES:
            result["ejemplos"].append({"order_id": oid, "primera_diferencia": {n: d for n, d in diffs.items() if d}})
    result["ok"] = result["iguales_en_los_tres"] == len(ids) == len(source)
    return result


def index_mentions(index_texts: list[str], field: str = "final_total") -> list[str]:
    """Índices cuya definición menciona un campo (R-15: ninguno sobre final_total)."""
    return [t for t in index_texts if field in t]


def _canon(v):
    if isinstance(v, dict):
        return {k: _canon(x) for k, x in v.items()}
    if isinstance(v, list):
        return [_canon(x) for x in v]
    if isinstance(v, Decimal):
        # Número normalizado y marcado como número: 12 = 12.0, pero 31.16 ≠ "31.16".
        return {"$n": str(v.normalize())}
    return v  # str, bool, None: bool no es número (true ≠ 1)


def canonical_digest(line: str | bytes, *, drop_mongo_id: bool = False) -> tuple[str, bytes]:
    """(order_id, huella) de una línea JSON, para comparar sin cargar el dataset.

    Misma regla que first_difference: ignora el orden de claves y la forma de
    escribir un número (12 frente a 12.0), pero no el tipo (número frente a texto,
    booleano frente a entero). Usada en compare(): con 500 000 documentos, tener
    los tres conjuntos en memoria no cabría en la VM (G3).
    """
    doc = json.loads(line, parse_float=Decimal, parse_int=Decimal)
    if drop_mongo_id:
        doc = strip_mongo_id(doc)
    blob = json.dumps(_canon(doc), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return doc["order_id"], hashlib.sha1(blob.encode()).digest()


# --- acceso a los motores ---------------------------------------------------

def sh(cmd: list[str], what: str, stdin: bytes | None = None) -> str:
    res = subprocess.run(cmd, input=stdin, capture_output=True, timeout=1800)
    if res.returncode != 0:
        raise RuntimeError(f"{what}: exit={res.returncode} {res.stderr.decode(errors='replace').strip()}")
    return res.stdout.decode().replace("\r", "")


def sh_to_file(cmd: list[str], what: str, path: Path) -> tuple[int, str]:
    """Ejecuta un comando volcando su salida directo a disco. Devuelve (líneas, sha256).

    Con 500 000 documentos la exportación pesa ~500 MB: no se guarda en memoria.
    """
    with path.open("wb") as f:
        res = subprocess.run(cmd, stdout=f, stderr=subprocess.PIPE, timeout=3600)
    if res.returncode != 0:
        raise RuntimeError(f"{what}: exit={res.returncode} {res.stderr.decode(errors='replace').strip()}")
    digest, lines = hashlib.sha256(), 0
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
            lines += chunk.count(b"\n")
    return lines, digest.hexdigest()


def mongo_json(env: dict, js: str, what: str):
    """Ejecuta JS en mongosh y devuelve lo que imprima como JSON."""
    out = sh(["docker", "exec", CONTAINERS["mongo"], "mongosh", "--quiet", env["MONGO_DB"],
              "--eval", f"print(JSON.stringify({js}))"], what)
    return json.loads(out.strip().splitlines()[-1])


def pg_json(env: dict, sql: str, what: str):
    """Ejecuta SQL que devuelve un único valor JSON y lo decodifica."""
    out = sh(["docker", "exec", CONTAINERS["postgres"], "psql", "-X", "-v", "ON_ERROR_STOP=1", "-tA",
              "-U", env["POSTGRES_USER"], "-d", env["POSTGRES_DB"], "-c", sql], what)
    return json.loads(out.strip() or "null")


MONGO_DOC_TYPES = """db.orders.aggregate([{$group: {_id: {
    order_id: {$type: "$order_id"}, timestamp: {$type: "$timestamp"},
    final_total: {$type: "$payment.final_total"}}, n: {$sum: 1}}}]).toArray()"""
MONGO_ITEM_TYPES = """db.orders.aggregate([{$unwind: "$items"}, {$group: {_id: {
    price: {$type: "$items.price"}, qty: {$type: "$items.qty"}}, n: {$sum: 1}}}]).toArray()"""
MONGO_DUPLICATES = """db.orders.aggregate([{$group: {_id: "$order_id", n: {$sum: 1}}},
    {$match: {n: {$gt: 1}}}, {$count: "repetidos"}]).toArray()"""
MONGO_R01 = """(() => { const s = db.orders.aggregate([{$collStats: {storageStats: {}}}]).toArray()[0];
    const h = db.hello();
    return {storage_engine: db.serverStatus().storageEngine.name,
            storageStats_tiene_wiredTiger: "wiredTiger" in s.storageStats,
            hello_msg: h.msg || null, es_mongos: h.msg === "isdbgrid", replica_set: h.setName || null,
            coleccion: db.getCollectionNames().includes("orders")}; })()"""

MONGO_SIZES = """(() => { const s = db.orders.aggregate([{$collStats: {storageStats: {}}}]).toArray()[0].storageStats;
    return {documentos: s.count, datos_sin_comprimir_bytes: s.size, tamano_medio_documento_bytes: s.avgObjSize,
            datos_en_disco_bytes: s.storageSize, indices_bytes: s.totalIndexSize,
            por_indice_bytes: s.indexSizes, total_bytes: s.totalSize}; })()"""
PG_SIZES = """SELECT json_build_object(
    'tabla_bytes', pg_table_size('orders'), 'indices_bytes', pg_indexes_size('orders'),
    'total_bytes', pg_total_relation_size('orders'), 'base_de_datos_bytes', pg_database_size(current_database()))"""
DATA_DIRS = {"mongo": "/data/db", "postgres": "/var/lib/postgresql/data/pgdata"}

PG_DOC_TYPES = """SELECT json_agg(t) FROM (SELECT jsonb_typeof(data->'order_id') AS order_id,
    jsonb_typeof(data->'timestamp') AS "timestamp",
    jsonb_typeof(data->'payment'->'final_total') AS final_total, count(*) AS n
    FROM orders GROUP BY 1, 2, 3) t"""
PG_ITEM_TYPES = """SELECT json_agg(t) FROM (SELECT jsonb_typeof(i->'price') AS price,
    jsonb_typeof(i->'qty') AS qty, count(*) AS n
    FROM orders, jsonb_array_elements(data->'items') AS i GROUP BY 1, 2) t"""
PG_ID_CHECK = """SELECT json_build_object(
    'filas', count(*),
    'id_distinto_de_order_id', count(*) FILTER (WHERE id::text IS DISTINCT FROM data->>'order_id'),
    'order_id_repetidos', count(*) - count(DISTINCT data->>'order_id')) FROM orders"""
PG_INDEXES = """SELECT json_agg(t ORDER BY indexname) FROM (SELECT indexname, indexdef,
    pg_relation_size(indexname::regclass) AS bytes FROM pg_indexes WHERE tablename = 'orders') t"""


def export_engine(gate: str, engine: str) -> dict:
    env = capture_env.load_env_file(ROOT / "docker" / "images.env")
    expected = GATES[gate]
    exports = ROOT / "data" / "exports"
    exports.mkdir(parents=True, exist_ok=True)
    out_file = exports / f"{gate}_{engine}.jsonl"
    container = CONTAINERS[engine]

    if engine == "mongo":
        count = int(sh(["docker", "exec", container, "mongosh", "--quiet", env["MONGO_DB"],
                        "--eval", "db.orders.countDocuments()"], "conteo").strip())
        lines, sha = sh_to_file(["docker", "exec", container, "mongoexport", "--quiet",
                                 "--db", env["MONGO_DB"], "--collection", "orders"], "mongoexport", out_file)
        result = {
            "tipos_documento": mongo_json(env, MONGO_DOC_TYPES, "tipos documento"),
            "tipos_items": mongo_json(env, MONGO_ITEM_TYPES, "tipos items"),
            "order_id_repetidos": (mongo_json(env, MONGO_DUPLICATES, "repetidos") or [{"repetidos": 0}])[0]["repetidos"],
            "indices": mongo_json(env, "db.orders.getIndexes()", "índices"),
            "r01": mongo_json(env, MONGO_R01, "R-01"),
            "tamano_en_disco": mongo_json(env, MONGO_SIZES, "tamaños"),
        }
        index_texts = [json.dumps(i["key"]) for i in result["indices"]]
    else:
        psql = ["docker", "exec", container, "psql", "-X", "-v", "ON_ERROR_STOP=1",
                "-U", env["POSTGRES_USER"], "-d", env["POSTGRES_DB"]]
        count = int(sh([*psql, "-tAc", "SELECT count(*) FROM orders"], "conteo").strip())
        lines, sha = sh_to_file([*psql, "-c", "COPY (SELECT data FROM orders) TO STDOUT"], "COPY TO STDOUT", out_file)
        id_check = pg_json(env, PG_ID_CHECK, "id = order_id")
        result = {
            "tipos_documento": pg_json(env, PG_DOC_TYPES, "tipos documento"),
            "tipos_items": pg_json(env, PG_ITEM_TYPES, "tipos items"),
            "order_id_repetidos": id_check["order_id_repetidos"],
            "id_igual_a_order_id": id_check,
            "indices": pg_json(env, PG_INDEXES, "índices"),
            "r03_tabla": sh([*psql, "-c", r"\d+ orders"], r"\d+ orders"),
            "tamano_en_disco": pg_json(env, PG_SIZES, "tamaños"),
        }
        index_texts = [i["indexdef"] for i in result["indices"]]

    # Todo lo que ocupa el directorio de datos del motor (incluye journal/WAL y catálogos).
    du = sh(["docker", "exec", container, "du", "-sb", DATA_DIRS[engine]], "du").split()[0]
    result["tamano_en_disco"]["directorio_de_datos_du_bytes"] = int(du)
    r15 = index_mentions(index_texts)
    checks = {
        "conteo_esperado": count == expected,
        "export_completo": lines == expected,
        "sin_order_id_repetidos": result["order_id_repetidos"] == 0,
        "r15_sin_indice_final_total": not r15,
    }
    if engine == "postgres":
        checks["id_igual_a_order_id"] = result["id_igual_a_order_id"]["id_distinto_de_order_id"] == 0
    try:
        environment = capture_env.capture(engine, env)
    except LookupError as exc:
        environment = {"error": str(exc)}

    return {
        "gate": gate, "engine": engine,
        "fecha_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "esperado": expected, "conteo": count,
        "export": {"archivo": str(out_file.relative_to(ROOT)), "lineas": lines,
                   "sha256": sha},
        **result,
        "r15_indices_con_final_total": r15,
        "comprobaciones": checks,
        "ok": all(checks.values()),
        "entorno": environment,
    }


def compare(gate: str) -> dict:
    """Validación al 100 % y comparación en tres direcciones, leyendo línea a línea.

    En memoria solo queda {order_id: huella} del archivo fuente (~80 MB con
    500 000), no los documentos. Hasta G2 se comparaban los documentos completos
    en memoria (three_way); con G3 no cabría en la VM. La regla de igualdad es la
    misma: canonical_digest() aplica la de first_difference().
    """
    exports = ROOT / "data" / "exports"
    src_path = ROOT / "data" / f"orders_{GATES[gate]}_seed42.jsonl"
    result = compare_files(src_path, exports / f"{gate}_mongo.jsonl", exports / f"{gate}_postgres.jsonl")
    return {"gate": gate, "fecha_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "archivo_fuente": str(src_path.relative_to(ROOT)), **result}


def compare_files(src_path: Path, mongo_path: Path, pg_path: Path) -> dict:
    """Núcleo de compare(), separado para poder probarlo con archivos fabricados."""
    engines = (("mongo", mongo_path, 1, True), ("postgres", pg_path, 2, False))
    validation: dict[str, dict] = {}

    def check(name: str, doc: dict, strict: bool) -> None:
        v = validation.setdefault(name, {"validados": 0, "invalidos": 0, "ejemplos": []})
        v["validados"] += 1
        errors = schema.validate_record(doc, strict_order=strict)
        if errors:
            v["invalidos"] += 1
            if len(v["ejemplos"]) < MAX_EXAMPLES:
                v["ejemplos"].append({"order_id": doc.get("order_id"), "errores": errors})

    source: dict[str, bytes] = {}
    with src_path.open() as f:
        for line in f:
            check("fuente (orden estricto)", json.loads(line), True)
            oid, digest = canonical_digest(line)
            source[oid] = digest

    # Por order_id: bit 1/2 = igual en mongo/postgres; bit 4/8 = presente en mongo/postgres.
    state = dict.fromkeys(source, 0)
    counts = {"fuente": len(source)}
    missing = {"fuente": 0, "mongo": 0, "postgres": 0}
    different = {"mongo": 0, "postgres": 0}
    same_order: dict[str, int] = {}
    examples: list[dict] = []
    for name, path, bit, is_mongo in engines:
        n = same = 0
        with path.open() as f:
            for line in f:
                n += 1
                doc = json.loads(line)
                if is_mongo:
                    doc = strip_mongo_id(doc)
                check(f"{name} (sin orden)", doc, False)
                same += tuple(doc) == schema.TOP_KEYS
                oid, digest = canonical_digest(line, drop_mongo_id=is_mongo)
                if oid not in state:
                    missing["fuente"] += 1
                    if len(examples) < MAX_EXAMPLES:
                        examples.append({"order_id": oid, "falta_en": ["fuente"], "aparece_en": name})
                    continue
                state[oid] |= bit << 2
                if digest == source[oid]:
                    state[oid] |= bit
                else:
                    different[name] += 1
                    if len(examples) < MAX_EXAMPLES:
                        examples.append({"order_id": oid, "motor": name, "_doc": doc})
        counts[name] = n
        same_order[name] = same
        missing[name] = sum(1 for v in state.values() if not v & (bit << 2))

    # Para los ejemplos de documentos distintos, la ruta exacta de la diferencia.
    wanted = {e["order_id"]: e for e in examples if "_doc" in e}
    if wanted:
        with src_path.open() as f:
            for line in f:
                src_doc = json.loads(line)
                e = wanted.get(src_doc["order_id"])
                if e:
                    e["primera_diferencia"] = first_difference(src_doc, e.pop("_doc"))
    for oid in [k for k, v in state.items() if (v & 12) != 12][:MAX_EXAMPLES - len(examples)]:
        examples.append({"order_id": oid,
                         "falta_en": [name for name, _, bit, _ in engines if not state[oid] & (bit << 2)]})

    equal_all = sum(1 for v in state.values() if v & 3 == 3)
    comparison = {**counts, "iguales_en_los_tres": equal_all, "faltan_en": missing,
                  "distintos": different, "ejemplos": examples,
                  "metodo": "huella SHA-1 de la forma canónica de cada documento, leída en streaming"}
    comparison["ok"] = (equal_all == len(source) and not any(missing.values()) and not any(different.values()))
    ok = comparison["ok"] and all(v["invalidos"] == 0 for v in validation.values())
    return {
        "validacion_esquema_100pct": validation,
        "comparacion_tres_direcciones": comparison,
        "documentos_con_mismo_orden_de_claves_que_la_fuente": same_order,
        "ok": ok,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("export")
    e.add_argument("--gate", required=True, choices=GATES)
    e.add_argument("--engine", required=True, choices=CONTAINERS)
    c = sub.add_parser("compare")
    c.add_argument("--gate", required=True, choices=GATES)
    c.add_argument("--out", type=Path, help="archivo de salida (por defecto results/f3/<gate>/compare.json)")
    args = parser.parse_args(argv)

    outdir = ROOT / "results" / "f3" / args.gate
    outdir.mkdir(parents=True, exist_ok=True)
    try:
        if args.cmd == "export":
            data = export_engine(args.gate, args.engine)
            out = outdir / f"export_{args.engine}.json"
        else:
            data = compare(args.gate)
            out = (args.out or outdir / "compare.json").resolve()
    except (RuntimeError, FileNotFoundError, KeyError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")

    if args.cmd == "export":
        print(f"== export {args.gate} / {args.engine}: conteo={data['conteo']} (esperado {data['esperado']})")
        print(f"   tipos documento : {json.dumps(data['tipos_documento'], ensure_ascii=False)}")
        print(f"   tipos items     : {json.dumps(data['tipos_items'], ensure_ascii=False)}")
        for name, ok in data["comprobaciones"].items():
            print(f"   {'OK   ' if ok else 'FALLA'} {name}")
    else:
        cmp_ = data["comparacion_tres_direcciones"]
        print(f"== compare {args.gate}: iguales en los tres = {cmp_['iguales_en_los_tres']}"
              f" de {cmp_['fuente']} (mongo={cmp_['mongo']}, postgres={cmp_['postgres']})")
        print(f"   faltan_en={cmp_['faltan_en']}  distintos={cmp_['distintos']}")
        for name, v in data["validacion_esquema_100pct"].items():
            print(f"   esquema {name}: {v['validados']} validados, {v['invalidos']} inválidos")
        print(f"   mismo orden de claves que la fuente: {data['documentos_con_mismo_orden_de_claves_que_la_fuente']}")
    shown = out.relative_to(ROOT) if out.is_relative_to(ROOT) else out
    print(f"   {'RESULTADO: OK' if data['ok'] else 'RESULTADO: FALLA'}  ->  {shown}")
    return 0 if data["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
