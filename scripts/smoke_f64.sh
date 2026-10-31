#!/usr/bin/env bash
# smoke_f64.sh — humo de F6.4: el runner con telemetría (comprobación previa, exportación y serie de 1 s).
#
# Uso, EN TU TERMINAL (igual que smoke_f55b.sh):
#   cd ~/benchmark-json-contention
#   scripts/up_monitoring.sh           # si no está arriba (la comprobación previa también lo intenta)
#   sudo -v
#   scripts/smoke_f64.sh
#
# Cuatro repeticiones, ventanas 30/120/10 (≥ 60 s de medición, F6-h):
#   postgresql y mongodb · PROFILE_A · Q2_MEM_LOW · c=50  → carga máxima del runner en las CPUs del
#                                                          monitoreo (8–11) y PROFILE_A, el de menos
#                                                          margen de memoria en la VM
#   postgresql y mongodb · PROFILE_C · Q2_MEM_LOW · c=1   → throttling real: control cruzado columna/Prometheus
# Al final, scripts/checks/check_smoke_f64.py compara cada fila y su serie de 1 s con Prometheus.
# Todo va a results/smoke/ (lo anterior se mueve a results/smoke_anterior_<fecha>).
# Duración aproximada: 15–20 minutos. No suspendas el equipo.

set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
sudo -n true 2>/dev/null || { echo "Primero ejecuta:  sudo -v   (y vuelve a lanzar en la MISMA terminal)"; exit 2; }

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
[[ -e results/smoke ]] && mv results/smoke "results/smoke_anterior_${STAMP}" && echo "(results/smoke anterior → results/smoke_anterior_${STAMP})"
mkdir -p results/smoke
exec > >(tee "results/smoke/f64_${STAMP}.txt") 2>&1

echo "== F6.4 humo con telemetría — $STAMP — loadavg $(cut -d' ' -f1-3 /proc/loadavg)"
timeout 60 powershell.exe -NoProfile -Command "\$b = Get-CimInstance Win32_Battery; 'host: bateria estado=' + \$b.BatteryStatus + ' carga=' + \$b.EstimatedChargeRemaining + '%'; powercfg /getactivescheme" 2>/dev/null | tr -d '\r' || true

for SPEC in "postgresql PROFILE_A_BASELINE 50" "mongodb PROFILE_A_BASELINE 50" \
            "postgresql PROFILE_C_SEVERE 1" "mongodb PROFILE_C_SEVERE 1"; do
  read -r ENGINE PROFILE CONC <<<"$SPEC"
  echo; echo "########## $ENGINE · $PROFILE · c=$CONC — $(date -u +%H:%M:%S) UTC"
  .venv/bin/python -m benchmark_runner.cli run-cell --smoke --ventanas 30 120 10 \
    --engine "$ENGINE" --profile "$PROFILE" --query-id Q2_MEM_LOW --concurrency "$CONC" --runs 1
  echo "########## exit $?"
done

echo; echo "########## Validación del CSV y comparación con Prometheus"
.venv/bin/python scripts/validate_csv.py results/smoke/measurements_smoke.csv
.venv/bin/python scripts/checks/check_smoke_f64.py
echo; echo "Listo. Avísale a Claude (registro: results/smoke/f64_${STAMP}.txt)."
