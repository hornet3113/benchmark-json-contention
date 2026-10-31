#!/usr/bin/env bash
# up_profile.sh — levanta UN motor con UN perfil de recursos y espera a que esté sano.
#
# Uso:  scripts/up_profile.sh <a_baseline|b_medium|c_severe> <mongo|postgres>
# Ej.:  scripts/up_profile.sh a_baseline mongo
#
# Por qué un script y no "docker compose up" directo: hay que cargar dos
# archivos de variables (imágenes + perfil de recursos) antes de invocar a
# compose. Hacerlo aquí en Bash evita depender de cómo cada versión de Compose
# maneja varios --env-file.

set -euo pipefail

PROFILE="${1:-}"
ENGINE="${2:-}"

if [[ -z "$PROFILE" || -z "$ENGINE" ]]; then
  echo "uso: $0 <a_baseline|b_medium|c_severe> <mongo|postgres>" >&2
  exit 2
fi

# Resolvemos la raíz del repo desde la ruta del script, no desde el directorio
# actual: al abrir Ubuntu desde PowerShell la sesión arranca en /mnt/c/... y un
# script que asuma "." terminaría trabajando en el lugar equivocado (F0-V3).
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROFILE_FILE="$ROOT/docker/profiles/${PROFILE}.env"
COMPOSE_FILE="$ROOT/docker/docker-compose.yml"

[[ -f "$PROFILE_FILE" ]] || { echo "ERROR: no existe $PROFILE_FILE" >&2; exit 2; }

case "$ENGINE" in
  mongo|postgres) ;;
  *) echo "ERROR: motor '$ENGINE' no válido (mongo|postgres)" >&2; exit 2 ;;
esac

# Exportamos todo lo que definan los dos archivos para que compose lo sustituya.
set -a
# shellcheck disable=SC1090
source "$ROOT/docker/images.env"
# shellcheck disable=SC1090
source "$PROFILE_FILE"
set +a

echo "== Perfil: $PROFILE_ID  |  Motor: $ENGINE"
echo "   CPUs=$CPUS_LIMIT  mem=$MEM_LIMIT  memswap=$MEMSWAP_LIMIT  swappiness=$MEM_SWAPPINESS"

# Bajamos cualquier motor que haya quedado arriba: solo uno a la vez (SPEC §2).
docker compose -f "$COMPOSE_FILE" --profile mongo --profile postgres down --remove-orphans >/dev/null 2>&1 || true

docker compose -f "$COMPOSE_FILE" --profile "$ENGINE" up -d

case "$ENGINE" in
  mongo)    CONTAINER="bench_mongo" ;;
  postgres) CONTAINER="bench_postgres" ;;
esac

echo -n "== Esperando healthcheck de $CONTAINER "
for _ in $(seq 1 60); do
  STATE="$(docker inspect -f '{{.State.Health.Status}}' "$CONTAINER" 2>/dev/null || echo unknown)"
  if [[ "$STATE" == "healthy" ]]; then
    echo " -> healthy"
    echo
    echo "Siguiente paso:  scripts/verify_limits.sh $PROFILE $ENGINE"
    exit 0
  fi
  if [[ "$STATE" == "unhealthy" ]]; then
    echo " -> UNHEALTHY"
    docker logs --tail 40 "$CONTAINER" >&2
    exit 1
  fi
  echo -n "."
  sleep 2
done

echo " -> TIMEOUT (120 s)"
docker logs --tail 40 "$CONTAINER" >&2
exit 1
