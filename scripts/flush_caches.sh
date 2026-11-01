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
# desatendida. Dos caminos, y el script elige solo:
#   - si está instalado /usr/local/sbin/bench-drop-caches (regla de V7 aprobada el
#     2026-11-02, docs/V7_SUDOERS.md), lo llama: no hace falta contraseña ni `sudo -v`;
#   - si no está, hace el flush como siempre, y entonces sí hay que ejecutar `sudo -v`
#     antes (el runner las renueva con `sudo -n -v`).
# Así el repo corre igual en una máquina sin la regla: el docente no tiene que instalar nada.
#
# Alcance (SPEC A5, L4): limpia el caché de páginas de la VM de WSL2, que comparten
# los contenedores. NO limpia la caché de Windows sobre el .vhdx: el estado de
# partida es repetible, no frío.

set -uo pipefail
MIN_KB=102400   # 100 MiB: por debajo no se exige que baje

buffcache_kb() { awk '/^(Buffers|Cached|SReclaimable):/{s+=$2} END{print s}' /proc/meminfo; }

BEFORE=$(buffcache_kb)
sync
HELPER=/usr/local/sbin/bench-drop-caches
if [[ -x $HELPER ]] && sudo -n -l "$HELPER" >/dev/null 2>&1; then
  VIA=ayudante_v7
  sudo -n "$HELPER" 2>/dev/null && SUDO=ok || SUDO=fallo
else
  VIA=sudo_v
  sudo -n sh -c 'echo 3 > /proc/sys/vm/drop_caches' 2>/dev/null && SUDO=ok || SUDO=fallo
fi
AFTER=$(buffcache_kb)
DELTA=$(( BEFORE - AFTER ))

OK=true; MOTIVO=""
if [[ $SUDO != ok ]]; then
  OK=false; MOTIVO="sudo -n falló por la vía $VIA (si es sudo_v, ejecuta sudo -v antes)"
elif (( BEFORE > MIN_KB && AFTER >= BEFORE )); then
  OK=false; MOTIVO="buff/cache no bajó"
fi
printf '{"buff_cache_antes_kb": %d, "buff_cache_despues_kb": %d, "liberado_kb": %d, "sudo": "%s", "via": "%s", "ok": %s, "motivo": "%s"}\n' \
  "$BEFORE" "$AFTER" "$DELTA" "$SUDO" "$VIA" "$OK" "$MOTIVO"
[[ $OK == true ]]
