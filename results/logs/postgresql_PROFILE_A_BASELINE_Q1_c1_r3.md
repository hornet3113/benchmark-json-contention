# postgresql_PROFILE_A_BASELINE_Q1_c1_r3

`status=spill` · `disk_spill=true` · 2026-11-02T19:02:04Z · ventanas {'warmup_s': 60, 'measure_s': 300, 'cooldown_s': 60}

## La fila del CSV

| Columna | Valor |
|---|---|
| timestamp_epoch | 1793646199 |
| engine | postgresql |
| profile | PROFILE_A_BASELINE |
| query_id | Q1 |
| concurrency | 1 |
| run_number | 3 |
| throughput_qps | 0.133333 |
| latency_p50_ms | 7415.458 |
| latency_p95_ms | 8644.232 |
| latency_p99_ms | 9290.853 |
| cpu_throttled_seconds | 0.333 |
| max_rss_mb | 102.484 |
| disk_spill | true |
| status | spill |

## Por qué salió así

- (sin motivos registrados)

## Consultas en la ventana (A4)

| Dato | Valor |
|---|---|
| Completadas en la ventana | 40 |
| Timeouts en la ventana | 0 |
| Errores en la ventana | 0 |
| Fracción de timeouts | 0.0 |
| Límite por consulta | 300 s |
| Percentiles válidos | {'p50': True, 'p95': True, 'p99': True} |
| Por tipo, toda la repetición | {'ok': 56, 'timeout': 0, 'error': 0} |
| Workers cortados al final | 0 |
| Baja densidad muestral | no |

## Volcado a disco (A6)

| Contador | Δ en la ventana |
|---|---|
| temp_bytes | 32 325 599 232 |
| temp_files | 600 |

Son **32.3 GB** en 600 archivos temporales; con 40 consultas completadas, ~0.81 GB por consulta.

## Recursos y entorno

| Dato | Valor |
|---|---|
| Throttling de CPU | 0.3 s |
| `max_rss_mb` (anon) | 102.5 MiB |
| Muestras de la serie de 1 s | 300 |
| `working_set` máximo (M3, SPEC A11) | 1636.9 MiB |
| `shmem` máximo (F6-A3) | 123.6 MiB |
| Flush de caché | liberó 1154164 kB por la vía `ayudante_v7`, ok=True |
| Telemetría | completa |
| Límites reales del cgroup | {'cpu.max': '400000 100000', 'memory.max': '4294967296', 'memory.swap.max': '0', 'cpuset.cpus.effective': '0-7'} |
| Versión del motor | 18.6 (Debian 18.6-1.pgdg13+2) |

## Evidencia original

- Crudo completo: `results/raw/postgresql_PROFILE_A_BASELINE_Q1_c1_r3.json`
- Telemetría de la ventana: `results/telemetry/postgresql_PROFILE_A_BASELINE_Q1_c1_r3.json`
- Plan de ejecución (R-31, solo en c=1): `no se captura en esta celda`
- Serie de 1 s del cgroup: dentro del crudo, en `serie_cgroup_1s`

