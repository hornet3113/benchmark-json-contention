# postgresql_PROFILE_B_MEDIUM_Q1_c50_r3

`status=error` · `disk_spill=true` · 2026-11-03T08:24:59Z · ventanas {'warmup_s': 60, 'measure_s': 300, 'cooldown_s': 60}

## La fila del CSV

| Columna | Valor |
|---|---|
| timestamp_epoch | 1793694389 |
| engine | postgresql |
| profile | PROFILE_B_MEDIUM |
| query_id | Q1 |
| concurrency | 50 |
| run_number | 3 |
| throughput_qps | 0.013333 |
| latency_p50_ms | 219361.985 |
| latency_p95_ms | 283268.265 |
| latency_p99_ms | 292150.314 |
| cpu_throttled_seconds | 1536.634 |
| max_rss_mb | 1802.176 |
| disk_spill | true |
| status | error |

## Por qué salió así

- baja densidad muestral: 4 completadas en la ventana (A4)
- 46 consulta(s) fallidas o con timeout dentro de la ventana
- datos censurados por la derecha: 92.0% de timeouts a 300 s (≥ 1%); percentiles válidos: ninguno

## Consultas en la ventana (A4)

| Dato | Valor |
|---|---|
| Completadas en la ventana | 4 |
| Timeouts en la ventana | 46 |
| Errores en la ventana | 0 |
| Fracción de timeouts | 0.92 |
| Límite por consulta | 300 s |
| Percentiles válidos | {'p50': False, 'p95': False, 'p99': False} |
| Por tipo, toda la repetición | {'ok': 4, 'timeout': 46, 'error': 0} |
| Workers cortados al final | 50 |
| Baja densidad muestral | sí |

## Volcado a disco (A6)

| Contador | Δ en la ventana |
|---|---|
| temp_bytes | 20 472 700 928 |
| temp_files | 105 |

Son **20.5 GB** en 105 archivos temporales; con 4 consultas completadas, ~5.12 GB por consulta.

## Recursos y entorno

| Dato | Valor |
|---|---|
| Throttling de CPU | 1536.6 s |
| `max_rss_mb` (anon) | 1802.2 MiB |
| Muestras de la serie de 1 s | 299 |
| `working_set` máximo (M3, SPEC A11) | 2038.8 MiB |
| `shmem` máximo (F6-A3) | 165.4 MiB |
| Flush de caché | liberó 3046388 kB por la vía `ayudante_v7`, ok=True |
| Telemetría | completa |
| Límites reales del cgroup | {'cpu.max': '200000 100000', 'memory.max': '2147483648', 'memory.swap.max': '0', 'cpuset.cpus.effective': '0-7'} |
| Versión del motor | 18.6 (Debian 18.6-1.pgdg13+2) |

## Ejemplos de error del motor

```
worker 35: timeout: canceling statement due to statement timeout
worker 39: timeout: canceling statement due to statement timeout
worker 0: timeout: canceling statement due to statement timeout
worker 27: timeout: canceling statement due to statement timeout
worker 6: timeout: canceling statement due to statement timeout
```

## Evidencia original

- Crudo completo: `results/raw/postgresql_PROFILE_B_MEDIUM_Q1_c50_r3.json`
- Telemetría de la ventana: `results/telemetry/postgresql_PROFILE_B_MEDIUM_Q1_c50_r3.json`
- Plan de ejecución (R-31, solo en c=1): `no se captura en esta celda`
- Serie de 1 s del cgroup: dentro del crudo, en `serie_cgroup_1s`

