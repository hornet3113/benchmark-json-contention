#!/usr/bin/env bash
# down_monitoring.sh — baja el monitoreo (F6). CONSERVA la base de Prometheus
# (volumen benchmon_prom_data); las ventanas medidas ya se exportan a results/ (F6-e).

set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
set -a
# shellcheck disable=SC1090
source "$ROOT/docker/images.env"
set +a
docker compose -f "$ROOT/monitoring/docker-compose.monitoring.yml" down
echo "Listo."
