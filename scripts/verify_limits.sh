#!/usr/bin/env bash
# verify_limits.sh — comprueba que los límites del perfil se aplicaron DE VERDAD
# y deja evidencia archivada.
#
# Uso:  scripts/verify_limits.sh <a_baseline|b_medium|c_severe> <mongo|postgres>
#
# Por qué existe: docker-compose.yml DECLARA límites; esto comprueba que el
# kernel los IMPUSO. Son cosas distintas. El manual (diapo 5/13) exige anotar
# "límites Docker reales", no los pedidos. Si Compose ignorara `cpus:` en esta
# versión, el experimento correría sin contención y los números no medirían
# nada: este script lo detecta y falla.
#
# Quién lee qué: este script NO lee el cgroup ni docker inspect por su cuenta.
# Lo hace scripts/capture_env.py, que es el único lugar del proyecto con esa
# lógica (R-28). Aquí solo se compara su captura contra los EXPECT_* del perfil:
#   cpu.max         vs  EXPECT_CPU_MAX
#   memory.max      vs  EXPECT_MEMORY_MAX
#   memory.swap.max vs  EXPECT_SWAP_MAX
#   cpuset.cpus.effective vs EXPECT_CPUSET   (F5-c, docker/images.env)
#
# Salida: results/env/f1/<PROFILE_ID>_<engine>_<fecha>.txt  y  .json
#         (el .json es la captura completa de capture_env.py + esperado + veredicto)
# Código de salida: 0 si todo coincide, 1 si algo no coincide, 2 si no se pudo capturar.

set -uo pipefail

PROFILE="${1:-}"
ENGINE="${2:-}"
if [[ -z "$PROFILE" || -z "$ENGINE" ]]; then
  echo "uso: $0 <a_baseline|b_medium|c_severe> <mongo|postgres>" >&2
  exit 2
fi

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
set -a
# shellcheck disable=SC1090
source "$ROOT/docker/images.env"
# shellcheck disable=SC1090
source "$ROOT/docker/profiles/${PROFILE}.env"
set +a

case "$ENGINE" in
  mongo|postgres) ;;
  *) echo "ERROR: motor '$ENGINE' no válido" >&2; exit 2 ;;
esac

# VERIFY_OUTDIR solo se usa en pruebas, para no mezclar sus archivos con la evidencia.
OUTDIR="${VERIFY_OUTDIR:-$ROOT/results/env/f1}"
mkdir -p "$OUTDIR"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"

CAPTURE="$(mktemp)"
trap 'rm -f "$CAPTURE"' EXIT
if ! python3 "$ROOT/scripts/capture_env.py" --engine "$ENGINE" --out "$CAPTURE"; then
  echo "       Levántalo con: scripts/up_profile.sh $PROFILE $ENGINE" >&2
  exit 2
fi

# jget <ruta/separada/por/barras> — un campo de la captura. null -> "null".
# Se separa por "/" porque las claves del cgroup llevan punto (cpu.max).
jget() {
  python3 -c '
import json, sys
d = json.load(open(sys.argv[1]))
for k in sys.argv[2].split("/"):
    d = d.get(k) if isinstance(d, dict) else None
print("null" if d is None else str(d).lower() if isinstance(d, bool) else ",".join(d) if isinstance(d, list) else d)
' "$CAPTURE" "$1"
}

ENGINE_NAME="$(jget engine)"
CONTAINER="$(jget container)"
BASE="$OUTDIR/${PROFILE_ID}_${ENGINE_NAME}_${STAMP}"

ACTUAL_CPU_MAX="$(jget cgroup/limits/cpu.max)"
ACTUAL_MEM_MAX="$(jget cgroup/limits/memory.max)"
ACTUAL_SWAP_MAX="$(jget cgroup/limits/memory.swap.max)"
ACTUAL_CPUSET="$(jget cgroup/limits/cpuset.cpus.effective)"

INSPECT=""
for k in NanoCpus CpuQuota CpuPeriod CpusetCpus Memory MemorySwap MemorySwappiness OOMKilled; do
  INSPECT+="$k=$(jget "docker_inspect/$k") "
done

# El informe se escribe al archivo y DESPUÉS se muestra. No usar "{ ... } | tee":
# cada lado de una tubería corre en un subproceso, el FAIL=1 de check() se
# perdería y el script saldría con 0 aunque hubiera discrepancias. (Ese defecto
# existió en la versión anterior de este script; detectado el 2026-11-01.)
FAIL=0
check() {  # check <etiqueta> <esperado> <obtenido>
  if [[ "$2" == "$3" ]]; then
    printf '  OK    %-16s esperado=%-22s obtenido=%s\n' "$1" "$2" "$3"
  else
    printf '  FALLA %-16s esperado=%-22s obtenido=%s\n' "$1" "$2" "$3"
    FAIL=1
  fi
}

