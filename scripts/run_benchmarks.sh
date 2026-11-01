#!/usr/bin/env bash
# run_benchmarks.sh — recorre la matriz completa, reanudable (F8; nombre exigido por R-25).
#
# Uso, EN TU TERMINAL:
#   cd ~/benchmark-json-contention
#   scripts/up_monitoring.sh
#   sudo -v
#   scripts/run_benchmarks.sh --listar                 # qué falta, sin correr nada (no necesita sudo)
#   scripts/run_benchmarks.sh --humo                   # prueba de 2 celdas con ventanas 5/20/5
#   scripts/run_benchmarks.sh                          # tanda 1: Q1 + Q2_MEM_LOW (36 celdas, 108 corridas)
#   scripts/run_benchmarks.sh --todo                   # las 54 celdas (162 corridas)
#   scripts/run_benchmarks.sh --matriz 36 --q2-variante MEM_LOW
#   scripts/run_benchmarks.sh --motor mongodb --perfil PROFILE_C_SEVERE   # un bloque
#   scripts/run_benchmarks.sh --max-celdas 8           # cortar la sesión tras 8 celdas
#
# REANUDABLE: antes de cada celda mira qué repeticiones ya tienen fila en el CSV
# (benchmark_runner/schedule.py) y solo corre las que faltan. Si se corta la
# sesión, se vuelve a lanzar el mismo comando y sigue donde quedó. No repite ni
# se salta nada; la clave es (engine, profile, query_id, concurrency, run_number).
#
# A2 (decisión de Alix, 2026-11-02, mientras el docente no responda): por defecto
# corre la TANDA 1 = Q1 + Q2_MEM_LOW, la variante restrictiva, que es trabajo
# correcto con los dos conteos. Si el docente dice 54, se añade Q2_MEM_HIGH con
# --todo; si dice 36, solo se cambia la etiqueta Q2_MEM_LOW → Q2.
#
# Solo un motor arriba a la vez, y cada repetición baja el motor, limpia la caché
# y lo vuelve a levantar (A5, lifecycle.prepare). El sudo lo renueva el runner
# mientras corre; si la caché de sudo caduca entre celdas, el script se detiene y
# lo dice, en vez de dejar repeticiones sin flush.

set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

MATRIZ=54
Q2_VARIANTE=""
SALIDA=""
HUMO=0
TODO=0
LISTAR=0
MAX_CELDAS=0
FALLOS_SEGUIDOS_MAX=3
declare -a MOTORES=() PERFILES=() QUERIES=() CONCURRENCIAS=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --matriz)        MATRIZ="$2"; shift 2 ;;
    --q2-variante)   Q2_VARIANTE="$2"; shift 2 ;;
    --motor)         MOTORES+=("$2"); shift 2 ;;
    --perfil)        PERFILES+=("$2"); shift 2 ;;
    --query)         QUERIES+=("$2"); shift 2 ;;
    --concurrencia)  CONCURRENCIAS+=("$2"); shift 2 ;;
    --salida)        SALIDA="$2"; shift 2 ;;
    --max-celdas)    MAX_CELDAS="$2"; shift 2 ;;
    --todo)          TODO=1; shift ;;
    --humo)          HUMO=1; shift ;;
    --listar)        LISTAR=1; shift ;;
    -h|--help)       sed -n '2,32p' "$0"; exit 0 ;;
    *) echo "ERROR: opción desconocida: $1" >&2; exit 2 ;;
  esac
done

