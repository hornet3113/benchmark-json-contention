# postgresql_PROFILE_A_BASELINE_Q1_c1_r2

`status=spill` · `disk_spill=true` · 2026-11-02T18:54:48Z · ventanas {'warmup_s': 60, 'measure_s': 300, 'cooldown_s': 60}

## La fila del CSV

| Columna | Valor |
|---|---|
| timestamp_epoch | 1793645763 |
| engine | postgresql |
| profile | PROFILE_A_BASELINE |
| query_id | Q1 |
| concurrency | 1 |
| run_number | 2 |
| throughput_qps | 0.130000 |
| latency_p50_ms | 7489.679 |
| latency_p95_ms | 8343.535 |
| latency_p99_ms | 9521.762 |
| cpu_throttled_seconds | 0.357 |
| max_rss_mb | 104.020 |
| disk_spill | true |
| status | spill |

## Por qué salió así

- (sin motivos registrados)

## Consultas en la ventana (A4)

| Dato | Valor |
|---|---|
| Completadas en la ventana | 39 |
| Timeouts en la ventana | 0 |
| Errores en la ventana | 0 |
| Fracción de timeouts | 0.0 |
| Límite por consulta | 300 s |
| Percentiles válidos | {'p50': True, 'p95': True, 'p99': True} |
| Por tipo, toda la repetición | {'ok': 55, 'timeout': 0, 'error': 0} |
| Workers cortados al final | 0 |
| Baja densidad muestral | no |

## Volcado a disco (A6)

| Contador | Δ en la ventana |
|---|---|
| temp_bytes | 31 517 163 520 |
| temp_files | 585 |

Son **31.5 GB** en 585 archivos temporales; con 39 consultas completadas, ~0.81 GB por consulta.

## Recursos y entorno

| Dato | Valor |
|---|---|
| Throttling de CPU | 0.4 s |
| `max_rss_mb` (anon) | 104.0 MiB |
| Muestras de la serie de 1 s | 298 |
| `working_set` máximo (M3, SPEC A11) | 1627.1 MiB |
| `shmem` máximo (F6-A3) | 121.4 MiB |
| Flush de caché | liberó 1016392 kB por la vía `ayudante_v7`, ok=True |
| Telemetría | completa |
| Límites reales del cgroup | {'cpu.max': '400000 100000', 'memory.max': '4294967296', 'memory.swap.max': '0', 'cpuset.cpus.effective': '0-7'} |
| Versión del motor | 18.6 (Debian 18.6-1.pgdg13+2) |

## Evidencia original

- Crudo completo: `results/raw/postgresql_PROFILE_A_BASELINE_Q1_c1_r2.json`
- Telemetría de la ventana: `results/telemetry/postgresql_PROFILE_A_BASELINE_Q1_c1_r2.json`
- Plan de ejecución (R-31, solo en c=1): `no se captura en esta celda`
- Serie de 1 s del cgroup: dentro del crudo, en `serie_cgroup_1s`