{
  echo "== Verificación de límites reales — F1"
  echo "fecha_utc        : $STAMP"
  echo "perfil           : $PROFILE_ID  (etiqueta del contenedor: $(jget profile_label))"
  echo "motor            : $ENGINE_NAME"
  echo "contenedor       : $CONTAINER"
  echo "imagen (ref.)    : $(jget image/tag)"
  echo "imagen (digest)  : $(jget image/repo_digests)"
  echo "imagen (id)      : $(jget image/id)"
  echo "version motor    : $(jget engine_version)"
  echo "storage engine   : $(jget storage_engine)"
  echo "docker inspect   : ${INSPECT% }"
  echo
  echo "-- cgroup v2 leído DENTRO del contenedor --"
  check "cpu.max"         "$EXPECT_CPU_MAX"    "$ACTUAL_CPU_MAX"
  check "memory.max"      "$EXPECT_MEMORY_MAX" "$ACTUAL_MEM_MAX"
  check "memory.swap.max" "$EXPECT_SWAP_MAX"   "$ACTUAL_SWAP_MAX"
  check "cpuset.cpus.eff" "$EXPECT_CPUSET"     "$ACTUAL_CPUSET"
  echo
  echo "-- mem_swappiness (ver SPEC A7, V8) --"
  echo "  docker inspect MemorySwappiness = $(jget docker_inspect/MemorySwappiness)"
  if [[ "$(jget cgroup/memory_swappiness/present)" == "true" ]]; then
    echo "  cgroup memory.swappiness = $(jget cgroup/memory_swappiness/value)"
  else
    echo "  NOTA: /sys/fs/cgroup/memory.swappiness no existe en este contenedor."
    echo "        cgroup v2 no expone un knob de swappiness por cgroup (era de v1)."
    echo "        La garantia efectiva de 'sin swap' es memory.swap.max=0, verificado arriba."
    echo "        No se marca como fallo: se declara en la seccion 1 del reporte."
  fi
  echo
  echo "-- archivos de métricas que alimentarán el CSV --"
  for f in cpu.stat memory.stat memory.peak memory.events memory.swap.max; do
    if [[ "$(jget "cgroup/metric_files/$f")" == "true" ]]; then
      echo "  OK    presente        /sys/fs/cgroup/$f"
    else
      echo "  FALLA ausente         /sys/fs/cgroup/$f"
      FAIL=1
    fi
  done
  echo
  echo "-- contexto de la VM en el momento de la verificación (capture_env.py) --"
  echo "  kernel  : $(jget host/kernel)  nproc=$(jget host/nproc)"
  echo "  loadavg : $(jget host/loadavg/raw)"
  echo "  memoria : total=$(( $(jget host/memory/MemTotal_kb) / 1024 ))MB disp=$(( $(jget host/memory/MemAvailable_kb) / 1024 ))MB buff/cache=$(( $(jget host/memory/buff_cache_kb) / 1024 ))MB"
  echo "  swap    : total=$(( $(jget host/memory/SwapTotal_kb) / 1024 ))MB used=$(( $(jget host/memory/swap_used_kb) / 1024 ))MB"
  ERRS="$(jget errores)"
  if [[ -n "$ERRS" ]]; then
    echo
    echo "-- errores de captura (los campos afectados quedan en null) --"
    echo "  $ERRS"
  fi
  echo
  if [[ $FAIL -eq 0 ]]; then
    echo "RESULTADO: TODOS LOS LIMITES COINCIDEN"
  else
    echo "RESULTADO: HAY DISCREPANCIAS — no continuar a F2/F3 hasta resolverlas"
  fi
} > "$BASE.txt"
cat "$BASE.txt"

# El JSON de evidencia es la captura completa más lo que se esperaba y el veredicto.
python3 - "$CAPTURE" "$BASE.json" "$STAMP" "$PROFILE_ID" "$EXPECT_CPU_MAX" "$EXPECT_MEMORY_MAX" "$EXPECT_SWAP_MAX" "$FAIL" "$EXPECT_CPUSET" <<'PY'
import json, sys
src, dst, stamp, profile, cpu, mem, swap, fail, cpuset = sys.argv[1:]
d = json.load(open(src))
d = {"fase": "F1", "fecha_utc": stamp, "profile": profile,
     "esperado": {"cpu.max": cpu, "memory.max": mem, "memory.swap.max": swap, "cpuset.cpus.effective": cpuset},
     "coinciden": fail == "0", **d}
open(dst, "w").write(json.dumps(d, ensure_ascii=False, indent=2) + "\n")
PY

echo
echo "Evidencia archivada en:"
echo "  $BASE.txt"
echo "  $BASE.json"
exit $FAIL
