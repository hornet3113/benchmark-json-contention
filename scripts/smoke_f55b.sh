#!/usr/bin/env bash
# smoke_f55b.sh — comparación del runner: 50 procesos frente a 10 × 5 hilos (F5.5, decisión 2 de Alix).
#
# Uso, EN TU TERMINAL (igual que smoke_f55.sh):
#   cd ~/benchmark-json-contention
#   sudo -v
#   scripts/smoke_f55b.sh              # los dos motores
#   scripts/smoke_f55b.sh mongodb      # solo uno
#
# Por motor, A-B-A en la celda Q2_MEM_LOW · PROFILE_A · c=50, ventanas 30/120/10:
#   run 1 = 50 procesos × 1 hilo · run 2 = 10 procesos × 5 hilos · run 3 = 50 procesos × 1 hilo
# Cada corrida lleva monitor (memoria del runner y de la VM) y una foto de la
# actividad del motor cada 10 s dentro de la ventana (F5.5b, criterio v3). Al final,
# scripts/checks/compare_runner_modes.py aplica el criterio fijado de antemano.
# Todo va a results/smoke/ (lo anterior se mueve a results/smoke_anterior_<fecha>).
# Duración aproximada: 20–25 minutos. No suspendas el equipo.

set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
sudo -n true 2>/dev/null || { echo "Primero ejecuta:  sudo -v   (y vuelve a lanzar en la MISMA terminal)"; exit 2; }

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
[[ -e results/smoke ]] && mv results/smoke "results/smoke_anterior_${STAMP}" && echo "(results/smoke anterior → results/smoke_anterior_${STAMP})"
mkdir -p results/smoke
exec > >(tee "results/smoke/f55b_${STAMP}.txt") 2>&1

echo "== F5.5b 50 procesos frente a 10×5 hilos — $STAMP — loadavg $(cut -d' ' -f1-3 /proc/loadavg)"
timeout 60 powershell.exe -NoProfile -Command "\$b = Get-CimInstance Win32_Battery; 'host: bateria estado=' + \$b.BatteryStatus + ' carga=' + \$b.EstimatedChargeRemaining + '%'; powercfg /getactivescheme" 2>/dev/null | tr -d '\r' || true

if [[ $# -gt 0 ]]; then ENGINES=("$@"); else ENGINES=(postgresql mongodb); fi
for ENGINE in "${ENGINES[@]}"; do
  for SPEC in "1 50 A1" "2 10 B" "3 50 A2"; do
    read -r RUNNO PROCS MODE <<<"$SPEC"
    echo; echo "########## $ENGINE · run $RUNNO · $MODE ($PROCS procesos) — $(date -u +%H:%M:%S) UTC"
    scripts/checks/monitor_host.sh "results/smoke/monitor_${ENGINE}_${MODE}.csv" 5 2>/dev/null & MON=$!
    .venv/bin/python -m benchmark_runner.cli run-cell --smoke --ventanas 30 120 10 --procesos "$PROCS" \
      --actividad-cada 10 \
      --engine "$ENGINE" --profile PROFILE_A_BASELINE --query-id Q2_MEM_LOW --concurrency 50 --runs "$RUNNO"
    echo "########## exit $?"
    kill "$MON" 2>/dev/null; wait "$MON" 2>/dev/null
  done
done

echo; echo "########## Validación del CSV y comparación"
.venv/bin/python scripts/validate_csv.py results/smoke/measurements_smoke.csv
.venv/bin/python scripts/checks/compare_runner_modes.py
echo; echo "Listo. Avísale a Claude (registro: results/smoke/f55b_${STAMP}.txt)."
