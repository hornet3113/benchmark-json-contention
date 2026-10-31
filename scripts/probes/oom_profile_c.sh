#!/usr/bin/env bash
# oom_profile_c.sh — prueba negativa de F1: un contenedor con los límites de
# PROFILE_C que pide 2 GiB debe morir por OOM, y memory.events debe registrarlo.
#
# Uso:  scripts/probes/oom_profile_c.sh
#
# ESTO ES UNA SONDA, NO UN RESULTADO DEL BENCHMARK. No usa los motores, no
# corre Q1 ni Q2 y no produce filas del CSV (CLAUDE.md, SPEC A12). Demuestra
# que el instrumento puede observar un OOM si ocurre.
#
# Cómo funciona:
#   - Contenedor desechable con cpus/mem/memswap leídos de c_severe.env, así
#     que memory.max=1 GiB y memory.swap.max=0: no hay swap donde escapar.
#   - "head -c 2G /dev/zero | tail" pide memoria: /dev/zero no tiene saltos de
#     línea, así que tail acumula los 2 GiB como una sola línea en RAM.
#   - El kernel mata a ese proceso (no al contenedor entero) al pasar de 1 GiB.
#     El sh que lo lanzó sobrevive, lee memory.events DESDE DENTRO del cgroup
#     y sale con el código del proceso muerto (137 = 128 + SIGKILL).
#
# Pasa si: código de salida 137  Y  oom_kill >= 1 en memory.events.
# Además registra State.OOMKilled de docker inspect (SPEC A6 usa las dos fuentes).
#
# Salida: results/env/f1/OOM_<PROFILE_ID>_<fecha>.txt
# Código de salida: 0 si pasa, 1 si no.

set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
set -a
# shellcheck disable=SC1090
source "$ROOT/docker/images.env"
# shellcheck disable=SC1090
source "$ROOT/docker/profiles/c_severe.env"
set +a

# Imagen ya descargada en F1; solo se usan sh, head y tail de coreutils.
PROBE_IMAGE="$MONGO_IMAGE"
CONTAINER="bench_oom_probe"
ALLOC="2G"

OUTDIR="$ROOT/results/env/f1"
mkdir -p "$OUTDIR"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OUT="$OUTDIR/OOM_${PROFILE_ID}_${STAMP}.txt"

docker rm -f "$CONTAINER" >/dev/null 2>&1

INNER='head -c '"$ALLOC"' /dev/zero | tail > /dev/null
rc=$?
echo "rc_asignador=$rc"
echo "--- memory.max";    cat /sys/fs/cgroup/memory.max
echo "--- memory.swap.max"; cat /sys/fs/cgroup/memory.swap.max
echo "--- memory.peak";   cat /sys/fs/cgroup/memory.peak
echo "--- memory.events"; cat /sys/fs/cgroup/memory.events
exit $rc'

# Todo lo que se imprima a partir de aquí queda también en el archivo de evidencia.
exec > >(tee "$OUT") 2>&1

{
  echo "== Sonda OOM — F1 — $STAMP"
  echo "perfil     : $PROFILE_ID  (cpus=$CPUS_LIMIT mem=$MEM_LIMIT memswap=$MEMSWAP_LIMIT)"
  echo "imagen     : $PROBE_IMAGE"
  echo "asignacion : $ALLOC  (head -c $ALLOC /dev/zero | tail)"
  echo "VM antes   : $(free -m | awk '/^Mem:/{print "used="$3"MB disp="$7"MB"}') $(free -m | awk '/^Swap:/{print "swap_used="$3"MB"}')"
  echo
  echo "-- salida del contenedor (leída desde dentro del cgroup) --"
  docker run --name "$CONTAINER" \
    --cpus="$CPUS_LIMIT" --memory="$MEM_LIMIT" --memory-swap="$MEMSWAP_LIMIT" \
    --entrypoint sh "$PROBE_IMAGE" -c "$INNER" 2>&1
  echo
  EXIT_CODE="$(docker inspect "$CONTAINER" --format '{{.State.ExitCode}}')"
  OOM_FLAG="$(docker inspect "$CONTAINER" --format '{{.State.OOMKilled}}')"
  OOM_KILLS="$(docker logs "$CONTAINER" 2>&1 | awk '$1=="oom_kill"{print $2}')"
  echo "-- docker inspect --"
  echo "  State.ExitCode  = $EXIT_CODE"
  echo "  State.OOMKilled = $OOM_FLAG"
  echo "  HostConfig      = $(docker inspect "$CONTAINER" --format 'NanoCpus={{.HostConfig.NanoCpus}} Memory={{.HostConfig.Memory}} MemorySwap={{.HostConfig.MemorySwap}}')"
  echo
  echo "VM despues : $(free -m | awk '/^Mem:/{print "used="$3"MB disp="$7"MB"}') $(free -m | awk '/^Swap:/{print "swap_used="$3"MB"}')"
  echo
  if [[ "$EXIT_CODE" == "137" && "${OOM_KILLS:-0}" -ge 1 ]]; then
    echo "RESULTADO: OOM OBSERVADO (exit=137, oom_kill=$OOM_KILLS, OOMKilled=$OOM_FLAG)"
    PASS=0
  else
    echo "RESULTADO: OOM NO OBSERVADO (exit=$EXIT_CODE, oom_kill=${OOM_KILLS:-ausente}, OOMKilled=$OOM_FLAG)"
    PASS=1
  fi
}

docker rm -f "$CONTAINER" >/dev/null 2>&1

echo
echo "Evidencia archivada en:"
echo "  $OUT"
exit "$PASS"