# Por defecto, tanda 1 (A2). Con --todo o con la matriz de 36 no se filtra por query.
if [[ ${#QUERIES[@]} -eq 0 && $TODO -eq 0 && "$MATRIZ" == "54" ]]; then
  QUERIES=(Q1 Q2_MEM_LOW)
fi

if [[ $HUMO -eq 1 ]]; then
  # Humo: 2 celdas, ventanas 5/20/5, salida aparte. NO son resultados (F5-g).
  [[ -z "$SALIDA" ]] && SALIDA="f8_humo"
  # 2 celdas (un motor cada una) × 1 repetición: comprueba el recorrido, el CSV y
  # la reanudación sin gastar media hora. Son ~40 s por repetición.
  MOTORES=(mongodb postgresql); PERFILES=(PROFILE_C_SEVERE); QUERIES=(Q2_MEM_LOW); CONCURRENCIAS=(1)
fi

# Dónde está el CSV que se consulta para reanudar: el mismo que escribirá el runner.
if [[ -n "$SALIDA" ]]; then
  BASE="results/$SALIDA"
  CSV="$BASE/$([[ $HUMO -eq 1 ]] && echo measurements_smoke.csv || echo measurements.csv)"
else
  BASE="results"; CSV="results/measurements.csv"
fi

# --- qué falta -----------------------------------------------------------------
# Una sola llamada a Python: imprime las líneas de resumen con "#" delante y, al
# final, una línea por celda pendiente ("motor perfil query concurrencia runs").
SALIDA_PEND="$(.venv/bin/python - "$CSV" "$MATRIZ" "$Q2_VARIANTE" \
    "$(IFS=,; echo "${MOTORES[*]:-}")" "$(IFS=,; echo "${PERFILES[*]:-}")" "$(IFS=,; echo "${QUERIES[*]:-}")" \
    "$(IFS=,; echo "${CONCURRENCIAS[*]:-}")" <<'PY'
import sys
from pathlib import Path
sys.path.insert(0, ".")
from benchmark_runner import schedule

csv_path, mode, variant, engines, profiles, queries, concs = sys.argv[1:8]
mode, variant = int(mode), (variant or None)
split = lambda s: tuple(x for x in s.split(",") if x) or None
res = schedule.summary(Path(csv_path), mode, variant)
print("# corridas de la matriz: {} · hechas: {} · faltan: {}".format(
    res["corridas_de_la_matriz"], res["hechas"], res["faltan"]))
ajenas = res["ajenas_a_esta_matriz"]
if ajenas:
    print("# AVISO: {} fila(s) del CSV no pertenecen a esta matriz (A2): {}".format(len(ajenas), ajenas[:3]))
conc_filter = tuple(int(x) for x in concs.split(",") if x) or None
for cell, runs in schedule.pending(Path(csv_path), mode, variant,
                                   split(engines), split(profiles), split(queries), conc_filter):
    print(cell.engine, cell.profile, cell.query_id, cell.concurrency,
          ",".join(str(r) for r in runs))
PY
)" || { echo "ERROR: no se pudo calcular lo pendiente" >&2; exit 1; }

echo "== Matriz de $MATRIZ celdas${Q2_VARIANTE:+ (variante $Q2_VARIANTE)} · CSV: $CSV"
echo "$SALIDA_PEND" | sed -n 's/^# /   /p'
readarray -t CELDAS < <(echo "$SALIDA_PEND" | grep -v '^#' | grep -v '^$')
# --max-celdas recorta la SESIÓN, así que se recorta aquí: el conteo, el tiempo
# estimado y el listado hablan de lo que de verdad va a correr, no de todo lo pendiente.
if [[ "$MAX_CELDAS" -gt 0 && ${#CELDAS[@]} -gt "$MAX_CELDAS" ]]; then
  RECORTADAS=$(( ${#CELDAS[@]} - MAX_CELDAS ))
  CELDAS=("${CELDAS[@]:0:$MAX_CELDAS}")
  echo "   (--max-celdas $MAX_CELDAS: quedan $RECORTADAS celda(s) pendientes para la próxima sesión)"
fi

TOTAL_RUNS=0
for L in "${CELDAS[@]}"; do
  if [[ $HUMO -eq 1 ]]; then
    TOTAL_RUNS=$((TOTAL_RUNS + 1))        # el humo corre solo la primera repetición que falte
  else
    N="$(echo "${L##* }" | tr -cd ',' | wc -c)"
    TOTAL_RUNS=$((TOTAL_RUNS + N + 1))
  fi
done
echo "   en esta sesión: ${#CELDAS[@]} celda(s), $TOTAL_RUNS repetición(es)"
if [[ $HUMO -eq 0 ]]; then
  printf "   tiempo estimado: %.1f h (448 s por repetición, medido en el piloto F7.2)\n" \
    "$(echo "$TOTAL_RUNS" | awk '{print $1*448/3600}')"
fi

if [[ ${#CELDAS[@]} -eq 0 ]]; then echo "   nada que correr: la matriz está completa."; exit 0; fi
if [[ $LISTAR -eq 1 ]]; then
  printf '   %s\n' "${CELDAS[@]}"
  exit 0
fi

# --- correr --------------------------------------------------------------------
# V7: vale la regla instalada o `sudo -v`; la función conoce las dos vías.
# shellcheck source=scripts/sudo_listo.sh
source "$ROOT/scripts/sudo_listo.sh"
sudo_listo || exit 2
mkdir -p "$BASE"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
LOG="$BASE/run_benchmarks_${STAMP}.txt"
exec > >(tee "$LOG") 2>&1

echo "== run_benchmarks.sh — $STAMP — loadavg $(cut -d' ' -f1-3 /proc/loadavg)"
timeout 60 powershell.exe -NoProfile -Command "\$b = Get-CimInstance Win32_Battery; 'host: bateria estado=' + \$b.BatteryStatus + ' carga=' + \$b.EstimatedChargeRemaining + '%'; powercfg /getactivescheme" 2>/dev/null | tr -d '\r' || true

HECHAS=0; FALLOS=0; SEGUIDOS=0; I=0
for L in "${CELDAS[@]}"; do
  read -r ENGINE PROFILE QID CONC RUNS <<<"$L"
  # En humo, solo la primera repetición que falte: así no duplica filas al relanzarlo.
  [[ $HUMO -eq 1 ]] && RUNS="${RUNS%%,*}"
  I=$((I + 1))
  echo; echo "########## [$I/${#CELDAS[@]}] $ENGINE · $PROFILE · $QID · c=$CONC · runs $RUNS — $(date -u +%H:%M:%S) UTC"

  # La caché de sudo caduca (~15 min). Comprobar ANTES de cada celda: si caducó, una
  # repetición correría sin flush o colgada pidiendo contraseña (V7). Con la regla de
  # V7 instalada no caduca nada, y `sudo_via` lo sabe.
  if [[ "$(sudo_via)" == ninguna ]]; then
    echo "== DETENIDO: ya no se puede limpiar la caché sin contraseña (la de sudo caducó)."
    echo "   Ejecuta 'sudo -v' y vuelve a lanzar el mismo comando, o instala la regla de V7."
    break
  fi

  declare -a OPTS=(--engine "$ENGINE" --profile "$PROFILE" --query-id "$QID" --concurrency "$CONC"
                   --runs ${RUNS//,/ } --matrix "$MATRIZ")
  [[ -n "$Q2_VARIANTE" ]] && OPTS+=(--q2-variant "$Q2_VARIANTE")
  if [[ $HUMO -eq 1 ]]; then
    OPTS+=(--smoke --ventanas 5 20 5 --salida "$SALIDA")
  else
    OPTS+=(--confirmo-medicion-real)
    [[ -n "$SALIDA" ]] && OPTS+=(--salida "$SALIDA")
  fi

  if .venv/bin/python -m benchmark_runner.cli run-cell "${OPTS[@]}"; then
    HECHAS=$((HECHAS + 1)); SEGUIDOS=0
  else
    RC=$?
    if [[ $RC -eq 3 ]]; then
      # R-08: el dataset no está intacto tras un OOM. Parar en seco, no "seguir con la
      # siguiente": todo lo que se midiera después sería sobre otro dataset.
      echo "== DETENIDO: dataset dañado tras un OOM. Recarga con scripts/load_dataset.sh"
      echo "   (DESTRUCTIVO), verifica con scripts/run_gate.sh y vuelve a lanzar."
      FALLOS=$((FALLOS + 1))
      break
    fi
    echo "########## celda con fallo (exit $RC); se anota y se sigue con la siguiente"
    FALLOS=$((FALLOS + 1)); SEGUIDOS=$((SEGUIDOS + 1))
    if [[ $SEGUIDOS -ge $FALLOS_SEGUIDOS_MAX ]]; then
      echo "== DETENIDO: $SEGUIDOS celdas seguidas con fallo. Revisa antes de seguir "
      echo "   (results/*/abortadas.jsonl y el log de arriba)."
      break
    fi
  fi
done

echo; echo "########## Resumen de la sesión: $HECHAS celda(s) completas, $FALLOS con fallo"
.venv/bin/python scripts/validate_csv.py "$CSV" || true
[[ "$MAX_CELDAS" -gt 0 ]] && echo "Corte pedido con --max-celdas $MAX_CELDAS: vuelve a lanzar el mismo comando para seguir."
echo "Para ver qué queda:  scripts/run_benchmarks.sh --listar${SALIDA:+ --salida $SALIDA}${TODO:+ --todo}"
echo "Registro: $LOG"
