# postgresql_PROFILE_A_BASELINE_Q1_c50_r2

`status=error` · `disk_spill=true` · 2026-11-03T05:11:35Z · ventanas {'warmup_s': 60, 'measure_s': 300, 'cooldown_s': 60}

## La fila del CSV

| Columna | Valor |
|---|---|
| timestamp_epoch | 1793682785 |
| engine | postgresql |
| profile | PROFILE_A_BASELINE |
| query_id | Q1 |
| concurrency | 50 |
| run_number | 2 |
| throughput_qps | 0.000000 |
| latency_p50_ms |  |
| latency_p95_ms |  |
| latency_p99_ms |  |
| cpu_throttled_seconds | 232.036 |
| max_rss_mb | 1791.266 |
| disk_spill | true |
| status | error |

## Por qué salió así

- 0 muestra(s) completada(s) en la ventana; se necesitan al menos 2 para un percentil (A4)
- 50 consulta(s) fallidas o con timeout dentro de la ventana
- datos censurados por la derecha: 100.0% de timeouts a 300 s (≥ 1%); percentiles válidos: ninguno

## Consultas en la ventana (A4)

| Dato | Valor |
|---|---|
| Completadas en la ventana | 0 |
| Timeouts en la ventana | 50 |
| Errores en la ventana | 0 |
| Fracción de timeouts | 1.0 |
| Límite por consulta | 300 s |
| Percentiles válidos | {'p50': False, 'p95': False, 'p99': False} |
| Por tipo, toda la repetición | {'ok': 0, 'timeout': 50, 'error': 0} |
| Workers cortados al final | 50 |
| Baja densidad muestral | sí |

## Volcado a disco (A6)

| Contador | Δ en la ventana |
|---|---|
| temp_bytes | 32 336 896 000 |
| temp_files | 58 |

Son **32.3 GB** en 58 archivos temporales; con 0 consultas completadas, ~32.34 GB por consulta.

## Recursos y entorno

| Dato | Valor |
|---|---|
| Throttling de CPU | 232.0 s |
| `max_rss_mb` (anon) | 1791.3 MiB |
| Muestras de la serie de 1 s | 299 |
| `working_set` máximo (M3, SPEC A11) | 2842.9 MiB |
| `shmem` máximo (F6-A3) | 164.5 MiB |
| Flush de caché | liberó 1249252 kB por la vía `ayudante_v7`, ok=True |
| Telemetría | completa |
| Límites reales del cgroup | {'cpu.max': '400000 100000', 'memory.max': '4294967296', 'memory.swap.max': '0', 'cpuset.cpus.effective': '0-7'} |
| Versión del motor | 18.6 (Debian 18.6-1.pgdg13+2) |

## Ejemplos de error del motor

```
worker 32: timeout: canceling statement due to statement timeout
worker 17: timeout: canceling statement due to statement timeout
worker 37: timeout: canceling statement due to statement timeout
worker 36: timeout: canceling statement due to statement timeout
worker 20: timeout: canceling statement due to statement timeout
```

## Evidencia original

- Crudo completo: `results/raw/postgresql_PROFILE_A_BASELINE_Q1_c50_r2.json`
- Telemetría de la ventana: `results/telemetry/postgresql_PROFILE_A_BASELINE_Q1_c50_r2.json`
- Plan de ejecución (R-31, solo en c=1): `no se captura en esta celda`
- Serie de 1 s del cgroup: dentro del crudo, en `serie_cgroup_1s`

