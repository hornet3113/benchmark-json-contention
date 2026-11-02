# Logs de spill y OOM (R-32, F8-c)

Un archivo por repetición con `status` `error` u `oom`, **o** con `disk_spill=true`.
Cada uno correlaciona su fila del CSV con los motivos, la censura (A4), los contadores
del cgroup, los contadores de volcado, el estado del contenedor y la telemetría, y
apunta a la evidencia original.

**Generado por `scripts/build_logs_f8c.py` a partir de `measurements.csv` y de
`results/raw/`: no es una fuente de datos y se puede regenerar.**

Repeticiones afectadas: **30** de 108 filas del CSV.

| Repetición | status | spill | Completadas | Temporales | Δ `oom_kill` |
|---|---|---|---|---|---|
| [postgresql_PROFILE_A_BASELINE_Q1_c1_r1](postgresql_PROFILE_A_BASELINE_Q1_c1_r1.md) | `spill` | true | 40 | 32.3 GB | 0 |
| [postgresql_PROFILE_A_BASELINE_Q1_c1_r2](postgresql_PROFILE_A_BASELINE_Q1_c1_r2.md) | `spill` | true | 39 | 31.5 GB | 0 |
| [postgresql_PROFILE_A_BASELINE_Q1_c1_r3](postgresql_PROFILE_A_BASELINE_Q1_c1_r3.md) | `spill` | true | 40 | 32.3 GB | 0 |
| [postgresql_PROFILE_B_MEDIUM_Q1_c1_r1](postgresql_PROFILE_B_MEDIUM_Q1_c1_r1.md) | `spill` | true | 33 | 27.5 GB | 0 |
| [postgresql_PROFILE_B_MEDIUM_Q1_c1_r2](postgresql_PROFILE_B_MEDIUM_Q1_c1_r2.md) | `spill` | true | 33 | 26.7 GB | 0 |
| [postgresql_PROFILE_B_MEDIUM_Q1_c1_r3](postgresql_PROFILE_B_MEDIUM_Q1_c1_r3.md) | `spill` | true | 33 | 26.7 GB | 0 |
| [postgresql_PROFILE_C_SEVERE_Q1_c1_r1](postgresql_PROFILE_C_SEVERE_Q1_c1_r1.md) | `spill` | true | 17 | 13.7 GB | 0 |
| [postgresql_PROFILE_C_SEVERE_Q1_c1_r2](postgresql_PROFILE_C_SEVERE_Q1_c1_r2.md) | `spill` | true | 17 | 13.7 GB | 0 |
| [postgresql_PROFILE_C_SEVERE_Q1_c1_r3](postgresql_PROFILE_C_SEVERE_Q1_c1_r3.md) | `spill` | true | 17 | 13.7 GB | 0 |
| [postgresql_PROFILE_A_BASELINE_Q1_c10_r1](postgresql_PROFILE_A_BASELINE_Q1_c10_r1.md) | `spill` | true | 44 | 35.6 GB | 0 |
| [postgresql_PROFILE_A_BASELINE_Q1_c10_r2](postgresql_PROFILE_A_BASELINE_Q1_c10_r2.md) | `spill` | true | 48 | 37.9 GB | 0 |
| [postgresql_PROFILE_A_BASELINE_Q1_c10_r3](postgresql_PROFILE_A_BASELINE_Q1_c10_r3.md) | `spill` | true | 38 | 30.7 GB | 0 |
| [postgresql_PROFILE_B_MEDIUM_Q1_c10_r1](postgresql_PROFILE_B_MEDIUM_Q1_c10_r1.md) | `spill` | true | 30 | 24.2 GB | 0 |
| [postgresql_PROFILE_B_MEDIUM_Q1_c10_r2](postgresql_PROFILE_B_MEDIUM_Q1_c10_r2.md) | `spill` | true | 30 | 24.2 GB | 0 |
| [postgresql_PROFILE_B_MEDIUM_Q1_c10_r3](postgresql_PROFILE_B_MEDIUM_Q1_c10_r3.md) | `spill` | true | 30 | 24.2 GB | 0 |
| [postgresql_PROFILE_C_SEVERE_Q1_c10_r1](postgresql_PROFILE_C_SEVERE_Q1_c10_r1.md) | `spill` | true | 10 | 8.1 GB | 0 |
| [postgresql_PROFILE_C_SEVERE_Q1_c10_r2](postgresql_PROFILE_C_SEVERE_Q1_c10_r2.md) | `spill` | true | 10 | 8.1 GB | 0 |
| [postgresql_PROFILE_C_SEVERE_Q1_c10_r3](postgresql_PROFILE_C_SEVERE_Q1_c10_r3.md) | `spill` | true | 10 | 8.1 GB | 0 |
| [mongodb_PROFILE_C_SEVERE_Q1_c50_r1](mongodb_PROFILE_C_SEVERE_Q1_c50_r1.md) | `error` | false | 40 | — | 0 |
| [mongodb_PROFILE_C_SEVERE_Q1_c50_r2](mongodb_PROFILE_C_SEVERE_Q1_c50_r2.md) | `error` | false | 38 | — | 0 |
| [mongodb_PROFILE_C_SEVERE_Q1_c50_r3](mongodb_PROFILE_C_SEVERE_Q1_c50_r3.md) | `error` | false | 44 | — | 0 |
| [postgresql_PROFILE_A_BASELINE_Q1_c50_r1](postgresql_PROFILE_A_BASELINE_Q1_c50_r1.md) | `error` | true | 0 | 35.3 GB | 0 |
| [postgresql_PROFILE_A_BASELINE_Q1_c50_r2](postgresql_PROFILE_A_BASELINE_Q1_c50_r2.md) | `error` | true | 0 | 32.3 GB | 0 |
| [postgresql_PROFILE_A_BASELINE_Q1_c50_r3](postgresql_PROFILE_A_BASELINE_Q1_c50_r3.md) | `error` | true | 2 | 34.4 GB | 0 |
| [postgresql_PROFILE_B_MEDIUM_Q1_c50_r1](postgresql_PROFILE_B_MEDIUM_Q1_c50_r1.md) | `oom` | true | 4 | 21.1 GB | 0 |
| [postgresql_PROFILE_B_MEDIUM_Q1_c50_r2](postgresql_PROFILE_B_MEDIUM_Q1_c50_r2.md) | `oom` | true | 4 | 20.7 GB | 0 |
| [postgresql_PROFILE_B_MEDIUM_Q1_c50_r3](postgresql_PROFILE_B_MEDIUM_Q1_c50_r3.md) | `error` | true | 4 | 20.5 GB | 0 |
| [postgresql_PROFILE_C_SEVERE_Q1_c50_r1](postgresql_PROFILE_C_SEVERE_Q1_c50_r1.md) | `oom` | false | 0 | — | 0 |
| [postgresql_PROFILE_C_SEVERE_Q1_c50_r2](postgresql_PROFILE_C_SEVERE_Q1_c50_r2.md) | `oom` | false | 0 | — | 1 |
| [postgresql_PROFILE_C_SEVERE_Q1_c50_r3](postgresql_PROFILE_C_SEVERE_Q1_c50_r3.md) | `oom` | false | 0 | — | 6 |
