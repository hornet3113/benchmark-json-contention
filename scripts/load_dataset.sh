#!/usr/bin/env bash
# load_dataset.sh — carga el dataset de F2 en UN motor (F3, SPEC §3).
#
# Uso:  scripts/load_dataset.sh <1000|10000|500000> <mongo|postgres>
#       (el contenedor del motor debe estar arriba: scripts/up_profile.sh a_baseline <motor>)
#
# Pasos, cada uno cronometrado por separado (F3-c):
#   0. verifica que el SHA-256 del archivo coincida con sus estadísticas de F2
#   1. recrea la colección / tabla           (docker/<motor>/init.*)      DESTRUCTIVO
#   2. carga por stdin                        (mongoimport / COPY)
#   3. crea los índices                       (docker/<motor>/indexes.*)
#   4. solo Postgres: VACUUM ANALYZE          (para que el planner tenga estadísticas)
#
# Los datos pasan por la entrada estándar de docker exec: no se monta ninguna
# carpeta del host en el contenedor (SPEC L6).
#
# Salida: resumen en pantalla y results/f3/<g1|g2|g3>/load_<motor>.json
# Código de salida: 0 si la carga terminó y el conteo es el esperado; 1 si no.

set -euo pipefail

SIZE="${1:-}"
ENGINE="${2:-}"
case "$SIZE" in 1000) GATE=g1 ;; 10000) GATE=g2 ;; 500000) GATE=g3 ;;
  *) echo "uso: $0 <1000|10000|500000> <mongo|postgres>" >&2; exit 2 ;; esac
case "$ENGINE" in
  mongo)    CONTAINER=bench_mongo ;;
  postgres) CONTAINER=bench_postgres ;;
  *) echo "uso: $0 <1000|10000|500000> <mongo|postgres>" >&2; exit 2 ;; esac

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
set -a
# shellcheck disable=SC1090
source "$ROOT/docker/images.env"
set +a

DATA="$ROOT/data/orders_${SIZE}_seed42.jsonl"
if [[ "$SIZE" == 500000 ]]; then STATS="$ROOT/results/dataset_stats.json"
else STATS="$ROOT/results/f2/dataset_stats_${SIZE}_seed42.json"; fi
OUTDIR="$ROOT/results/f3/$GATE"
mkdir -p "$OUTDIR"

docker ps --format '{{.Names}}' | grep -qx "$CONTAINER" || {
  echo "ERROR: $CONTAINER no está corriendo. Levántalo con: scripts/up_profile.sh a_baseline $ENGINE" >&2; exit 2; }

# --- 0. el archivo es el que se verificó en F2 ------------------------------
[[ -f "$DATA" && -f "$STATS" ]] || { echo "ERROR: falta $DATA o $STATS (genera con F2)" >&2; exit 2; }
SHA_FILE="$(sha256sum "$DATA" | cut -d' ' -f1)"
SHA_STATS="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["sha256"])' "$STATS")"
if [[ "$SHA_FILE" != "$SHA_STATS" ]]; then
  echo "ERROR: el SHA-256 de $DATA no coincide con $STATS" >&2
  echo "       archivo=$SHA_FILE  estadísticas=$SHA_STATS" >&2
  exit 1
fi
echo "== Carga $GATE: $SIZE registros en $ENGINE"
echo "   archivo : ${DATA#"$ROOT/"}  sha256=$SHA_FILE (coincide con ${STATS#"$ROOT/"})"

now() { date +%s.%N; }
secs() { python3 -c "print(round($2 - $1, 3))"; }

if [[ "$ENGINE" == mongo ]]; then
  MONGOSH=(docker exec "$CONTAINER" mongosh --quiet "$MONGO_DB")
  "${MONGOSH[@]}" --eval "$(cat "$ROOT/docker/mongo/init.js")"

  T0=$(now)
  # --stopOnError: un documento rechazado detiene la carga en vez de pasar en silencio.
  docker exec -i "$CONTAINER" mongoimport --db "$MONGO_DB" --collection orders \
    --type json --mode insert --stopOnError < "$DATA" 2>&1 | sed 's/^/   mongoimport: /'
  T1=$(now)
  "${MONGOSH[@]}" --eval "$(cat "$ROOT/docker/mongo/indexes.js")"
  T2=$(now)
  T3=$T2
  COUNT="$("${MONGOSH[@]}" --eval 'db.orders.countDocuments()' | tr -d '\r')"
else
  PSQL=(docker exec -i "$CONTAINER" psql -X -q -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB")
  "${PSQL[@]}" -f - < "$ROOT/docker/postgres/init.sql"

  T0=$(now)
  # COPY en formato texto: válido porque F2 garantiza 0 líneas con "\" o
  # caracteres de control (docs/F3_CARGA.md, problema 3).
  "${PSQL[@]}" -c "COPY orders_staging (doc) FROM STDIN" < "$DATA"
  "${PSQL[@]}" -c "INSERT INTO orders (id, data) SELECT (doc->>'order_id')::uuid, doc FROM orders_staging"
  "${PSQL[@]}" -c "DROP TABLE orders_staging"
  T1=$(now)
  "${PSQL[@]}" -f - < "$ROOT/docker/postgres/indexes.sql"
  T2=$(now)
  "${PSQL[@]}" -c "VACUUM ANALYZE orders"
  T3=$(now)
  COUNT="$("${PSQL[@]}" -tAc 'SELECT count(*) FROM orders' | tr -d '\r')"
fi

LOAD_S=$(secs "$T0" "$T1"); INDEX_S=$(secs "$T1" "$T2"); ANALYZE_S=$(secs "$T2" "$T3")
echo "   conteo  : $COUNT (esperado $SIZE)"
echo "   tiempos : carga=${LOAD_S}s  índices=${INDEX_S}s  analyze=${ANALYZE_S}s"

OK=false; [[ "$COUNT" == "$SIZE" ]] && OK=true
cat > "$OUTDIR/load_${ENGINE}.json" <<JSON
{
  "gate": "$GATE",
  "engine": "$ENGINE",
  "fecha_utc": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "archivo": "${DATA#"$ROOT/"}",
  "sha256": "$SHA_FILE",
  "esperado": $SIZE,
  "conteo": $COUNT,
  "segundos": {"carga": $LOAD_S, "indices": $INDEX_S, "analyze": $ANALYZE_S},
  "ok": $OK
}
JSON
echo "   evidencia: ${OUTDIR#"$ROOT/"}/load_${ENGINE}.json"
[[ "$OK" == true ]]
