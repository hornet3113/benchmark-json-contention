#!/usr/bin/env python3
"""synthetic_data_generator.py — dataset sintético de órdenes (R-25, playbook.pdf §4).

Nombre exigido por el manual (§8.1).

Uso (desde la raíz del repo):
    python3 generator/synthetic_data_generator.py --size 1000|10000|500000

Escribe data/orders_<tamaño>_seed<semilla>.jsonl (un registro JSON por línea)
y sus estadísticas: results/dataset_stats.json para 500 000 (PLAN F2),
results/f2/dataset_stats_<tamaño>.json para los demás. Código de salida 0 si
todos los registros cumplen el contrato y no hay order_id repetidos; 1 si no.

Reglas que este archivo garantiza (docs/F2_GENERADOR.md):

  - Determinismo: toda la aleatoriedad sale del `rng` recibido, y las llamadas
    se hacen siempre en el mismo orden. Misma semilla → mismos registros. Por
    eso los N primeros registros de cualquier tamaño son idénticos entre sí.
  - order_id: UUID canónico en minúsculas, generado desde el rng (uuid4()
    usaría azar del sistema). Es el mismo valor que F3 usará como id en
    PostgreSQL.
  - timestamp: texto ISO-8601 estricto, UTC con "Z" y sin fracciones.
  - Importes en centavos enteros; se convierten a número JSON con 2 decimales
    solo al final, así final_total = subtotal + tax - discount exactamente.
  - Serialización fija (claves en orden, sin espacios, ASCII, "\\n"): misma
    semilla → mismo SHA-256.
  - Escritura atómica: se escribe a .tmp y se renombra al terminar. Un corte a
    medias no deja un archivo incompleto con el nombre definitivo.
"""

from __future__ import annotations

import argparse
import hashlib
import heapq
import json
import platform
import random
import sys
import time
import uuid
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

if __package__ in (None, ""):  # ejecutado como script: python3 generator/synthetic_data_generator.py
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from generator import distributions as D  # noqa: E402
from generator import schema  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SIZES = (1_000, 10_000, 500_000)  # PLAN F2: modos --size
STATS_SCHEMA = "dataset_stats/1"

# Filtro y corte de Q2, copiados de playbook.pdf §5.2 para medir cuántas filas
# selecciona y si hay empate en la frontera. NO es la query: esa vive en queries/.
Q2_STATUS = "completed"
Q2_TS_GTE = "2026-01-01T00:00:00Z"
Q2_LIMIT = 1000

_TS_SPAN_SECONDS = int((D.TS_END - D.TS_START).total_seconds())
_CATEGORY_NAMES = tuple(D.CATEGORIES)
_COUNTRY_CODES = tuple(D.COUNTRIES)


def _weighted(rng: random.Random, weights: dict):
    return rng.choices(tuple(weights), weights=tuple(weights.values()))[0]


def _money(cents: int) -> float:
    """Centavos enteros → número con 2 decimales. repr(1234/100) == '12.34'."""
    return cents / 100


def _item(rng: random.Random) -> tuple[dict, int, int, int]:
    """Un ítem y sus importes en centavos: (ítem, bruto, descuento, impuesto)."""
    category = rng.choice(_CATEGORY_NAMES)
    brand = rng.randint(1, D.BRAND_COUNT)
    sku_number = rng.randint(0, D.SKU_NUMBER_MAX)
    qty = rng.randint(D.QTY_MIN, D.QTY_MAX)
    price_cents = rng.randint(D.PRICE_CENTS_MIN, D.PRICE_CENTS_MAX)
    tax_pct = _weighted(rng, D.TAX_PCT_WEIGHTS)
    discounts = rng.sample(D.DISCOUNT_PCT_VALUES, _weighted(rng, D.DISCOUNT_COUNT_WEIGHTS))

    # Redondeo "mitad hacia arriba" en enteros: (x + 50) // 100.
    gross = qty * price_cents
    discount = (gross * sum(discounts) + 50) // 100
    tax = ((gross - discount) * tax_pct + 50) // 100

    item = {
        "sku": f"{D.CATEGORIES[category]}-{brand:02d}-{sku_number:05d}",
        "category": category,
        "brand": f"BRAND{brand:02d}",
        "qty": qty,
        "price": _money(price_cents),
        "tax_pct": tax_pct,
        "discounts": discounts,
    }
    return item, gross, discount, tax


