#!/usr/bin/env bash
# up_monitoring.sh — levanta Prometheus + cAdvisor + node_exporter (F6, R-23) y espera a up==1.
#
# Uso:  scripts/up_monitoring.sh
#
# Es un proyecto de compose aparte ("benchmon", F6-b): up_profile.sh y
# down_profile.sh no lo tocan, así que puede quedarse arriba durante toda la
# matriz mientras el motor se baja y se sube en cada repetición.

set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="$ROOT/monitoring/docker-compose.monitoring.yml"
PROM="http://127.0.0.1:9090"

set -a
# shellcheck disable=SC1090
source "$ROOT/docker/images.env"
set +a

docker compose -f "$COMPOSE_FILE" up -d

# up==1 en los tres jobs. Prometheus tarda unos segundos en hacer el primer scrape.
echo -n "== Esperando up==1 en prometheus, cadvisor y node "
for _ in $(seq 1 60); do
  N="$(curl -s --max-time 2 "$PROM/api/v1/query" --data-urlencode 'query=sum(up)' \
       | python3 -c 'import sys,json; r=json.load(sys.stdin)["data"]["result"]; print(int(float(r[0]["value"][1])) if r else 0)' 2>/dev/null || echo 0)"
  if [[ "$N" == "3" ]]; then echo " -> 3/3"; exit 0; fi
  echo -n "."
  sleep 1
done
echo " -> TIMEOUT (60 s), up=$N de 3"
curl -s --max-time 2 "$PROM/api/v1/targets" | python3 -m json.tool 2>/dev/null | grep -E '"(job|health|lastError)"' >&2 || true
exit 1
