#!/usr/bin/env bash
# sudo_listo.sh — ¿se podrá limpiar la caché sin pedir contraseña? (V7)
#
# No se ejecuta solo: los scripts lo cargan con `source`.
#
# Hay DOS vías válidas, y por eso existe esta función en vez de un `sudo -n true`
# suelto (que fue justo el fallo: con la regla de V7 instalada, `sudo -n true`
# sigue fallando, porque el NOPASSWD cubre solo el ayudante, y los scripts
# pedían `sudo -v` sin necesidad):
#   1. la regla de V7 (docs/V7_SUDOERS.md): `/usr/local/sbin/bench-drop-caches`
#      permitido sin contraseña. No hay nada que renovar;
#   2. credenciales en caché (`sudo -v`), que caducan a los ~15 min.
#
# `sudo -n -l <ruta>` pregunta si está permitido; NO ejecuta el ayudante.
# Misma lógica que benchmark_runner/lifecycle.py:sudo_ready().

V7_HELPER=/usr/local/sbin/bench-drop-caches

sudo_via() {
  if [[ -x $V7_HELPER ]] && sudo -n -l "$V7_HELPER" >/dev/null 2>&1; then
    echo ayudante_v7
  elif sudo -n true 2>/dev/null; then
    echo sudo_v
  else
    echo ninguna
  fi
}

# Uso:  sudo_listo || exit 2
sudo_listo() {
  local via
  via="$(sudo_via)"
  if [[ $via == ninguna ]]; then
    echo "ERROR: la limpieza de caché necesita sudo y no hay forma de hacerlo sin contraseña (V7)." >&2
    echo "  Opción a) ejecuta 'sudo -v' en ESTA terminal y vuelve a lanzar (caduca a los ~15 min)." >&2
    echo "  Opción b) instala la regla: sudo scripts/v7_install_sudoers.sh  (docs/V7_SUDOERS.md)." >&2
    return 1
  fi
  echo "== sudo para el flush: vía $via"
  return 0
}
