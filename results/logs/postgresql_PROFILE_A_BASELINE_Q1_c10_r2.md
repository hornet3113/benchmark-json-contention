# postgresql_PROFILE_A_BASELINE_Q1_c10_r2

`status=spill` · `disk_spill=true` · 2026-11-02T23:36:09Z · ventanas {'warmup_s': 60, 'measure_s': 300, 'cooldown_s': 60}

## La fila del CSV

| Columna | Valor |
|---|---|
| timestamp_epoch | 1793662653 |
| engine | postgresql |
| profile | PROFILE_A_BASELINE |
| query_id | Q1 |
| concurrency | 10 |
| run_number | 2 |
| throughput_qps | 0.160000 |
| latency_p50_ms | 67635.856 |
| latency_p95_ms | 85461.304 |
| latency_p99_ms | 86514.269 |
| cpu_throttled_seconds | 889.540 |
| max_rss_mb | 569.043 |
| disk_spill | true |
| status | spill |

## Por qué salió así

- (sin motivos registrados)

## Consultas en la ventana (A4)

| Dato | Valor |
|---|---|
| Completadas en la ventana | 48 |
| Timeouts en la ventana | 0 |
| Errores en la ventana | 0 |
| Fracción de timeouts | 0.0 |
| Límite por consulta | 300 s |
| Percentiles válidos | {'p50': True, 'p95': True, 'p99': True} |
| Por tipo, toda la repetición | {'ok': 58, 'timeout': 0, 'error': 0} |
| Workers cortados al final | 10 |
| Baja densidad muestral | no |

## Volcado a disco (A6)

| Contador | Δ en la ventana |
|---|---|
| temp_bytes | 37 873 123 328 |
| temp_files | 662 |

Son **37.9 GB** en 662 archivos temporales; con 48 consultas completadas, ~0.79 GB por consulta.

## Recursos y entorno

| Dato | Valor |
|---|---|
| Throttling de CPU | 889.5 s |
| `max_rss_mb` (anon) | 569.0 MiB |
| Muestras de la serie de 1 s | 300 |
| `working_set` máximo (M3, SPEC A11) | 2207.6 MiB |
| `shmem` máximo (F6-A3) | 156.4 MiB |
| Flush de caché | liberó 900184 kB por la vía `ayudante_v7`, ok=True |
| Telemetría | con_huecos |
| Límites reales del cgroup | {'cpu.max': '400000 100000', 'memory.max': '4294967296', 'memory.swap.max': '0', 'cpuset.cpus.effective': '0-7'} |
| Versión del motor | 18.6 (Debian 18.6-1.pgdg13+2) |

## Evidencia original

- Crudo completo: `results/raw/postgresql_PROFILE_A_BASELINE_Q1_c10_r2.json`
- Telemetría de la ventana: `results/telemetry/postgresql_PROFILE_A_BASELINE_Q1_c10_r2.json`
- Plan de ejecución (R-31, solo en c=1): `no se captura en esta celda`
- Serie de 1 s del cgroup: dentro del crudo, en `serie_cgroup_1s`

