#!/usr/bin/env bash
# v7_install_sudoers.sh — instala el ayudante del flush y su regla de sudoers (V7).
#
# Uso, EN TU TERMINAL:  sudo scripts/v7_install_sudoers.sh
# Revertir:             sudo scripts/v7_revert_sudoers.sh
#
# Diseño aprobado por Alix el 2026-11-02; está explicado en docs/V7_SUDOERS.md.
# Lo que hace, y nada más:
#   /usr/local/sbin/bench-drop-caches   root:root 0755  (sync + drop_caches, sin parámetros)
#   /etc/sudoers.d/bench-drop-caches    root:root 0440  (NOPASSWD solo para ese ejecutable)
#
# El ayudante vive FUERA del repositorio a propósito: si estuviera en el repo, que
# tu usuario puede editar, la regla equivaldría a darte root sin contraseña.

set -euo pipefail
[[ $EUID -eq 0 ]] || { echo "ERROR: ejecútalo con sudo: sudo $0" >&2; exit 2; }

USUARIO="${SUDO_USER:?no se sabe para qué usuario instalar (ejecútalo con sudo, no como root directo)}"
HELPER=/usr/local/sbin/bench-drop-caches
RULE=/etc/sudoers.d/bench-drop-caches

cat > "$HELPER" <<'HELPEREOF'
#!/bin/sh
# bench-drop-caches — sync + drop_caches. Instalado para el proyecto
# benchmark-json-contention (V7, SPEC A5). No acepta parámetros.
# Revertir:  sudo rm /etc/sudoers.d/bench-drop-caches /usr/local/sbin/bench-drop-caches
[ $# -eq 0 ] || { echo "bench-drop-caches no acepta parámetros" >&2; exit 2; }
sync
echo 3 > /proc/sys/vm/drop_caches
HELPEREOF
chown root:root "$HELPER"
chmod 0755 "$HELPER"

# La regla se escribe en un temporal y se VALIDA antes de ponerla en su sitio: un
# archivo de sudoers con un error de sintaxis puede dejarte sin sudo.
TMP="$(mktemp)"
printf '%s ALL=(root) NOPASSWD: %s\n' "$USUARIO" "$HELPER" > "$TMP"
if ! visudo -cqf "$TMP"; then
  rm -f "$TMP"
  echo "ERROR: la regla no pasó la validación de visudo; no se instaló nada." >&2
  exit 1
fi
install -o root -g root -m 0440 "$TMP" "$RULE"
rm -f "$TMP"

echo "== Instalado:"
stat -c '   %U:%G %a %n' "$HELPER" "$RULE"
echo "== Comprobaciones (como $USUARIO):"
sudo -u "$USUARIO" sudo -n "$HELPER" && echo "   flush sin contraseña: OK"
sudo -u "$USUARIO" sudo -n "$HELPER" x >/dev/null 2>&1 \
  && echo "   AVISO: aceptó un parámetro (no debería)" || echo "   con parámetro: rechazado, OK"
sudo -u "$USUARIO" sudo -n true >/dev/null 2>&1 \
  && echo "   AVISO: el resto de sudo NO pide contraseña (revisa otras reglas)" \
  || echo "   el resto de sudo sigue pidiendo contraseña: OK"
echo
echo "Para revertir:  sudo scripts/v7_revert_sudoers.sh"