def make_record(rng: random.Random) -> dict:
    """Genera un registro. El orden de las claves es el de generator/schema.py."""
    order_id = str(uuid.UUID(int=rng.getrandbits(128), version=4))
    ts = D.TS_START + timedelta(seconds=rng.randint(0, _TS_SPAN_SECONDS))

    country = rng.choice(_COUNTRY_CODES)
    (lon0, lat0), states = D.COUNTRIES[country]
    state = rng.choice(tuple(states))
    city = rng.choice(states[state])
    j = D.COORD_JITTER_DEG
    coordinates = [round(lon0 + rng.uniform(-j, j), D.COORD_DECIMALS),
                   round(lat0 + rng.uniform(-j, j), D.COORD_DECIMALS)]

    customer = {
        "id": f"C{rng.randrange(D.CUSTOMER_POOL):06d}",
        "tier": _weighted(rng, D.TIER_WEIGHTS),
        "segment": _weighted(rng, D.SEGMENT_WEIGHTS),
        "geo": {
            "country": country,
            "state": state,
            "city": city,
            "zip": f"{rng.randint(0, 99999):05d}",
            "coordinates": coordinates,
        },
    }

    items, subtotal, discount, tax = [], 0, 0, 0
    for _ in range(_weighted(rng, D.ITEM_COUNT_WEIGHTS)):
        item, g, d, t = _item(rng)
        items.append(item)
        subtotal += g
        discount += d
        tax += t

    payment = {
        "method": _weighted(rng, D.METHOD_WEIGHTS),
        "status": _weighted(rng, D.STATUS_WEIGHTS),
        "transaction_id": f"tx_{rng.getrandbits(64):016x}",
        "gateway_latency_ms": rng.randint(D.GATEWAY_LATENCY_MS_MIN, D.GATEWAY_LATENCY_MS_MAX),
        "totals": {
            "subtotal": _money(subtotal),
            "tax": _money(tax),
            "discount": _money(discount),
        },
        # Hermano de totals, no hijo (A1). Número, nunca string.
        "final_total": _money(subtotal - discount + tax),
    }

    metadata = {
        "channel": _weighted(rng, D.CHANNEL_WEIGHTS),
        "user_agent": rng.choice(D.USER_AGENTS),
        "session_id": f"{rng.getrandbits(128):032x}",
        "flags": rng.sample(D.FLAG_VALUES, _weighted(rng, D.FLAG_COUNT_WEIGHTS)),
    }

    return {
        "order_id": order_id,
        "timestamp": ts.strftime(D.TS_FORMAT),
        "customer": customer,
        "items": items,
        "payment": payment,
        "metadata": metadata,
    }


# --- F2.2: escritura en streaming y estadísticas ---------------------------

def serialize(rec: dict) -> bytes:
    """Una línea JSONL. Formato fijo: es parte de lo que el hash garantiza."""
    return (json.dumps(rec, separators=(",", ":"), ensure_ascii=True) + "\n").encode("ascii")


