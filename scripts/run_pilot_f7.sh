#!/usr/bin/env bash
# run_pilot_f7.sh — celda piloto de F7: MEDICIÓN REAL (60/300/60 s), 3 repeticiones por motor.
#
# Uso, EN TU TERMINAL:
#   cd ~/benchmark-json-contention
#   scripts/up_monitoring.sh          # si no está arriba
#   sudo -v
#   scripts/run_pilot_f7.sh           # los dos motores (Mongo primero, como pide PLAN F7)
#   scripts/run_pilot_f7.sh mongodb   # solo uno
#
# Celda: <motor> × PROFILE_C_SEVERE × Q2_MEM_LOW × c=1, repeticiones 1 2 3 (PLAN F7).
# Las filas van a results/f7/measurements.csv (F7-a), NO al CSV de la matriz.
# Duración: ~7-8 min por repetición → ~45-50 min en total. No suspendas el equipo
# y ten el cargador conectado: con batería, Windows baja la frecuencia y eso puede
# crear la tendencia que este piloto busca descartar (F7-b).

set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
sudo -n true 2>/dev/null || { echo "Primero ejecuta:  sudo -v   (y vuelve a lanzar en la MISMA terminal)"; exit 2; }

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p results/f7
exec > >(tee "results/f7/pilot_${STAMP}.txt") 2>&1

echo "== F7 celda piloto (MEDICIÓN REAL) — $STAMP — loadavg $(cut -d' ' -f1-3 /proc/loadavg)"
echo "== ventanas 60/300/60 · PROFILE_C_SEVERE · Q2_MEM_LOW · c=1 · runs 1 2 3"
# Energía: BatteryStatus 2 = conectado a la red. Queda en el registro para poder
# descartarlo como causa si aparece una tendencia (F7-b).
timeout 60 powershell.exe -NoProfile -Command "\$b = Get-CimInstance Win32_Battery; 'host: bateria estado=' + \$b.BatteryStatus + ' carga=' + \$b.EstimatedChargeRemaining + '%'; powercfg /getactivescheme" 2>/dev/null | tr -d '\r' || true

if [[ $# -gt 0 ]]; then ENGINES=("$@"); else ENGINES=(mongodb postgresql); fi
for ENGINE in "${ENGINES[@]}"; do
  echo; echo "########## $ENGINE — $(date -u +%H:%M:%S) UTC"
  scripts/checks/monitor_host.sh "results/f7/monitor_${ENGINE}.csv" 5 2>/dev/null & MON=$!
  .venv/bin/python -m benchmark_runner.cli run-cell --confirmo-medicion-real --salida f7 \
    --engine "$ENGINE" --profile PROFILE_C_SEVERE --query-id Q2_MEM_LOW --concurrency 1 --runs 1 2 3
  echo "########## exit $?"
  kill "$MON" 2>/dev/null; wait "$MON" 2>/dev/null
done

echo; echo "########## Validación del CSV y análisis del piloto"
.venv/bin/python scripts/validate_csv.py results/f7/measurements.csv
.venv/bin/python scripts/checks/check_pilot_f7.py
echo; echo "Listo. Avísale a Claude (registro: results/f7/pilot_${STAMP}.txt)."
