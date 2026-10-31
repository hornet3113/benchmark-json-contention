"""schema.py — contrato de un registro del dataset (R-09, R-10, A1, docs/F2_GENERADOR.md).

validate_record(rec) devuelve la LISTA de problemas encontrados (vacía = válido),
para que una prueba que falle diga qué está mal y no solo que algo lo está.

Se usa en tres sitios: las pruebas del generador (F2), la validación de la
muestra al generar (F2.2) y, en F3-G1, sobre lo que se lee de vuelta de cada
motor, para comprobar que los tipos sobrevivieron a la carga.
"""

from __future__ import annotations

import re
import uuid

# Claves exactas de cada objeto, en el orden en que el generador las escribe.
# Ni más ni menos: una clave de más también es un error de contrato.
TOP_KEYS = ("order_id", "timestamp", "customer", "items", "payment", "metadata")
CUSTOMER_KEYS = ("id", "tier", "segment", "geo")
GEO_KEYS = ("country", "state", "city", "zip", "coordinates")
ITEM_KEYS = ("sku", "category", "brand", "qty", "price", "tax_pct", "discounts")
# final_total es hermano de totals, no hijo (A1): así Q2 corre literal.
PAYMENT_KEYS = ("method", "status", "transaction_id", "gateway_latency_ms", "totals", "final_total")
TOTALS_KEYS = ("subtotal", "tax", "discount")
METADATA_KEYS = ("channel", "user_agent", "session_id", "flags")

MAX_NESTING = 3  # F2-a: raíz = nivel 0

# Forma canónica de un uuid tal como PostgreSQL lo escribe al convertirlo a texto.
UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
# Trampa 1: sin fracciones de segundo y siempre "Z".
TIMESTAMP_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
# Caracteres que el formato texto de COPY interpreta: "\" y los de control.
_COPY_UNSAFE_RE = re.compile(r"[\\\x00-\x1f\x7f]")


def nesting_depth(value) -> int:
    """Niveles de contenedores por debajo de la raíz (F2-a).

    Un escalar no suma; cada dict o list suma 1. A la raíz se le resta 1 porque
    es el nivel 0: {"a": 1} → 0, {"a": {"b": 1}} → 1.
    """
    def depth(v) -> int:
        if isinstance(v, dict):
            return 1 + max((depth(x) for x in v.values()), default=0)
        if isinstance(v, list):
            return 1 + max((depth(x) for x in v), default=0)
        return 0
    return depth(value) - 1


def _is_number(v) -> bool:
    # bool es subclase de int en Python, pero en JSON no es un número.
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for k, v in value.items():
            yield k
            yield from _strings(v)
    elif isinstance(value, list):
        for v in value:
            yield from _strings(v)


def _cents(v: float) -> int:
    return round(v * 100)


