#!/usr/bin/env python3
"""extract_queries.py — copia Q1 y Q2 del manual a queries/, sin reescribirlas a mano.

Uso:  python3 scripts/extract_queries.py [--check]

Lee docs/manual/playbook.pdf con `pdftotext -layout` (poppler-utils), recorta los
cuatro bloques de §5.1 y §5.2 por sus encabezados ("MongoDB (pipeline)." y
"PostgreSQL.") y los escribe en:

    queries/mongo/q1_unwind_group.json     queries/postgres/q1_unwind_group.sql
    queries/mongo/q2_sort_topk.json        queries/postgres/q2_sort_topk.sql

Por qué un script: CLAUDE.md exige que las queries se copien LITERALMENTE del
manual, y un error al teclear (un espacio en '2026-01-01 00:00:00Z', por
ejemplo) dejaría de ser copia literal. Así el revisor puede repetir la
extracción y comparar.

Lo único que se quita es lo que el PDF mete en medio y no es query: líneas en
blanco, el número de página y el encabezado de la página siguiente (el
pipeline de Q2 en Mongo cruza un salto de página). Los espacios al final de
cada línea se recortan. Nada más se toca.

--check no escribe: compara lo extraído con los archivos existentes y sale con
1 si difieren.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PDF = ROOT / "docs" / "manual" / "playbook.pdf"
TARGETS = (
    ("5.1.", "mongo", ROOT / "queries" / "mongo" / "q1_unwind_group.json"),
    ("5.1.", "postgres", ROOT / "queries" / "postgres" / "q1_unwind_group.sql"),
    ("5.2.", "mongo", ROOT / "queries" / "mongo" / "q2_sort_topk.json"),
    ("5.2.", "postgres", ROOT / "queries" / "postgres" / "q2_sort_topk.sql"),
)
# Ruido de salto de página en la salida de pdftotext: número de página suelto
# y la cabecera "IT2iD … Bases de Datos en la Nube" (precedida de \f).
_PAGE_NOISE = re.compile(r"^\s*\d+\s*$|IT2iD\s+Bases de Datos en la Nube")


def pdf_text() -> list[str]:
    out = subprocess.run(["pdftotext", "-layout", str(PDF), "-"], capture_output=True, text=True, check=True)
    return out.stdout.splitlines()


def section(lines: list[str], start: str, end: str) -> list[str]:
    """Líneas desde el encabezado `start` (excluido) hasta la primera que empiece por `end`."""
    i = next(n for n, l in enumerate(lines) if l.strip().startswith(start))
    j = next(n for n in range(i + 1, len(lines)) if lines[n].strip().startswith(end))
    return lines[i + 1:j]


def block(sec: list[str], engine: str) -> str:
    """Bloque de un motor dentro de una sección, sin ruido de página."""
    heads = [n for n, l in enumerate(sec) if l.strip() in ("MongoDB (pipeline).", "PostgreSQL.")]
    mongo_at = next(n for n in heads if sec[n].strip() == "MongoDB (pipeline).")
    pg_at = next(n for n in heads if sec[n].strip() == "PostgreSQL.")
    body = sec[mongo_at + 1:pg_at] if engine == "mongo" else sec[pg_at + 1:]
    kept = [l.rstrip() for l in body if l.strip() and not _PAGE_NOISE.search(l)]
    return "\n".join(kept) + "\n"


def extract() -> dict[Path, str]:
    lines = pdf_text()
    sections = {"5.1.": section(lines, "5.1.", "5.2."), "5.2.": section(lines, "5.2.", "6.")}
    return {path: block(sections[sec], engine) for sec, engine, path in TARGETS}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="comparar con queries/ sin escribir")
    args = parser.parse_args(argv)

    blocks = extract()
    differ = 0
    for path, text in blocks.items():
        if path.suffix == ".json":
            json.loads(text)  # un pipeline que no es JSON válido es un error de extracción
        rel = path.relative_to(ROOT)
        if args.check:
            same = path.exists() and path.read_text() == text
            differ += not same
            print(f"{'IGUAL ' if same else 'DIFIERE'} {rel}")
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
            print(f"escrito {rel} ({len(text.splitlines())} líneas)")
    return 1 if differ else 0


if __name__ == "__main__":
    sys.exit(main())
