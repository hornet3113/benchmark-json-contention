#!/usr/bin/env bash
# down_profile.sh — baja ambos motores.
#
#   scripts/down_profile.sh            -> para los contenedores, CONSERVA los datos
#   scripts/down_profile.sh --volumes  -> además BORRA los volúmenes (dataset incluido)
#
# El borrado de volúmenes es destructivo y en F3 significa recargar el dataset
# completo, así que hay que pedirlo explícitamente.

set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="$ROOT/docker/docker-compose.yml"

set -a
# shellcheck disable=SC1090
source "$ROOT/docker/images.env"
# shellcheck disable=SC1090
source "$ROOT/docker/profiles/a_baseline.env"   # solo para satisfacer la sustitución de variables
set +a

EXTRA=()
if [[ "${1:-}" == "--volumes" ]]; then
  echo "AVISO: se borrarán benchjson_mongo_data y benchjson_pg_data."
  read -r -p "Escribe BORRAR para confirmar: " ANS
  [[ "$ANS" == "BORRAR" ]] || { echo "Cancelado."; exit 1; }
  EXTRA+=(--volumes)
fi

docker compose -f "$COMPOSE_FILE" --profile mongo --profile postgres down --remove-orphans "${EXTRA[@]}"
echo "Listo."
