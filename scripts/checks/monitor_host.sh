#!/usr/bin/env bash
# monitor_host.sh — muestrea cada N s lo que el runner NO registra, para la prueba de carga máxima (F5.5).
#
# Uso:  scripts/checks/monitor_host.sh <archivo.csv> [intervalo_s=5]   (se detiene con kill)
#
# Columnas:
#   utc, mem_disp_mb, swap_usado_mb  → memoria de la VM (L3: holgura limitada con PROFILE_A)
#   runner_procesos, runner_rss_mb   → el proceso del runner y TODOS sus descendientes (workers)
#   pg_tmp_mb                        → archivos temporales de Postgres (base/pgsql_tmp), vía docker exec
#
# ES UNA SONDA, no una medición del benchmark: el `docker exec du` corre dentro
# del contenedor y consume algo de su CPU. Sus datos no van al CSV.

set -uo pipefail
OUT="${1:?uso: $0 <archivo.csv> [intervalo_s]}"
EVERY="${2:-5}"
PGTMP=/var/lib/postgresql/data/pgdata/base/pgsql_tmp
echo "utc,mem_disp_mb,swap_usado_mb,runner_procesos,runner_rss_mb,pg_tmp_mb" > "$OUT"
while true; do
  read -r DISP SWAP < <(free -m | awk '/^Mem:/{d=$7} /^Swap:/{s=$3} END{print d, s}')
  # Árbol de procesos del runner: el principal (benchmark_runner.cli) y sus descendientes.
  read -r NPROC RSS < <(ps -eo pid=,ppid=,rss=,args= | python3 -c '
import sys
# Runner = proceso cuyos ARGUMENTOS EXACTOS (/proc/<pid>/cmdline) incluyen
# "-m" seguido de "benchmark_runner.cli". Buscar el texto en la línea de
# comandos contaría también a cualquier shell que lo mencione (o a este monitor).
def is_runner(pid):
    try:
        argv = open(f"/proc/{pid}/cmdline", "rb").read().split(b"\0")
    except OSError:
        return False
    return any(a == b"-m" and b == b"benchmark_runner.cli" for a, b in zip(argv, argv[1:]))
rows = [l.split(None, 3) for l in sys.stdin if l.strip()]
kids, rss, roots = {}, {}, []
for pid, ppid, r, *args in rows:
    kids.setdefault(ppid, []).append(pid); rss[pid] = int(r)
    if is_runner(pid): roots.append(pid)
seen, stack = set(), list(roots)
while stack:
    p = stack.pop()
    if p not in seen:
        seen.add(p); stack.extend(kids.get(p, []))
print(len(seen), sum(rss[p] for p in seen) // 1024)')
  if docker ps --format '{{.Names}}' | grep -qx bench_postgres; then
    TMP=$(docker exec bench_postgres sh -c "du -sm $PGTMP 2>/dev/null | cut -f1" 2>/dev/null); TMP=${TMP:-0}
  else
    TMP=""
  fi
  echo "$(date -u +%H:%M:%S),$DISP,$SWAP,$NPROC,$RSS,$TMP" >> "$OUT"
  sleep "$EVERY"
done
