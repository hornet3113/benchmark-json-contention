# postgresql_PROFILE_A_BASELINE_Q1_c1_r1

`status=spill` · `disk_spill=true` · 2026-11-02T18:47:24Z · ventanas {'warmup_s': 60, 'measure_s': 300, 'cooldown_s': 60}

## La fila del CSV

| Columna | Valor |
|---|---|
| timestamp_epoch | 1793645319 |
| engine | postgresql |
| profile | PROFILE_A_BASELINE |
| query_id | Q1 |
| concurrency | 1 |
| run_number | 1 |
| throughput_qps | 0.133333 |
| latency_p50_ms | 7536.995 |
| latency_p95_ms | 7973.912 |
| latency_p99_ms | 8277.344 |
| cpu_throttled_seconds | 0.117 |
| max_rss_mb | 104.836 |
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
| Por tipo, toda la repetición | {'ok': 55, 'timeout': 0, 'error': 0} |
| Workers cortados al final | 0 |
| Baja densidad muestral | no |

## Volcado a disco (A6)

| Contador | Δ en la ventana |
|---|---|
| temp_bytes | 32 325 206 016 |
| temp_files | 600 |

Son **32.3 GB** en 600 archivos temporales; con 40 consultas completadas, ~0.81 GB por consulta.

## Recursos y entorno

| Dato | Valor |
|---|---|
| Throttling de CPU | 0.1 s |
| `max_rss_mb` (anon) | 104.8 MiB |
| Muestras de la serie de 1 s | 300 |
| `working_set` máximo (M3, SPEC A11) | 1629.9 MiB |
| `shmem` máximo (F6-A3) | 121.4 MiB |
| Flush de caché | liberó 774556 kB por la vía `ayudante_v7`, ok=True |
| Telemetría | completa |
| Límites reales del cgroup | {'cpu.max': '400000 100000', 'memory.max': '4294967296', 'memory.swap.max': '0', 'cpuset.cpus.effective': '0-7'} |
| Versión del motor | 18.6 (Debian 18.6-1.pgdg13+2) |

## Evidencia original

- Crudo completo: `results/raw/postgresql_PROFILE_A_BASELINE_Q1_c1_r1.json`
- Telemetría de la ventana: `results/telemetry/postgresql_PROFILE_A_BASELINE_Q1_c1_r1.json`
- Plan de ejecución (R-31, solo en c=1): `/home/alix_anahi/benchmark-json-contention/results/explains/postgresql_PROFILE_A_BASELINE_Q1_c1.json`
- Serie de 1 s del cgroup: dentro del crudo, en `serie_cgroup_1s`

