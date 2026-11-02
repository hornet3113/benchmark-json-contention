# postgresql_PROFILE_B_MEDIUM_Q1_c10_r2

`status=spill` · `disk_spill=true` · 2026-11-03T00:21:03Z · ventanas {'warmup_s': 60, 'measure_s': 300, 'cooldown_s': 60}

## La fila del CSV

| Columna | Valor |
|---|---|
| timestamp_epoch | 1793665339 |
| engine | postgresql |
| profile | PROFILE_B_MEDIUM |
| query_id | Q1 |
| concurrency | 10 |
| run_number | 2 |
| throughput_qps | 0.100000 |
| latency_p50_ms | 113287.745 |
| latency_p95_ms | 119146.737 |
| latency_p99_ms | 119574.689 |
| cpu_throttled_seconds | 1558.830 |
| max_rss_mb | 570.324 |
| disk_spill | true |
| status | spill |

## Por qué salió así

- (sin motivos registrados)

## Consultas en la ventana (A4)

| Dato | Valor |
|---|---|
| Completadas en la ventana | 30 |
| Timeouts en la ventana | 0 |
| Errores en la ventana | 0 |
| Fracción de timeouts | 0.0 |
| Límite por consulta | 300 s |
| Percentiles válidos | {'p50': True, 'p95': True, 'p99': True} |
| Por tipo, toda la repetición | {'ok': 30, 'timeout': 0, 'error': 0} |
| Workers cortados al final | 10 |
| Baja densidad muestral | no |

## Volcado a disco (A6)

| Contador | Δ en la ventana |
|---|---|
| temp_bytes | 24 242 233 344 |
| temp_files | 411 |

Son **24.2 GB** en 411 archivos temporales; con 30 consultas completadas, ~0.81 GB por consulta.

## Recursos y entorno

| Dato | Valor |
|---|---|
| Throttling de CPU | 1558.8 s |
| `max_rss_mb` (anon) | 570.3 MiB |
| Muestras de la serie de 1 s | 300 |
| `working_set` máximo (M3, SPEC A11) | 1435.0 MiB |
| `shmem` máximo (F6-A3) | 156.3 MiB |
| Flush de caché | liberó 407948 kB por la vía `ayudante_v7`, ok=True |
| Telemetría | completa |
| Límites reales del cgroup | {'cpu.max': '200000 100000', 'memory.max': '2147483648', 'memory.swap.max': '0', 'cpuset.cpus.effective': '0-7'} |
| Versión del motor | 18.6 (Debian 18.6-1.pgdg13+2) |

## Evidencia original

- Crudo completo: `results/raw/postgresql_PROFILE_B_MEDIUM_Q1_c10_r2.json`
- Telemetría de la ventana: `results/telemetry/postgresql_PROFILE_B_MEDIUM_Q1_c10_r2.json`
- Plan de ejecución (R-31, solo en c=1): `no se captura en esta celda`
- Serie de 1 s del cgroup: dentro del crudo, en `serie_cgroup_1s`