def validate_record(rec, *, strict_order: bool = True) -> list[str]:
    """Problemas del registro (lista vacía = válido).

    strict_order=True exige las claves en el orden del generador: es lo que se
    usa al generar y lo que fija el SHA-256. strict_order=False solo exige el
    mismo CONJUNTO de claves: es para documentos leídos de vuelta de un motor,
    porque JSONB reordena las claves (por longitud y luego alfabéticamente).
    """
    errors: list[str] = []

    def keys(obj, expected, where) -> bool:
        if not isinstance(obj, dict):
            errors.append(f"{where}: se esperaba objeto, llegó {type(obj).__name__}")
            return False
        if (tuple(obj.keys()) != expected) if strict_order else (set(obj) != set(expected)):
            missing = [k for k in expected if k not in obj]
            extra = [k for k in obj if k not in expected]
            errors.append(f"{where}: claves {list(obj)} (faltan {missing}, sobran {extra})")
            return False
        return True

    def number(v, where, *, integer=False, minimum=None):
        if not _is_number(v) or (integer and not isinstance(v, int)):
            errors.append(f"{where}: se esperaba {'entero' if integer else 'número'}, llegó {v!r}")
        elif minimum is not None and v < minimum:
            errors.append(f"{where}: {v} < {minimum}")

    def text(v, where):
        if not isinstance(v, str) or not v:
            errors.append(f"{where}: se esperaba texto no vacío, llegó {v!r}")

    if not keys(rec, TOP_KEYS, "registro"):
        return errors

    oid = rec["order_id"]
    if not isinstance(oid, str) or not UUID_RE.match(oid) or str(uuid.UUID(oid)) != oid:
        errors.append(f"order_id: no es un UUID canónico en minúsculas: {oid!r}")

    ts = rec["timestamp"]
    if not isinstance(ts, str) or not TIMESTAMP_RE.match(ts):
        errors.append(f"timestamp: no cumple YYYY-MM-DDTHH:MM:SSZ: {ts!r}")

    cust = rec["customer"]
    if keys(cust, CUSTOMER_KEYS, "customer"):
        for k in ("id", "tier", "segment"):
            text(cust[k], f"customer.{k}")
        geo = cust["geo"]
        if keys(geo, GEO_KEYS, "customer.geo"):
            for k in ("country", "state", "city", "zip"):
                text(geo[k], f"customer.geo.{k}")
            c = geo["coordinates"]
            if not (isinstance(c, list) and len(c) == 2 and all(_is_number(x) for x in c)):
                errors.append(f"customer.geo.coordinates: se esperaba [lon, lat], llegó {c!r}")
            elif not (-180 <= c[0] <= 180 and -90 <= c[1] <= 90):
                errors.append(f"customer.geo.coordinates: fuera de rango {c!r}")

    items = rec["items"]
    if not isinstance(items, list) or not items:
        errors.append(f"items: se esperaba arreglo no vacío, llegó {items!r}")
        items = []
    for i, it in enumerate(items):
        w = f"items[{i}]"
        if not keys(it, ITEM_KEYS, w):
            continue
        for k in ("sku", "category", "brand"):
            text(it[k], f"{w}.{k}")
        number(it["qty"], f"{w}.qty", integer=True, minimum=1)
        number(it["price"], f"{w}.price", minimum=0)
        number(it["tax_pct"], f"{w}.tax_pct", minimum=0)
        d = it["discounts"]
        if not (isinstance(d, list) and all(_is_number(x) for x in d)):
            errors.append(f"{w}.discounts: se esperaba lista de números, llegó {d!r}")

    pay = rec["payment"]
    if keys(pay, PAYMENT_KEYS, "payment"):
        for k in ("method", "status", "transaction_id"):
            text(pay[k], f"payment.{k}")
        number(pay["gateway_latency_ms"], "payment.gateway_latency_ms", integer=True, minimum=0)
        # Trampa conocida (CLAUDE.md): si final_total fuera string, Mongo
        # ordenaría "9.5" > "100.0" y los Top-1000 no coincidirían.
        number(pay["final_total"], "payment.final_total", minimum=0)
        tot = pay["totals"]
        if keys(tot, TOTALS_KEYS, "payment.totals"):
            for k in TOTALS_KEYS:
                number(tot[k], f"payment.totals.{k}", minimum=0)
            amounts = [pay["final_total"], *(tot[k] for k in TOTALS_KEYS)]
            if all(_is_number(a) for a in amounts) and _cents(pay["final_total"]) != (
                    _cents(tot["subtotal"]) + _cents(tot["tax"]) - _cents(tot["discount"])):
                errors.append(f"payment.final_total {pay['final_total']} != subtotal + tax - discount {tot}")

    meta = rec["metadata"]
    if keys(meta, METADATA_KEYS, "metadata"):
        for k in ("channel", "user_agent", "session_id"):
            text(meta[k], f"metadata.{k}")
        f = meta["flags"]
        if not (isinstance(f, list) and all(isinstance(x, str) for x in f)):
            errors.append(f"metadata.flags: se esperaba lista de textos, llegó {f!r}")

    depth = nesting_depth(rec)
    if depth != MAX_NESTING:
        errors.append(f"anidamiento: {depth} niveles, se esperaban {MAX_NESTING}")

    bad = sorted({s for s in _strings(rec) if _COPY_UNSAFE_RE.search(s)})
    if bad:
        errors.append(f"textos con caracteres que rompen COPY: {bad[:3]}")

    return errors
