#!/usr/bin/env bash
# smoke_f55.sh — prueba de humo de F5.5. La ejecuta Alix EN SU TERMINAL (opción (a)).
#
# Uso:
#   cd ~/benchmark-json-contention
#   sudo -v                 # pide tu contraseña una vez; el runner la renueva sin volver a pedirla
#   scripts/smoke_f55.sh
#
# Por qué en tu terminal: sudo guarda las credenciales por terminal y la sesión
# de Claude no tiene terminal propia; la limpieza de caché (A5) necesita sudo.
#
# Hace 4 corridas. TODO va a results/smoke/: NO son resultados del experimento (F5-g).
#   1. mongodb    PROFILE_C  Q2_MEM_LOW  c=1   ventanas 5/20/5     circuito completo
#   2. postgresql PROFILE_C  Q2_MEM_LOW  c=1   ventanas 5/20/5     circuito completo
#   3. postgresql PROFILE_A  Q1          c=50  ventanas 10/300/10  carga máxima: disco temporal y memoria
#   4. mongodb    PROFILE_A  Q1          c=50  ventanas 10/60/10   carga máxima: memoria del runner
# Las 3 y 4 llevan monitor (scripts/checks/monitor_host.sh) y no capturan plan:
# con 50 consultas huérfanas en el servidor, el plan estaría distorsionado.
#
# Una corrida que falle no detiene las siguientes: al final hay un resumen.
# Duración aproximada: 10–15 minutos. No suspendas el equipo mientras corre.

set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if ! sudo -n true 2>/dev/null; then
  echo "Primero ejecuta:  sudo -v   (y vuelve a lanzar este script en la MISMA terminal)"; exit 2
fi
[[ -x .venv/bin/python ]] || { echo "Falta .venv (F5.1)"; exit 2; }

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
if [[ -e results/smoke ]]; then
  mv results/smoke "results/smoke_anterior_${STAMP}"
  echo "(results/smoke existía: se movió a results/smoke_anterior_${STAMP})"
fi
mkdir -p results/smoke
exec > >(tee "results/smoke/f55_${STAMP}.txt") 2>&1

RUN=(.venv/bin/python -m benchmark_runner.cli run-cell --smoke)
CSV=results/smoke/measurements_smoke.csv
declare -A RC

step() {  # step <n> <descripción> <args...>
  local n="$1" what="$2"; shift 2
  echo; echo "########## $n. $what — $(date -u +%H:%M:%S) UTC"
  "${RUN[@]}" "$@"; RC[$n]=$?
  echo "########## $n terminó con exit ${RC[$n]}"
}

with_monitor() {  # with_monitor <n> <descripción> <args...>
  local n="$1"
  # stderr descartado: al detenerlo con kill puede quejarse de una tubería rota (inofensivo).
  scripts/checks/monitor_host.sh "results/smoke/monitor_${n}.csv" 5 2>/dev/null & local MON=$!
  step "$@"
  kill "$MON" 2>/dev/null; wait "$MON" 2>/dev/null
  echo "   monitor: results/smoke/monitor_${n}.csv"
}

echo "== F5.5 prueba de humo — $STAMP — $(uname -r) — loadavg $(cut -d' ' -f1-3 /proc/loadavg)"
timeout 60 powershell.exe -NoProfile -Command "\$b = Get-CimInstance Win32_Battery; 'host: bateria estado=' + \$b.BatteryStatus + ' (2=corriente) carga=' + \$b.EstimatedChargeRemaining + '%'; powercfg /getactivescheme" 2>/dev/null | tr -d '\r' || true

step 1 "mongodb PROFILE_C Q2_MEM_LOW c=1" --engine mongodb --profile PROFILE_C_SEVERE --query-id Q2_MEM_LOW --concurrency 1
step 2 "postgresql PROFILE_C Q2_MEM_LOW c=1" --engine postgresql --profile PROFILE_C_SEVERE --query-id Q2_MEM_LOW --concurrency 1
with_monitor 3 "postgresql PROFILE_A Q1 c=50 (carga máxima)" --engine postgresql --profile PROFILE_A_BASELINE \
  --query-id Q1 --concurrency 50 --ventanas 10 300 10 --no-explain
with_monitor 4 "mongodb PROFILE_A Q1 c=50 (carga máxima)" --engine mongodb --profile PROFILE_A_BASELINE \
  --query-id Q1 --concurrency 50 --ventanas 10 60 10 --no-explain

echo; echo "########## Validación del CSV de humo"
.venv/bin/python scripts/validate_csv.py "$CSV"; RC[v]=$?

echo; echo "########## Resumen"
for k in 1 2 3 4 v; do echo "   paso $k: exit ${RC[$k]:-no ejecutado}"; done
[[ -f $CSV ]] && { echo; cat "$CSV"; }
echo; echo "Listo. Avísale a Claude: lo leerá todo de results/smoke/ (registro: results/smoke/f55_${STAMP}.txt)."