class Stats:
    """Acumula las estadísticas registro a registro, sin guardar el dataset.

    Lo único que crece con el tamaño es el conjunto de order_id (para detectar
    repetidos): ~100 bytes por registro, unos 50 MB para 500 000.
    """

    MAX_ERROR_EXAMPLES = 5

    def __init__(self, top_k: int = Q2_LIMIT):
        self.top_k = top_k
        self.records = 0
        self.items = 0
        self.items_price_gt_50 = 0
        self.completed = 0
        self.ts_ge_2026 = 0
        self.q2_rows = 0
        self.q2_top = []                 # min-heap con los top_k+1 final_total (en centavos) de Q2
        self.groups = Counter()          # (country, category) → ítems, como agrupa Q1
        self.status = Counter()
        self.items_per_record = Counter()
        self.depths = Counter()
        self.ts_min = self.ts_max = None
        self.final_min = self.final_max = None
        self.order_ids = set()
        self.duplicate_order_ids = 0
        self.invalid_records = 0
        self.error_examples = []

    def add(self, rec: dict) -> None:
        self.records += 1
        errors = schema.validate_record(rec)
        if errors:
            # Se cuenta y se guarda un ejemplo, pero no entra en los agregados:
            # sus campos pueden faltar o tener tipos que romperían las cuentas.
            self.invalid_records += 1
            if len(self.error_examples) < self.MAX_ERROR_EXAMPLES:
                self.error_examples.append({"record": self.records, "errors": errors})
            return

        oid = rec["order_id"]
        if oid in self.order_ids:
            self.duplicate_order_ids += 1
        self.order_ids.add(oid)

        ts, pay = rec["timestamp"], rec["payment"]
        final = pay["final_total"]
        self.ts_min = ts if self.ts_min is None else min(self.ts_min, ts)
        self.ts_max = ts if self.ts_max is None else max(self.ts_max, ts)
        self.final_min = final if self.final_min is None else min(self.final_min, final)
        self.final_max = final if self.final_max is None else max(self.final_max, final)
        self.status[pay["status"]] += 1
        self.depths[schema.nesting_depth(rec)] += 1
        self.completed += pay["status"] == Q2_STATUS
        self.ts_ge_2026 += ts >= Q2_TS_GTE

        if pay["status"] == Q2_STATUS and ts >= Q2_TS_GTE:
            self.q2_rows += 1
            cents = round(final * 100)
            if len(self.q2_top) <= self.top_k:
                heapq.heappush(self.q2_top, cents)
            elif cents > self.q2_top[0]:
                heapq.heapreplace(self.q2_top, cents)

        country = rec["customer"]["geo"]["country"]
        self.items_per_record[len(rec["items"])] += 1
        for it in rec["items"]:
            self.items += 1
            self.items_price_gt_50 += it["price"] > 50
            self.groups[(country, it["category"])] += 1

    def q2_boundary(self) -> dict:
        """¿Empatan las filas top_k y top_k+1 de Q2? Si sí, cada motor puede
        devolver un conjunto distinto sin que haya error (docs/F2_GENERADOR.md, trampa 2)."""
        if self.q2_rows <= self.top_k:
            return {"aplica": False,
                    "motivo": f"solo {self.q2_rows} filas pasan el filtro: el LIMIT {self.top_k} las devuelve todas"}
        top = sorted(self.q2_top, reverse=True)
        kth, next_ = top[self.top_k - 1], top[self.top_k]
        return {"aplica": True,
                "final_total_fila_k": kth / 100,
                "final_total_fila_k_mas_1": next_ / 100,
                "empate_en_la_frontera": kth == next_}

    def result(self) -> dict:
        pct = lambda a, b: round(100 * a / b, 4) if b else None  # noqa: E731
        return {
            "registros": self.records,
            "registros_invalidos": self.invalid_records,
            "ejemplos_de_errores": self.error_examples,
            "order_id_repetidos": self.duplicate_order_ids,
            "anidamiento_niveles": dict(sorted(self.depths.items())),
            "items": {
                "total": self.items,
                "media_por_registro": round(self.items / self.records, 4) if self.records else None,
                "distribucion": dict(sorted(self.items_per_record.items())),
                "pct_price_gt_50": pct(self.items_price_gt_50, self.items),
            },
            "payment_status": dict(sorted(self.status.items())),
            "pct_completed": pct(self.completed, self.records),
            "pct_timestamp_ge_2026": pct(self.ts_ge_2026, self.records),
            "timestamp_min": self.ts_min,
            "timestamp_max": self.ts_max,
            "final_total_min": self.final_min,
            "final_total_max": self.final_max,
            "q1_grupos_pais_categoria": {
                "distintos": len(self.groups),
                "posibles": len(D.COUNTRIES) * len(D.CATEGORIES),
                "items_min_por_grupo": min(self.groups.values(), default=0),
                "items_max_por_grupo": max(self.groups.values(), default=0),
            },
            "q2": {
                "filtro": f"payment.status = '{Q2_STATUS}' AND timestamp >= '{Q2_TS_GTE}'",
                "filas": self.q2_rows,
                "pct": pct(self.q2_rows, self.records),
                "frontera_top_k": {"k": self.top_k, **self.q2_boundary()},
            },
        }

    @property
    def ok(self) -> bool:
        return self.records > 0 and self.invalid_records == 0 and self.duplicate_order_ids == 0


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def generate(size: int, out: Path, seed: int = D.SEED, top_k: int = Q2_LIMIT) -> dict:
    """Genera `size` registros en `out` (JSONL) y devuelve las estadísticas."""
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(out.name + ".tmp")
    rng = random.Random(seed)
    stats = Stats(top_k=top_k)
    digest = hashlib.sha256()
    nbytes = 0

    started = datetime.now(timezone.utc)
    t0 = time.perf_counter()
    with tmp.open("wb") as f:
        for _ in range(size):
            rec = make_record(rng)
            line = serialize(rec)
            f.write(line)
            digest.update(line)
            nbytes += len(line)
            stats.add(rec)
    elapsed = time.perf_counter() - t0
    tmp.replace(out)

    src = Path(__file__).resolve().parent
    return {
        "schema": STATS_SCHEMA,
        "generado_utc": started.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "archivo": str(out.relative_to(ROOT)) if out.is_relative_to(ROOT) else str(out),
        "tamano_pedido": size,
        "semilla": seed,
        "sha256": digest.hexdigest(),
        "bytes": nbytes,
        "segundos": round(elapsed, 2),
        "contrato_ok": stats.ok,
        "generador": {
            "python": platform.python_version(),
            # Liga el dataset a la versión exacta del código que lo produjo.
            "sha256_fuentes": {p.name: _sha256_file(p) for p in sorted(src.glob("*.py"))},
        },
        **stats.result(),
    }


