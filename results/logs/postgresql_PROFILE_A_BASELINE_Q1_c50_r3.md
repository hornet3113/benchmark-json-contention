# postgresql_PROFILE_A_BASELINE_Q1_c50_r3

`status=error` · `disk_spill=true` · 2026-11-03T05:19:22Z · ventanas {'warmup_s': 60, 'measure_s': 300, 'cooldown_s': 60}

## La fila del CSV

| Columna | Valor |
|---|---|
| timestamp_epoch | 1793683248 |
| engine | postgresql |
| profile | PROFILE_A_BASELINE |
| query_id | Q1 |
| concurrency | 50 |
| run_number | 3 |
| throughput_qps | 0.006667 |
| latency_p50_ms | 275775.851 |
| latency_p95_ms | 283669.771 |
| latency_p99_ms | 284371.453 |
| cpu_throttled_seconds | 443.136 |
| max_rss_mb | 1791.461 |
| disk_spill | true |
| status | error |

## Por qué salió así

- baja densidad muestral: 2 completadas en la ventana (A4)
- 48 consulta(s) fallidas o con timeout dentro de la ventana
- datos censurados por la derecha: 96.0% de timeouts a 300 s (≥ 1%); percentiles válidos: ninguno

## Consultas en la ventana (A4)

| Dato | Valor |
|---|---|
| Completadas en la ventana | 2 |
| Timeouts en la ventana | 48 |
| Errores en la ventana | 0 |
| Fracción de timeouts | 0.96 |
| Límite por consulta | 300 s |
| Percentiles válidos | {'p50': False, 'p95': False, 'p99': False} |
| Por tipo, toda la repetición | {'ok': 2, 'timeout': 48, 'error': 0} |
| Workers cortados al final | 50 |
| Baja densidad muestral | sí |

## Volcado a disco (A6)

| Contador | Δ en la ventana |
|---|---|
| temp_bytes | 34 378 350 592 |
| temp_files | 97 |

Son **34.4 GB** en 97 archivos temporales; con 2 consultas completadas, ~17.19 GB por consulta.

## Recursos y entorno

| Dato | Valor |
|---|---|
| Throttling de CPU | 443.1 s |
| `max_rss_mb` (anon) | 1791.5 MiB |
| Muestras de la serie de 1 s | 300 |
| `working_set` máximo (M3, SPEC A11) | 2797.3 MiB |
| `shmem` máximo (F6-A3) | 165.5 MiB |
| Flush de caché | liberó 1722024 kB por la vía `ayudante_v7`, ok=True |
| Telemetría | con_huecos |
| Límites reales del cgroup | {'cpu.max': '400000 100000', 'memory.max': '4294967296', 'memory.swap.max': '0', 'cpuset.cpus.effective': '0-7'} |
| Versión del motor | 18.6 (Debian 18.6-1.pgdg13+2) |

## Ejemplos de error del motor

```
worker 20: timeout: canceling statement due to statement timeout
worker 42: timeout: canceling statement due to statement timeout
worker 25: timeout: canceling statement due to statement timeout
worker 16: timeout: canceling statement due to statement timeout
worker 8: timeout: canceling statement due to statement timeout
```

## Evidencia original

- Crudo completo: `results/raw/postgresql_PROFILE_A_BASELINE_Q1_c50_r3.json`
- Telemetría de la ventana: `results/telemetry/postgresql_PROFILE_A_BASELINE_Q1_c50_r3.json`
- Plan de ejecución (R-31, solo en c=1): `no se captura en esta celda`
- Serie de 1 s del cgroup: dentro del crudo, en `serie_cgroup_1s`

