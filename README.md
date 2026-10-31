# Benchmark MongoDB vs PostgreSQL JSONB bajo contención

Medición de latencia, rendimiento y huella de recursos en agregaciones JSON
anidadas con límites estrictos de CPU y memoria (Docker, cgroups v2).

Materia: Bases de Datos en la Nube · IT2iD · Universidad Politécnica de Chiapas · 2026

## Estado del proyecto

| Fase | Estado |
|---|---|
| F0 — Validación del entorno | Cerrada con reservas (ver PLAN.md) |
| F1 — Infraestructura Docker | **Cerrada** (2026-11-01): límites verificados en 3 perfiles × 2 motores, evidencia en `results/env/f1/` |
| F2 — Generador de dataset | No iniciada |
| F3 — Carga escalonada | No iniciada |
| F4–F9 | No iniciadas |

## Si abres esto en Claude Code (VS Code)

`CLAUDE.md` se carga solo al inicio de cada sesión y lleva las reglas de
trabajo, el estado de las fases y las decisiones ya tomadas. Empieza pidiendo
a Claude que lea `CLAUDE.md`, `SPEC.md` y `PLAN.md` antes de proponer nada.

El manual del proyecto está en `docs/manual/`, así que Claude puede consultarlo
sin que tengas que adjuntarlo.

## Documentos

- `CLAUDE.md` — instrucciones del proyecto y estado actual (lo lee Claude Code)
- `SPEC.md` — requisitos del manual con referencia a archivo y página, arquitectura, ambigüedades y decisiones
- `PLAN.md` — fases, dependencias, criterios de aceptación, riesgos
- `CHECKLIST.md` — verificación de entrega
- `docs/F1_INFRAESTRUCTURA.md` — cómo ejecutar y verificar F1

## Entorno

Este proyecto se desarrolla sobre Windows 11 + WSL2 (Ubuntu) + Docker Desktop.
Los scripts se ejecutan desde la distribución `Ubuntu`.

**El repositorio debe vivir dentro del sistema de archivos de WSL2** (por
ejemplo `~/benchmark-json-contention`), nunca bajo `/mnt/c/`: esa ruta pasa por
una capa de traducción y degradaría las mediciones de I/O.

Los valores absolutos que produzca este experimento **dependen del hardware y
de la capa de virtualización**. Otro equipo, sobre Linux nativo, obtendrá
números distintos. Lo reproducible es el procedimiento, el esquema del CSV y
qué celdas resultan marcadas, no las cifras.

Las limitaciones del entorno virtualizado están documentadas en `SPEC.md` §6
(L1–L7) y se declaran en la sección 1 del reporte.

## Arranque rápido (F1)

```bash
cd ~/benchmark-json-contention
chmod +x scripts/*.sh
(set -a; source docker/images.env; docker pull "$MONGO_IMAGE" && docker pull "$PG_IMAGE")   # imágenes fijadas por digest
scripts/up_profile.sh a_baseline mongo
scripts/verify_limits.sh a_baseline mongo
scripts/down_profile.sh
```

Ver `docs/F1_INFRAESTRUCTURA.md` para el detalle y los criterios de aceptación.
