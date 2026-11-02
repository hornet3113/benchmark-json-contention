#!/usr/bin/env bash
# monitor_cpu_clock.sh — ¿baja la frecuencia del procesador durante una corrida? (F8)
#
# Uso:  scripts/checks/monitor_cpu_clock.sh <archivo.csv> [intervalo_s=15]   (se detiene con kill)
#
# Por qué existe: en el bloque 2 de F8, la celda Postgres × A × Q2_MEM_LOW (la única
# que satura las 4 CPUs) perdió un 19 % de throughput de r1 a r3 **gastando el mismo
# tiempo de CPU** (1 142 s en las tres). Mismo CPU y menos trabajo apunta a que el
# reloj baja. Desde WSL2 no se puede ver: no hay `cpufreq` y /proc/cpuinfo informa
# siempre la nominal (2295.613 MHz).
#
# QUÉ SE MIDE, y por qué no es lo primero que se intentó: `Win32_Processor.
# CurrentClockSpeed` (WMI) está **clavado** en esta máquina — 2010 MHz en las 1008
# muestras del bloque 3, 4 h de carga incluidas. El indicador que sí varía es el
# contador de rendimiento **"% de rendimiento del procesador"** (en inglés,
# "% Processor Performance"): el porcentaje de la frecuencia nominal al que va de
# verdad el procesador. Con 2295.613 MHz nominales, 80 % ≈ 1 836 MHz.
#
# ES UNA SONDA del entorno, no una medición del benchmark: no produce filas del CSV.
# Un solo proceso de PowerShell con el bucle dentro, y el nombre del contador se
# busca por expresión regular porque está traducido ("Información del procesador").
# Se envía con -EncodedCommand: evita el entrecomillado y la política de ejecución
# de scripts, que en esta máquina está deshabilitada (no se toca).
#
# Columnas: utc, rendimiento_pct, mhz_estimado, mhz_wmi, carga_pct

set -uo pipefail
OUT="${1:?uso: $0 <archivo.csv> [intervalo_s]}"
EVERY="${2:-15}"
NOMINAL=2295.613        # /proc/cpuinfo del Ryzen 5 PRO 5675U de esta máquina
echo "utc,rendimiento_pct,mhz_estimado,mhz_wmi,carga_pct" > "$OUT"

read -r -d '' PS_CODE <<'PS'
$ProgressPreference = 'SilentlyContinue'
$set = Get-Counter -ListSet * -ErrorAction SilentlyContinue |
       Where-Object { ($_.CounterSetName -match 'procesador' -and $_.CounterSetName -match 'formaci') -or
                      $_.CounterSetName -eq 'Processor Information' }
$perf = $null
if ($set) {
  $perf = $set.Counter |
          Where-Object { $_ -match 'rendimiento del procesador' -or $_ -match '% Processor Performance' } |
          ForEach-Object { $_ -replace '\(\*\)', '(_Total)' } | Select-Object -First 1
}
while ($true) {
  $t = (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
  $pct = ''
  if ($perf) {
    $c = Get-Counter -Counter $perf -ErrorAction SilentlyContinue
    if ($c) { $pct = [math]::Round($c.CounterSamples[0].CookedValue, 1) }
  }
  $w = Get-CimInstance Win32_Processor
  $mhz = ''
  if ($pct -ne '') { $mhz = [math]::Round(__NOMINAL__ * $pct / 100) }
  Write-Output ($t + ',' + $pct + ',' + $mhz + ',' + $w.CurrentClockSpeed + ',' + $w.LoadPercentage)
  Start-Sleep -Seconds __EVERY__
}
PS
PS_CODE="${PS_CODE//__NOMINAL__/$NOMINAL}"
PS_CODE="${PS_CODE//__EVERY__/$EVERY}"
ENC="$(printf '%s' "$PS_CODE" | iconv -f UTF-8 -t UTF-16LE | base64 -w0)"

# El bucle vive dentro de PowerShell, así que un `kill` a este script no lo mata:
# hay que terminarlo a mano o quedaría muestreando para siempre (comprobado).
limpiar() { [[ -n "${PS_PID:-}" ]] && kill "$PS_PID" 2>/dev/null; }
trap limpiar EXIT INT TERM

powershell.exe -NoProfile -NonInteractive -EncodedCommand "$ENC" 2>/dev/null \
  | tr -d '\r' | grep -E '^[0-9]{4}-' >> "$OUT" &
PS_PID=$!
wait "$PS_PID"
