# postgresql_PROFILE_C_SEVERE_Q1_c1_r1

`status=spill` · `disk_spill=true` · 2026-11-02T20:15:34Z · ventanas {'warmup_s': 60, 'measure_s': 300, 'cooldown_s': 60}

## La fila del CSV

| Columna | Valor |
|---|---|
| timestamp_epoch | 1793650613 |
| engine | postgresql |
| profile | PROFILE_C_SEVERE |
| query_id | Q1 |
| concurrency | 1 |
| run_number | 1 |
| throughput_qps | 0.056667 |
| latency_p50_ms | 17546.177 |
| latency_p95_ms | 18777.076 |
| latency_p99_ms | 19154.458 |
| cpu_throttled_seconds | 502.393 |
| max_rss_mb | 104.996 |
| disk_spill | true |
| status | spill |

## Por qué salió así

- baja densidad muestral: 17 completadas en la ventana (A4)

## Consultas en la ventana (A4)

| Dato | Valor |
|---|---|
| Completadas en la ventana | 17 |
| Timeouts en la ventana | 0 |
| Errores en la ventana | 0 |
| Fracción de timeouts | 0.0 |
| Límite por consulta | 300 s |
| Percentiles válidos | {'p50': True, 'p95': True, 'p99': True} |
| Por tipo, toda la repetición | {'ok': 24, 'timeout': 0, 'error': 0} |
| Workers cortados al final | 0 |
| Baja densidad muestral | sí |

## Volcado a disco (A6)

| Contador | Δ en la ventana |
|---|---|
| temp_bytes | 13 738 262 528 |
| temp_files | 255 |

Son **13.7 GB** en 255 archivos temporales; con 17 consultas completadas, ~0.81 GB por consulta.

## Recursos y entorno

| Dato | Valor |
|---|---|
| Throttling de CPU | 502.4 s |
| `max_rss_mb` (anon) | 105.0 MiB |
| Muestras de la serie de 1 s | 300 |
| `working_set` máximo (M3, SPEC A11) | 875.6 MiB |
| `shmem` máximo (F6-A3) | 64.1 MiB |
| Flush de caché | liberó 1958096 kB por la vía `ayudante_v7`, ok=True |
| Telemetría | completa |
| Límites reales del cgroup | {'cpu.max': '100000 100000', 'memory.max': '1073741824', 'memory.swap.max': '0', 'cpuset.cpus.effective': '0-7'} |
| Versión del motor | 18.6 (Debian 18.6-1.pgdg13+2) |

## Evidencia original

- Crudo completo: `results/raw/postgresql_PROFILE_C_SEVERE_Q1_c1_r1.json`
- Telemetría de la ventana: `results/telemetry/postgresql_PROFILE_C_SEVERE_Q1_c1_r1.json`
- Plan de ejecución (R-31, solo en c=1): `/home/alix_anahi/benchmark-json-contention/results/explains/postgresql_PROFILE_C_SEVERE_Q1_c1.json`
- Serie de 1 s del cgroup: dentro del crudo, en `serie_cgroup_1s`

