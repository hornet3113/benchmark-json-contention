# mongodb_PROFILE_C_SEVERE_Q1_c50_r1

`status=error` · `disk_spill=false` · 2026-11-03T04:17:50Z · ventanas {'warmup_s': 60, 'measure_s': 300, 'cooldown_s': 60}

## La fila del CSV

| Columna | Valor |
|---|---|
| timestamp_epoch | 1793679556 |
| engine | mongodb |
| profile | PROFILE_C_SEVERE |
| query_id | Q1 |
| concurrency | 50 |
| run_number | 1 |
| throughput_qps | 0.133333 |
| latency_p50_ms | 285805.476 |
| latency_p95_ms | 297152.704 |
| latency_p99_ms | 299632.124 |
| cpu_throttled_seconds | 2085.448 |
| max_rss_mb | 630.492 |
| disk_spill | false |
| status | error |

## Por qué salió así

- 10 consulta(s) fallidas o con timeout dentro de la ventana
- datos censurados por la derecha: 20.0% de timeouts a 300 s (≥ 1%); percentiles válidos: p50

## Consultas en la ventana (A4)

| Dato | Valor |
|---|---|
| Completadas en la ventana | 40 |
| Timeouts en la ventana | 10 |
| Errores en la ventana | 0 |
| Fracción de timeouts | 0.2 |
| Límite por consulta | 300 s |
| Percentiles válidos | {'p50': True, 'p95': False, 'p99': False} |
| Por tipo, toda la repetición | {'ok': 40, 'timeout': 10, 'error': 0} |
| Workers cortados al final | 50 |
| Baja densidad muestral | no |

## Recursos y entorno

| Dato | Valor |
|---|---|
| Throttling de CPU | 2085.4 s |
| `max_rss_mb` (anon) | 630.5 MiB |
| Muestras de la serie de 1 s | 299 |
| `working_set` máximo (M3, SPEC A11) | 868.3 MiB |
| `shmem` máximo (F6-A3) | 0.0 MiB |
| Flush de caché | liberó 1772148 kB por la vía `ayudante_v7`, ok=True |
| Telemetría | con_huecos |
| Límites reales del cgroup | {'cpu.max': '100000 100000', 'memory.max': '1073741824', 'memory.swap.max': '0', 'cpuset.cpus.effective': '0-7'} |
| Versión del motor | 8.2.12 |

## Ejemplos de error del motor

```
worker 12: timeout: Executor error during aggregate command on namespace: bench.orders :: caused by :: operation exceeded time limit, full error: {'ok': 0.0, 'errmsg': 'Executor error during aggregate command on namespace: bench.orders :: caused by :: operation exceeded time limit', 'code': 50, 'cod
worker 42: timeout: Executor error during aggregate command on namespace: bench.orders :: caused by :: operation exceeded time limit, full error: {'ok': 0.0, 'errmsg': 'Executor error during aggregate command on namespace: bench.orders :: caused by :: operation exceeded time limit', 'code': 50, 'cod
worker 38: timeout: Executor error during aggregate command on namespace: bench.orders :: caused by :: operation exceeded time limit, full error: {'ok': 0.0, 'errmsg': 'Executor error during aggregate command on namespace: bench.orders :: caused by :: operation exceeded time limit', 'code': 50, 'cod
worker 37: timeout: Executor error during aggregate command on namespace: bench.orders :: caused by :: operation exceeded time limit, full error: {'ok': 0.0, 'errmsg': 'Executor error during aggregate command on namespace: bench.orders :: caused by :: operation exceeded time limit', 'code': 50, 'cod
worker 5: timeout: Executor error during aggregate command on namespace: bench.orders :: caused by :: operation exceeded time limit, full error: {'ok': 0.0, 'errmsg': 'Executor error during aggregate command on namespace: bench.orders :: caused by :: operation exceeded time limit', 'code': 50, 'code
```

## Evidencia original

- Crudo completo: `results/raw/mongodb_PROFILE_C_SEVERE_Q1_c50_r1.json`
- Telemetría de la ventana: `results/telemetry/mongodb_PROFILE_C_SEVERE_Q1_c50_r1.json`
- Plan de ejecución (R-31, solo en c=1): `no se captura en esta celda`
- Serie de 1 s del cgroup: dentro del crudo, en `serie_cgroup_1s`