def default_paths(size: int, seed: int) -> tuple[Path, Path]:
    data = ROOT / "data" / f"orders_{size}_seed{seed}.jsonl"
    if size == 500_000 and seed == D.SEED:
        stats = ROOT / "results" / "dataset_stats.json"   # nombre fijado en PLAN F2
    else:
        stats = ROOT / "results" / "f2" / f"dataset_stats_{size}_seed{seed}.json"
    return data, stats


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Genera el dataset sintético (playbook.pdf §4).")
    parser.add_argument("--size", type=int, required=True, choices=SIZES)
    parser.add_argument("--seed", type=int, default=D.SEED,
                        help=f"semilla (por defecto {D.SEED}, la versionada en SPEC A8)")
    parser.add_argument("--out", type=Path, help="archivo JSONL (por defecto data/orders_<size>_seed<seed>.jsonl)")
    parser.add_argument("--stats", type=Path, help="archivo de estadísticas (por defecto según PLAN F2)")
    args = parser.parse_args(argv)

    data_path, stats_path = default_paths(args.size, args.seed)
    out = (args.out or data_path).resolve()
    stats_file = (args.stats or stats_path).resolve()

    stats = generate(args.size, out, seed=args.seed)
    stats_file.parent.mkdir(parents=True, exist_ok=True)
    stats_file.write_text(json.dumps(stats, ensure_ascii=False, indent=2) + "\n")

    q2 = stats["q2"]["frontera_top_k"]
    print(f"registros        : {stats['registros']}  ({stats['bytes']} bytes, {stats['segundos']} s)")
    print(f"sha256           : {stats['sha256']}")
    print(f"contrato         : {'OK' if stats['contrato_ok'] else 'FALLA'}"
          f"  (inválidos={stats['registros_invalidos']}, order_id repetidos={stats['order_id_repetidos']})")
    print(f"ítems/registro   : {stats['items']['media_por_registro']}"
          f"  · price>50 {stats['items']['pct_price_gt_50']} %"
          f"  · completed {stats['pct_completed']} %  · ts>=2026 {stats['pct_timestamp_ge_2026']} %")
    print(f"filas filtro Q2  : {stats['q2']['filas']}"
          f"  · empate en la fila {q2['k']}: {q2.get('empate_en_la_frontera', 'no aplica')}")
    print(f"datos            : {out}")
    print(f"estadísticas     : {stats_file}")
    return 0 if stats["contrato_ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
