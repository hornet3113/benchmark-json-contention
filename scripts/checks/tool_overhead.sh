#!/usr/bin/env bash
# tool_overhead.sh — cuánto tarda en ARRANCAR cada herramienta de carga, sin trabajo real.
#
# Uso:  scripts/checks/tool_overhead.sh <g2|g3> <mongo|postgres>   (con el motor arriba)
#
# Por qué: en G1, crear los índices de 1 000 documentos en Mongo "tardó" 4.99 s,
# y casi todo era el arranque de mongosh. Para extrapolar el tiempo de carga a
# 500 000 hay que restar ese arranque fijo, que no crece con los datos.
#
# Mide 5 veces cada invocación vacía, con los mismos comandos que usa
# load_dataset.sh, y guarda todas las muestras y la mediana.
# Salida: results/f3/<gate>/overhead_<motor>.json

set -euo pipefail
GATE="${1:-}"; ENGINE="${2:-}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
set -a
# shellcheck disable=SC1090
source "$ROOT/docker/images.env"
set +a
OUT="$ROOT/results/f3/$GATE/overhead_${ENGINE}.json"
mkdir -p "$(dirname "$OUT")"
N=5

time_runs() {  # time_runs <comando...> → segundos separados por espacio
  local s=() t0 t1
  for _ in $(seq 1 $N); do
    t0=$(date +%s.%N); "$@" >/dev/null 2>&1 </dev/null; t1=$(date +%s.%N)
    s+=("$(python3 -c "print(round($t1 - $t0, 3))")")
  done
  echo "${s[*]}"
}

if [[ "$ENGINE" == mongo ]]; then
  # mongoimport con entrada vacía: arranca, se conecta, no inserta nada.
  IMPORT=$(time_runs docker exec -i bench_mongo mongoimport --db "$MONGO_DB" --collection overhead_probe --type json)
  SHELL_=$(time_runs docker exec bench_mongo mongosh --quiet "$MONGO_DB" --eval '1')
  docker exec bench_mongo mongosh --quiet "$MONGO_DB" --eval 'db.overhead_probe.drop()' >/dev/null
  JSON_TOOLS="\"mongoimport\": [${IMPORT// /, }], \"mongosh\": [${SHELL_// /, }]"
else
  PSQL=$(time_runs docker exec -i bench_postgres psql -X -q -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c 'SELECT 1')
  JSON_TOOLS="\"psql\": [${PSQL// /, }]"
fi

python3 - "$OUT" "$GATE" "$ENGINE" <<PY
import json, statistics, sys
out, gate, engine = sys.argv[1:4]
samples = {$JSON_TOOLS}
data = {"gate": gate, "engine": engine, "repeticiones": $N, "muestras_s": samples,
        "mediana_s": {k: round(statistics.median(v), 3) for k, v in samples.items()}}
open(out, "w").write(json.dumps(data, indent=2) + "\n")
print(f"== arranque de herramientas ({engine}), mediana de $N: {data['mediana_s']}")
PY
