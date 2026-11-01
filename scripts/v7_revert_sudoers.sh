#!/usr/bin/env bash
# v7_revert_sudoers.sh — deshace lo que instaló v7_install_sudoers.sh (V7).
#
# Uso, EN TU TERMINAL:  sudo scripts/v7_revert_sudoers.sh
#
# Borra los dos archivos que se añadieron y olvida las credenciales en caché.
# No modifica nada preexistente: /etc/sudoers no se toca en ningún momento.

set -euo pipefail
[[ $EUID -eq 0 ]] || { echo "ERROR: ejecútalo con sudo: sudo $0" >&2; exit 2; }

rm -fv /etc/sudoers.d/bench-drop-caches /usr/local/sbin/bench-drop-caches
sudo -k || true
echo "== Comprobación:"
if sudo -l 2>/dev/null | grep -q bench-drop-caches; then
  echo "   AVISO: la regla sigue apareciendo en sudo -l" >&2; exit 1
fi
echo "   revertido: ya no hay regla ni ayudante."
echo "   scripts/flush_caches.sh vuelve solo a la ruta de siempre (sudo -v antes de cada sesión)."
