# postgresql_PROFILE_B_MEDIUM_Q1_c1_r2

`status=spill` · `disk_spill=true` · 2026-11-02T19:38:52Z · ventanas {'warmup_s': 60, 'measure_s': 300, 'cooldown_s': 60}

## La fila del CSV

| Columna | Valor |
|---|---|
| timestamp_epoch | 1793648412 |
| engine | postgresql |
| profile | PROFILE_B_MEDIUM |
| query_id | Q1 |
| concurrency | 1 |
| run_number | 2 |
| throughput_qps | 0.110000 |
| latency_p50_ms | 8922.943 |
| latency_p95_ms | 10810.070 |
| latency_p99_ms | 11661.445 |
| cpu_throttled_seconds | 147.011 |
| max_rss_mb | 106.145 |
| disk_spill | true |
| status | spill |

## Por qué salió así

- (sin motivos registrados)

## Consultas en la ventana (A4)

| Dato | Valor |
|---|---|
| Completadas en la ventana | 33 |
| Timeouts en la ventana | 0 |
| Errores en la ventana | 0 |
| Fracción de timeouts | 0.0 |
| Límite por consulta | 300 s |
| Percentiles válidos | {'p50': True, 'p95': True, 'p99': True} |
| Por tipo, toda la repetición | {'ok': 46, 'timeout': 0, 'error': 0} |
| Workers cortados al final | 0 |
| Baja densidad muestral | no |

## Volcado a disco (A6)

| Contador | Δ en la ventana |
|---|---|
| temp_bytes | 26 668 302 336 |
| temp_files | 495 |

Son **26.7 GB** en 495 archivos temporales; con 33 consultas completadas, ~0.81 GB por consulta.

## Recursos y entorno

| Dato | Valor |
|---|---|
| Throttling de CPU | 147.0 s |
| `max_rss_mb` (anon) | 106.1 MiB |
| Muestras de la serie de 1 s | 300 |
| `working_set` máximo (M3, SPEC A11) | 1622.5 MiB |
| `shmem` máximo (F6-A3) | 103.8 MiB |
| Flush de caché | liberó 2003884 kB por la vía `ayudante_v7`, ok=True |
| Telemetría | con_huecos |
| Límites reales del cgroup | {'cpu.max': '200000 100000', 'memory.max': '2147483648', 'memory.swap.max': '0', 'cpuset.cpus.effective': '0-7'} |
| Versión del motor | 18.6 (Debian 18.6-1.pgdg13+2) |

## Evidencia original

- Crudo completo: `results/raw/postgresql_PROFILE_B_MEDIUM_Q1_c1_r2.json`
- Telemetría de la ventana: `results/telemetry/postgresql_PROFILE_B_MEDIUM_Q1_c1_r2.json`
- Plan de ejecución (R-31, solo en c=1): `no se captura en esta celda`
- Serie de 1 s del cgroup: dentro del crudo, en `serie_cgroup_1s`

