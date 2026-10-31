#!/usr/bin/env bash
# flush_caches.sh — sync + drop_caches del kernel de la VM, con el EFECTO medido (R-21, A5).
#
# Uso:  scripts/flush_caches.sh           (imprime una línea JSON; exit 0 si hizo efecto)
#
# A5: no basta con ejecutar el comando; se mide buff/cache antes y después
# (Buffers + Cached + SReclaimable de /proc/meminfo, como `free`). Si había
# caché que liberar (> MIN_KB) y no bajó, falla.
#
# V7: usa `sudo -n` (no interactivo). Si no hay credenciales en caché, falla al
# instante en vez de quedarse esperando una contraseña y colgar una corrida
# desatendida. Antes de correr: `sudo -v`. El runner las renueva con `sudo -n -v`.
# NO se configura nada permanente en el sistema (sin reglas en /etc/sudoers.d).
#
# Alcance (SPEC A5, L4): limpia el caché de páginas de la VM de WSL2, que comparten
# los contenedores. NO limpia la caché de Windows sobre el .vhdx: el estado de
# partida es repetible, no frío.

set -uo pipefail
MIN_KB=102400   # 100 MiB: por debajo no se exige que baje

buffcache_kb() { awk '/^(Buffers|Cached|SReclaimable):/{s+=$2} END{print s}' /proc/meminfo; }

BEFORE=$(buffcache_kb)
sync
if sudo -n sh -c 'echo 3 > /proc/sys/vm/drop_caches' 2>/dev/null; then
  SUDO=ok
else
  SUDO=fallo
fi
AFTER=$(buffcache_kb)
DELTA=$(( BEFORE - AFTER ))

OK=true; MOTIVO=""
if [[ $SUDO != ok ]]; then
  OK=false; MOTIVO="sudo -n falló: sin credenciales en caché (ejecuta sudo -v antes)"
elif (( BEFORE > MIN_KB && AFTER >= BEFORE )); then
  OK=false; MOTIVO="buff/cache no bajó"
fi
printf '{"buff_cache_antes_kb": %d, "buff_cache_despues_kb": %d, "liberado_kb": %d, "sudo": "%s", "ok": %s, "motivo": "%s"}\n' \
  "$BEFORE" "$AFTER" "$DELTA" "$SUDO" "$OK" "$MOTIVO"
[[ $OK == true ]]
