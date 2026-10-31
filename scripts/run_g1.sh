#!/usr/bin/env bash
# run_g1.sh — compuerta G1 de F3: 1 000 registros en ambos motores (docs/F3_CARGA.md).
#
# Uso:  scripts/run_g1.sh
#
# Orden (solo un motor arriba a la vez, CLAUDE.md):
#   1. Mongo    : levantar (PROFILE_A, F3-a) → cargar → exportar y verificar
#   2. Postgres : levantar (baja Mongo)      → cargar → A3.2 → exportar y verificar
#   3. bajar todo → comparar en tres direcciones (sin motores)
#
# DESTRUCTIVO para los datos de los motores: load_dataset.sh recrea la
# colección y la tabla. Los volúmenes y el dataset de F2 no se tocan.
#
# Salida: results/f3/g1/run_<fecha>.txt (todo lo que se ve en pantalla),
#         a32_index_variants.txt, load_*.json, export_*.json, compare.json.
# Se detiene en el primer paso que falle.

set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="$ROOT/results/f3/g1"
mkdir -p "$OUT"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
exec > >(tee "$OUT/run_${STAMP}.txt") 2>&1

set -a
# shellcheck disable=SC1090
source "$ROOT/docker/images.env"
set +a

step() {  # step <descripción> <comando...>
  local what="$1"; shift
  echo; echo "### $what"; echo "\$ ${*#"$ROOT/"}"
  "$@"; local rc=$?
  if [[ $rc -ne 0 ]]; then
    echo "!!! FALLÓ ($rc): $what — G1 se detiene aquí"
    "$ROOT/scripts/down_profile.sh" >/dev/null 2>&1
    exit 1
  fi
}

echo "== G1 — $STAMP — python $(python3 --version | cut -d' ' -f2) · $(uname -r)"

step "1a. Levantar Mongo (PROFILE_A)"         "$ROOT/scripts/up_profile.sh" a_baseline mongo
step "1b. Cargar 1 000 en Mongo"              "$ROOT/scripts/load_dataset.sh" 1000 mongo
step "1c. Exportar y verificar Mongo"         python3 "$ROOT/scripts/verify_gate.py" export --gate g1 --engine mongo

step "2a. Levantar Postgres (baja Mongo)"     "$ROOT/scripts/up_profile.sh" a_baseline postgres
step "2b. Cargar 1 000 en Postgres"           "$ROOT/scripts/load_dataset.sh" 1000 postgres

echo; echo "### 2c. A3.2 — variantes de índice (los errores son resultados, no fallos)"
# stdbuf: sin él, psql guarda stdout en búfer y los ERROR (stderr) aparecen
# lejos de la sentencia que los produjo (pasó en la primera corrida de G1).
docker exec -i bench_postgres stdbuf -oL -eL psql -X -e -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
  < "$ROOT/scripts/checks/a32_index_variants.sql" > "$OUT/a32_index_variants.txt" 2>&1
cat "$OUT/a32_index_variants.txt"

step "2d. Exportar y verificar Postgres"      python3 "$ROOT/scripts/verify_gate.py" export --gate g1 --engine postgres
step "3a. Bajar motores"                      "$ROOT/scripts/down_profile.sh"
step "3b. Comparar en tres direcciones"       python3 "$ROOT/scripts/verify_gate.py" compare --gate g1

echo; echo "== G1 terminó: todos los pasos con exit 0. Evidencia en ${OUT#"$ROOT/"}/"
