#!/usr/bin/env bash
# run_gate.sh — compuertas G2 y G3 de F3: carga + equivalencia de Q1/Q2 (F4).
#
# Uso:  scripts/run_gate.sh g2|g3
#
# Generaliza run_g1.sh, que NO se modifica: es el script que produjo la
# evidencia de G1. G3 habilitada por Alix el 2026-11-01.
#
# Orden (solo un motor arriba a la vez, CLAUDE.md):
#   1. Mongo    : levantar → arranque de herramientas → cargar → verificar carga → queries
#   2. Postgres : levantar (baja Mongo) → lo mismo
#   3. bajar → comparar en tres direcciones → equivalencia Q1/Q2
#   4. g2: extrapolación del tiempo de carga a 500 000 · g3: medido frente a lo
#      estimado en G2, y espacio libre (PLAN G3)
#
# DESTRUCTIVO para los datos de los motores (recrea colección y tabla).
# Salida: results/f3/<gate>/ y results/explains/<gate>/. Se detiene en el primer fallo.

set -uo pipefail
GATE="${1:-}"
case "$GATE" in
  g2) SIZE=10000 ;;
  g3) SIZE=500000 ;;
  *) echo "uso: $0 g2|g3" >&2; exit 2 ;;
esac

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="$ROOT/results/f3/$GATE"
mkdir -p "$OUT"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
exec > >(tee "$OUT/run_${STAMP}.txt") 2>&1

step() {  # step <descripción> <comando...>
  local what="$1"; shift
  echo; echo "### $what"; echo "\$ ${*#"$ROOT/"}"
  "$@"; local rc=$?
  if [[ $rc -ne 0 ]]; then
    echo "!!! FALLÓ ($rc): $what — $GATE se detiene aquí"
    "$ROOT/scripts/down_profile.sh" >/dev/null 2>&1
    exit 1
  fi
}

echo "== $GATE — $STAMP — $SIZE registros — python $(python3 --version | cut -d' ' -f2) · $(uname -r)"
step "0. Queries de queries/ iguales a las extraídas del PDF" python3 "$ROOT/scripts/extract_queries.py" --check

for ENGINE in mongo postgres; do
  N=1; [[ $ENGINE == postgres ]] && N=2
  step "$N.a Levantar $ENGINE (PROFILE_A)"          "$ROOT/scripts/up_profile.sh" a_baseline "$ENGINE"
  step "$N.b Arranque de herramientas ($ENGINE)"    "$ROOT/scripts/checks/tool_overhead.sh" "$GATE" "$ENGINE"
  step "$N.c Cargar $SIZE en $ENGINE"               "$ROOT/scripts/load_dataset.sh" "$SIZE" "$ENGINE"
  step "$N.d Exportar y verificar carga ($ENGINE)"  python3 "$ROOT/scripts/verify_gate.py" export --gate "$GATE" --engine "$ENGINE"
  step "$N.e Q1 y Q2 con variantes ($ENGINE)"       python3 "$ROOT/scripts/check_equivalence.py" run --gate "$GATE" --engine "$ENGINE"
done

step "3.a Bajar motores"                           "$ROOT/scripts/down_profile.sh"
step "3.b Comparar documentos en tres direcciones" python3 "$ROOT/scripts/verify_gate.py" compare --gate "$GATE"
step "3.c Equivalencia de Q1 y Q2 (F4)"            python3 "$ROOT/scripts/check_equivalence.py" compare --gate "$GATE"

if [[ "$GATE" == g2 ]]; then
echo; echo "### 3.d Extrapolación del tiempo de carga a 500 000 (estimación, no medición)"
python3 - "$OUT" "$SIZE" <<'PY'
import json, math, sys
out, size = sys.argv[1], int(sys.argv[2])
factor = 500_000 / size
# Invocaciones de herramienta en cada paso de load_dataset.sh
calls = {"mongo": {"carga": ("mongoimport", 1), "indices": ("mongosh", 1)},
         "postgres": {"carga": ("psql", 3), "indices": ("psql", 1), "analyze": ("psql", 1)}}
res = {"tamano_medido": size, "factor": factor, "supuestos": [
    "carga y analyze: lineales en el número de documentos",
    "índices: n·log n (B-Tree); factor = 50 · log(500000)/log(10000)",
    "se resta el arranque fijo de cada herramienta, medido en overhead_<motor>.json"]}
nlogn = factor * math.log(500_000) / math.log(size)
for engine, steps in calls.items():
    load = json.load(open(f"{out}/load_{engine}.json"))["segundos"]
    over = json.load(open(f"{out}/overhead_{engine}.json"))["mediana_s"]
    e = {}
    for step, (tool, n) in steps.items():
        fixed = n * over[tool]
        net = max(0.0, load[step] - fixed)
        f = nlogn if step == "indices" else factor
        e[step] = {"medido_s": load[step], "arranque_s": round(fixed, 3), "neto_s": round(net, 3),
                   "estimado_500k_s": round(net * f + fixed, 1)}
    e["total_estimado_500k_s"] = round(sum(v["estimado_500k_s"] for v in e.values()), 1)
    res[engine] = e
    print(f"   {engine}: " + "  ".join(f"{k}: medido {v['medido_s']}s, arranque {v['arranque_s']}s → ~{v['estimado_500k_s']}s"
                                    for k, v in e.items() if isinstance(v, dict))
          + f"  | total ~{e['total_estimado_500k_s']}s")
json.dump(res, open(f"{out}/load_extrapolation.json", "w"), indent=2)
print(f"   -> results/f3/{out.rsplit('/', 1)[-1]}/load_extrapolation.json")
PY
else
echo; echo "### 3.d Tiempo de carga medido a 500 000 frente a lo estimado en G2"
python3 - "$OUT" "$ROOT/results/f3/g2/load_extrapolation.json" <<'PY'
import json, sys
out, est = sys.argv[1], json.load(open(sys.argv[2]))
res = {}
for engine in ("mongo", "postgres"):
    measured = json.load(open(f"{out}/load_{engine}.json"))["segundos"]
    rows = {}
    for step, v in measured.items():
        e = est[engine].get(step, {}).get("estimado_500k_s")
        if e:
            rows[step] = {"medido_s": v, "estimado_g2_s": e, "medido_entre_estimado": round(v / e, 2)}
    total = round(sum(r["medido_s"] for r in rows.values()), 1)
    rows["total"] = {"medido_s": total, "estimado_g2_s": est[engine]["total_estimado_500k_s"],
                     "medido_entre_estimado": round(total / est[engine]["total_estimado_500k_s"], 2)}
    res[engine] = rows
    print(f"   {engine}: " + "  ".join(f"{k}: {r['medido_s']}s (estimado {r['estimado_g2_s']}s, x{r['medido_entre_estimado']})"
                                    for k, r in rows.items()))
json.dump(res, open(f"{out}/load_vs_estimate.json", "w"), indent=2)
print("   -> results/f3/g3/load_vs_estimate.json")
PY

echo; echo "### 3.e Espacio libre (PLAN G3; estimación del proyecto en SPEC §6, V4: ~25 GB)"
{ echo '$ df -h /'; df -h /; echo; echo '$ docker system df'; docker system df; } | tee "$OUT/espacio_libre.txt"
fi

echo; echo "== $GATE terminó: todos los pasos con exit 0. Evidencia en ${OUT#"$ROOT/"}/ y results/explains/$GATE/"
