#!/usr/bin/env python3
"""reetiquetar_q2.py — `Q2_MEM_LOW` → `Q2` al resolverse A2 con 36 celdas (A2, R-26).

Uso:
    .venv/bin/python scripts/reetiquetar_q2.py                 # muestra el plan, NO cambia nada
    .venv/bin/python scripts/reetiquetar_q2.py --confirmo      # lo aplica

Por qué. El docente fijó **36 celdas** (A2), y con 36 el dominio de `query_id`
del manual es `Q1 | Q2`: una sola variante de Q2. La matriz se corrió con la
variante **restrictiva** (`work_mem = 4MB` en Postgres, `allowDiskUse: false` en
Mongo) y se etiquetó `Q2_MEM_LOW` mientras A2 estaba abierta. Los datos valen
igual; lo que cambia es la etiqueta, y `validate_csv.py --matrix 36` rechaza
`Q2_MEM_LOW` por estar fuera de dominio.

**No se edita nada a mano** (CLAUDE.md). Esto hace el cambio completo y auditable:

  1. Copia el CSV a `measurements.csv.bak-<sello>` antes de tocarlo.
  2. Reescribe el CSV cambiando **solo** la columna `query_id`, línea por línea,
     sin reformatear ningún número.
  3. Renombra los crudos, la telemetría y los planes, y dentro de cada crudo
     actualiza `run_id` y `fila_csv.query_id`, añadiendo un bloque
     `reetiquetado` con de/a/motivo/sello: **cada archivo lleva su propio rastro**.
  4. Escribe `results/reetiquetado_<sello>.json` con el mapa completo de nombres.
  5. No toca `opciones` del crudo, que es donde consta que la variante medida fue
     la restrictiva (`work_mem: 4MB` / `allowDiskUse: false`). La etiqueta se
     pierde; la configuración real no.

Después hay que regenerar `results/logs/` (`build_logs_f8c.py`) y validar con
`validate_csv.py results/measurements.csv --matrix 36 --expect-rows 108`.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from benchmark_runner import csv_writer  # noqa: E402

DE, A = "Q2_MEM_LOW", "Q2"
MOTIVO = ("A2 resuelta: el docente fijó 36 celdas, y con 36 el dominio de query_id es Q1|Q2. "
          "La variante medida es la restrictiva (work_mem 4MB / allowDiskUse false), que consta "
          "en 'opciones' de cada crudo.")
SUBDIRS = ("raw", "telemetry", "explains")


def nuevo_nombre(nombre: str) -> str:
    return nombre.replace(DE, A)


def plan(base: Path) -> dict:
    csv_path = base / "measurements.csv"
    if not csv_path.exists():
        sys.exit(f"no existe {csv_path}")
    with csv_path.open(newline="") as f:
        rows = list(csv.DictReader(f))
    filas = [r for r in rows if r["query_id"] == DE]
    choques, archivos = [], {}
    for sub in SUBDIRS:
        d = base / sub
        if not d.exists():
            continue
        archivos[sub] = []
        for p in sorted(d.glob(f"*{DE}*")):
            destino = p.with_name(nuevo_nombre(p.name))
            archivos[sub].append((p, destino))
            if destino.exists():
                choques.append(str(destino.relative_to(ROOT)))
    ya = [r for r in rows if r["query_id"] == A]
    return {"csv": csv_path, "filas_totales": len(rows), "filas_a_cambiar": len(filas),
            "filas_ya_con_la_etiqueta_nueva": len(ya), "archivos": archivos, "choques": choques}


def aplicar(base: Path, p: dict, stamp: str) -> dict:
    csv_path: Path = p["csv"]
    texto = csv_path.read_text()
    lineas = texto.splitlines(keepends=True)
    encabezado, datos = lineas[0], lineas[1:]
    i_qid = csv_writer.COLUMNS.index("query_id")
    salida, cambiadas = [], 0
    for linea in datos:
        if not linea.strip():
            continue
        campos = next(csv.reader(io.StringIO(linea)))
        if campos[i_qid] == DE:
            campos[i_qid] = A
            cambiadas += 1
            buf = io.StringIO()
            csv.writer(buf, lineterminator="").writerow(campos)
            salida.append(buf.getvalue() + ("\r\n" if linea.endswith("\r\n") else "\n"))
        else:
            salida.append(linea)        # las demás, byte a byte
    copia = csv_path.with_suffix(f".csv.bak-{stamp}")
    shutil.copy2(csv_path, copia)
    csv_path.write_text(encabezado + "".join(salida))

    movidos = {}
    for sub, pares in p["archivos"].items():
        movidos[sub] = []
        for origen, destino in pares:
            if sub == "raw":
                d = json.loads(origen.read_text())
                if "run_id" in d:
                    d["run_id"] = nuevo_nombre(d["run_id"])
                if isinstance(d.get("fila_csv"), dict) and d["fila_csv"].get("query_id") == DE:
                    d["fila_csv"]["query_id"] = A
                d["reetiquetado"] = {"de": DE, "a": A, "motivo": MOTIVO, "sello": stamp}
                destino.write_text(json.dumps(d, ensure_ascii=False, default=str) + "\n")
                origen.unlink()
            else:
                shutil.move(str(origen), destino)
            movidos[sub].append([str(origen.relative_to(ROOT)), str(destino.relative_to(ROOT))])

    registro = {"de": DE, "a": A, "motivo": MOTIVO, "sello": stamp,
                "csv": str(csv_path.relative_to(ROOT)), "copia_de_seguridad": str(copia.relative_to(ROOT)),
                "filas_cambiadas": cambiadas, "archivos_renombrados": movidos,
                "siguiente": ["scripts/build_logs_f8c.py",
                              "scripts/validate_csv.py results/measurements.csv --matrix 36 --expect-rows 108"]}
    destino_reg = base / f"reetiquetado_{stamp}.json"
    destino_reg.write_text(json.dumps(registro, ensure_ascii=False, indent=1) + "\n")
    registro["registro"] = str(destino_reg.relative_to(ROOT))
    return registro


def revertir(registro: Path) -> int:
    """Deshace lo que hizo `--confirmo`: el CSV vuelve de su copia y los nombres se invierten.

    Que la operación sea reversible es la condición para aplicarla sobre evidencia ya medida.
    """
    if not registro.exists():
        sys.exit(f"no existe {registro}")
    reg = json.loads(registro.read_text())
    csv_path, copia = ROOT / reg["csv"], ROOT / reg["copia_de_seguridad"]
    if not copia.exists():
        sys.exit(f"falta la copia de seguridad {copia}: no se puede revertir sin ella")
    vueltos = 0
    for sub, pares in reg["archivos_renombrados"].items():
        for origen, destino in pares:
            o, d = ROOT / origen, ROOT / destino
            if not d.exists():
                print(f"   AVISO: no está {destino}; se omite")
                continue
            if sub == "raw":
                doc = json.loads(d.read_text())
                doc.pop("reetiquetado", None)
                if "run_id" in doc:
                    doc["run_id"] = doc["run_id"].replace(A, DE)
                if isinstance(doc.get("fila_csv"), dict) and doc["fila_csv"].get("query_id") == A:
                    doc["fila_csv"]["query_id"] = DE
                o.write_text(json.dumps(doc, ensure_ascii=False, default=str) + "\n")
                d.unlink()
            else:
                shutil.move(str(d), o)
            vueltos += 1
    shutil.copy2(copia, csv_path)
    print(f"== revertido: {vueltos} archivo(s) y el CSV restaurado de {reg['copia_de_seguridad']}")
    print(f"   el registro {registro.name} se conserva como rastro de lo que se hizo y se deshizo.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--salida", default="", metavar="DIR")
    ap.add_argument("--confirmo", action="store_true", help="aplica el cambio; sin esto solo muestra el plan")
    ap.add_argument("--revertir", metavar="REGISTRO.json",
                    help="deshace un reetiquetado: restaura el CSV de su copia y renombra al revés")
    args = ap.parse_args()
    base = ROOT / "results" / args.salida if args.salida else ROOT / "results"

    if args.revertir:
        return revertir(Path(args.revertir))

    p = plan(base)
    print(f"== {p['csv'].relative_to(ROOT)}: {p['filas_totales']} filas")
    print(f"   filas con {DE} → {A}: {p['filas_a_cambiar']}")
    print(f"   filas que ya dicen {A}: {p['filas_ya_con_la_etiqueta_nueva']}")
    for sub, pares in p["archivos"].items():
        print(f"   {sub}/: {len(pares)} archivo(s) a renombrar")
    if p["choques"]:
        sys.exit(f"ABORTADO: el destino ya existe para {len(p['choques'])} archivo(s): {p['choques'][:3]}")
    if not p["filas_a_cambiar"] and not any(p["archivos"].values()):
        print("   nada que hacer: ya está reetiquetado.")
        return 0
    if not args.confirmo:
        print("\n(plan; no se cambió nada. Añade --confirmo para aplicarlo)")
        return 0

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    reg = aplicar(base, p, stamp)
    print(f"\n== aplicado: {reg['filas_cambiadas']} fila(s), "
          f"{sum(len(v) for v in reg['archivos_renombrados'].values())} archivo(s)")
    print(f"   copia de seguridad: {reg['copia_de_seguridad']}")
    print(f"   registro: {reg['registro']}")
    print("   ahora: " + " y ".join(reg["siguiente"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
