#!/usr/bin/env bash
# run_memory_f74.sh — F7.4: ¿aguanta la memoria de la VM con la ventana real en PROFILE_A?
#
# Uso, EN TU TERMINAL:
#   cd ~/benchmark-json-contention
#   scripts/up_monitoring.sh          # si no está arriba
#   sudo -v
#   scripts/run_memory_f74.sh
#
# Casilla que F6 pasó a F7: con PROFILE_A el motor tiene 4 GiB, el runner con
# c=50 usa ~460 MiB, el monitoreo ~135 MiB y Prometheus llega a ~392 MiB con su
# caché; la VM tiene 7.159 GiB (L3, D-WSL1). En el humo de F6.4 el mínimo de
# MemAvailable fue 3.9 GiB, pero con ventanas de 120 s. Aquí se mide con la
# ventana REAL de 300 s y con Q1, que es la query que más memoria mueve
# (en F3 volcó 1.4 GiB a disco en Postgres).
#
# Una repetición por motor, ventanas reales 60/300/60, c=50. Va con --smoke
# (NO son resultados del benchmark; se mide la memoria, no el rendimiento) y con
# --salida f7_memoria, para no pisar results/smoke/.
#
# Duración: ~8 min por motor → ~16 min. Cargador conectado y sin suspensión.

set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
# V7: vale la regla instalada o `sudo -v`; la función conoce las dos vías.
# shellcheck source=scripts/sudo_listo.sh
source "$ROOT/scripts/sudo_listo.sh"
sudo_listo || exit 2

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p results/f7_memoria
exec > >(tee "results/f7_memoria/memoria_${STAMP}.txt") 2>&1

echo "== F7.4 memoria con la ventana real en PROFILE_A — $STAMP — loadavg $(cut -d' ' -f1-3 /proc/loadavg)"
echo "== ventanas 60/300/60 · PROFILE_A_BASELINE · Q1 · c=50 · 1 repetición por motor"
free -m | sed 's/^/   /'
timeout 60 powershell.exe -NoProfile -Command "\$b = Get-CimInstance Win32_Battery; 'host: bateria estado=' + \$b.BatteryStatus + ' carga=' + \$b.EstimatedChargeRemaining + '%'; powercfg /getactivescheme" 2>/dev/null | tr -d '\r' || true

for ENGINE in postgresql mongodb; do
  echo; echo "########## $ENGINE · PROFILE_A_BASELINE · Q1 · c=50 — $(date -u +%H:%M:%S) UTC"
  # El monitor del host añade lo que el runner no registra: memoria de la VM,
  # swap, procesos y RSS del árbol del runner, y temporales de Postgres.
  scripts/checks/monitor_host.sh "results/f7_memoria/monitor_${ENGINE}.csv" 5 2>/dev/null & MON=$!
  .venv/bin/python -m benchmark_runner.cli run-cell --smoke --salida f7_memoria --ventanas 60 300 60 \
    --engine "$ENGINE" --profile PROFILE_A_BASELINE --query-id Q1 --concurrency 50 --runs 1
  echo "########## exit $?"
  kill "$MON" 2>/dev/null; wait "$MON" 2>/dev/null
done

echo; echo "########## Análisis (serie de 1 s, telemetría, memoria de la VM y costo del monitoreo)"
.venv/bin/python scripts/checks/check_smoke_f64.py results/f7_memoria
echo; echo "########## Memoria del árbol del runner y de la VM (monitor del host)"
for ENGINE in postgresql mongodb; do
  echo "-- $ENGINE: mínimo de mem_disp_mb, máximo de swap y de runner_rss_mb"
  awk -F, 'NR>1 && $2!="" {if(m==""||$2<m)m=$2; if($3>s)s=$3; if($5>r)r=$5}
           END{printf "   mem_disp_min=%s MB  swap_max=%s MB  runner_rss_max=%s MB\n", m, s, r}' \
      "results/f7_memoria/monitor_${ENGINE}.csv"
done
echo; echo "Listo. Avísale a Claude (registro: results/f7_memoria/memoria_${STAMP}.txt)."
