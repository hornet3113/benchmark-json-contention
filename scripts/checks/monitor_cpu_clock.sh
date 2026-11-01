#!/usr/bin/env bash
# monitor_cpu_clock.sh — frecuencia real del procesador durante una corrida (F8).
#
# Uso:  scripts/checks/monitor_cpu_clock.sh <archivo.csv> [intervalo_s=15]   (se detiene con kill)
#
# Por qué existe: en el bloque 2 de F8, la celda Postgres × A × Q2_MEM_LOW (la única
# que satura las 4 CPUs) perdió un 19 % de throughput de r1 a r3 **gastando el mismo
# tiempo de CPU** (1 142 s en las tres). El mismo tiempo de CPU haciendo menos trabajo
# apunta a que el reloj bajó. Desde WSL2 no se puede comprobar: no hay `cpufreq` y
# /proc/cpuinfo informa siempre la frecuencia nominal (2295.613 MHz). Windows sí lo sabe.
#
# ES UNA SONDA del entorno, no una medición del benchmark: no produce filas del CSV.
# Un solo proceso de PowerShell con un bucle dentro (no uno por muestra), para no
# cargar el host con arranques de proceso cada pocos segundos.
#
# Columnas: utc, mhz_actual, mhz_max, carga_pct  (de Win32_Processor)

set -uo pipefail
OUT="${1:?uso: $0 <archivo.csv> [intervalo_s]}"
EVERY="${2:-15}"
echo "utc,mhz_actual,mhz_max,carga_pct" > "$OUT"

# El bucle vive dentro de PowerShell, así que un `kill` a este script no lo mata:
# hay que terminarlo a mano o quedaría muestreando para siempre (comprobado).
limpiar() { [[ -n "${PS_PID:-}" ]] && kill "$PS_PID" 2>/dev/null; }
trap limpiar EXIT INT TERM

powershell.exe -NoProfile -Command "
  while (\$true) {
    \$p = Get-CimInstance Win32_Processor
    \$t = (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
    Write-Output (\$t + ',' + \$p.CurrentClockSpeed + ',' + \$p.MaxClockSpeed + ',' + \$p.LoadPercentage)
    Start-Sleep -Seconds $EVERY
  }" 2>/dev/null | tr -d '\r' >> "$OUT" &
PS_PID=$!
wait "$PS_PID"
