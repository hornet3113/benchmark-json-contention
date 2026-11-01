#!/usr/bin/env bash
# run_cold_f73.sh — F7.3: ¿cuánto tarda la PRIMERA consulta en frío, por perfil y motor?
#
# Uso, EN TU TERMINAL:
#   cd ~/benchmark-json-contention
#   scripts/up_monitoring.sh          # si no está arriba
#   sudo -v
#   scripts/run_cold_f73.sh                    # los 3 perfiles × 2 motores × 3 queries (18 corridas)
#   scripts/run_cold_f73.sh a_baseline         # solo un perfil
#
# Casilla de PLAN F7 (ampliada por Alix a los tres perfiles): medir la primera
# consulta en frío y compararla con los 60 s de calentamiento del manual. Si no
# cabe, los P95/P99 de ese perfil salen contaminados y se declara como limitación
# del protocolo, no como error del runner.
#
# Cada corrida es el procedimiento REAL de una repetición (flush de caché, motor
# nuevo, calentamiento de 60 s) pero con la ventana de medición recortada a 30 s:
# lo que se mide está en el calentamiento, no en la ventana. Por eso va con
# --smoke (NO son resultados del benchmark) y con --salida f7_frio, para no pisar
# results/smoke/. c=50 es el peor caso: 50 primeras consultas en frío a la vez.
#
# Duración: ~2.5 min por corrida si la primera consulta termina → ~45 min. Puede
# pasar de 1.5 h: con Q1 y c=50 en PROFILE_C la primera consulta puede agotar el
# límite de 300 s, y entonces esa celda tarda ~6 min. Un timeout NO es un fallo
# aquí: es el hallazgo (la primera consulta no cabe en ningún calentamiento) y la
# celda sale con status=error, que en humo no importa.
# Cargador conectado y sin suspensión: una celda interrumpida no sirve.

set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
sudo -n true 2>/dev/null || { echo "Primero ejecuta:  sudo -v   (y vuelve a lanzar en la MISMA terminal)"; exit 2; }

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p results/f7_frio
exec > >(tee "results/f7_frio/frio_${STAMP}.txt") 2>&1

echo "== F7.3 primera consulta en frío — $STAMP — loadavg $(cut -d' ' -f1-3 /proc/loadavg)"
echo "== ventanas 60/30/5 (el dato está en el calentamiento) · c=50 · Q1, Q2_MEM_LOW y Q2_MEM_HIGH"
timeout 60 powershell.exe -NoProfile -Command "\$b = Get-CimInstance Win32_Battery; 'host: bateria estado=' + \$b.BatteryStatus + ' carga=' + \$b.EstimatedChargeRemaining + '%'; powercfg /getactivescheme" 2>/dev/null | tr -d '\r' || true

if [[ $# -gt 0 ]]; then PROFILES=("$@"); else PROFILES=(a_baseline b_medium c_severe); fi
declare -A PROFILE_ID=([a_baseline]=PROFILE_A_BASELINE [b_medium]=PROFILE_B_MEDIUM [c_severe]=PROFILE_C_SEVERE)

for P in "${PROFILES[@]}"; do
  for ENGINE in postgresql mongodb; do
    for QID in Q1 Q2_MEM_LOW Q2_MEM_HIGH; do
      echo; echo "########## ${PROFILE_ID[$P]} · $ENGINE · $QID · c=50 — $(date -u +%H:%M:%S) UTC"
      .venv/bin/python -m benchmark_runner.cli run-cell --smoke --salida f7_frio --ventanas 60 30 5 \
        --engine "$ENGINE" --profile "${PROFILE_ID[$P]}" --query-id "$QID" --concurrency 50 --runs 1
      echo "########## exit $?"
    done
  done
done

echo; echo "########## Análisis"
.venv/bin/python scripts/checks/check_cold_f73.py
echo; echo "Listo. Avísale a Claude (registro: results/f7_frio/frio_${STAMP}.txt)."
