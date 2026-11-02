# mongodb_PROFILE_C_SEVERE_Q1_c50_r3

`status=error` · `disk_spill=false` · 2026-11-03T04:33:12Z · ventanas {'warmup_s': 60, 'measure_s': 300, 'cooldown_s': 60}

## La fila del CSV

| Columna | Valor |
|---|---|
| timestamp_epoch | 1793680478 |
| engine | mongodb |
| profile | PROFILE_C_SEVERE |
| query_id | Q1 |
| concurrency | 50 |
| run_number | 3 |
| throughput_qps | 0.146667 |
| latency_p50_ms | 282414.811 |
| latency_p95_ms | 298170.263 |
| latency_p99_ms | 298622.147 |
| cpu_throttled_seconds | 2083.861 |
| max_rss_mb | 651.270 |
| disk_spill | false |
| status | error |

## Por qué salió así

- 6 consulta(s) fallidas o con timeout dentro de la ventana
- datos censurados por la derecha: 12.0% de timeouts a 300 s (≥ 1%); percentiles válidos: p50

## Consultas en la ventana (A4)

| Dato | Valor |
|---|---|
| Completadas en la ventana | 44 |
| Timeouts en la ventana | 6 |
| Errores en la ventana | 0 |
| Fracción de timeouts | 0.12 |
| Límite por consulta | 300 s |
| Percentiles válidos | {'p50': True, 'p95': False, 'p99': False} |
| Por tipo, toda la repetición | {'ok': 44, 'timeout': 6, 'error': 0} |
| Workers cortados al final | 50 |
| Baja densidad muestral | no |

## Recursos y entorno

| Dato | Valor |
|---|---|
| Throttling de CPU | 2083.9 s |
| `max_rss_mb` (anon) | 651.3 MiB |
| Muestras de la serie de 1 s | 301 |
| `working_set` máximo (M3, SPEC A11) | 882.9 MiB |
| `shmem` máximo (F6-A3) | 0.0 MiB |
| Flush de caché | liberó 1578752 kB por la vía `ayudante_v7`, ok=True |
| Telemetría | completa |
| Límites reales del cgroup | {'cpu.max': '100000 100000', 'memory.max': '1073741824', 'memory.swap.max': '0', 'cpuset.cpus.effective': '0-7'} |
| Versión del motor | 8.2.12 |

## Ejemplos de error del motor

```
worker 20: timeout: Executor error during aggregate command on namespace: bench.orders :: caused by :: operation exceeded time limit, full error: {'ok': 0.0, 'errmsg': 'Executor error during aggregate command on namespace: bench.orders :: caused by :: operation exceeded time limit', 'code': 50, 'cod
worker 9: timeout: Executor error during aggregate command on namespace: bench.orders :: caused by :: operation exceeded time limit, full error: {'ok': 0.0, 'errmsg': 'Executor error during aggregate command on namespace: bench.orders :: caused by :: operation exceeded time limit', 'code': 50, 'code
worker 21: timeout: Executor error during aggregate command on namespace: bench.orders :: caused by :: operation exceeded time limit, full error: {'ok': 0.0, 'errmsg': 'Executor error during aggregate command on namespace: bench.orders :: caused by :: operation exceeded time limit', 'code': 50, 'cod
worker 42: timeout: Executor error during aggregate command on namespace: bench.orders :: caused by :: operation exceeded time limit, full error: {'ok': 0.0, 'errmsg': 'Executor error during aggregate command on namespace: bench.orders :: caused by :: operation exceeded time limit', 'code': 50, 'cod
worker 29: timeout: Executor error during aggregate command on namespace: bench.orders :: caused by :: operation exceeded time limit, full error: {'ok': 0.0, 'errmsg': 'Executor error during aggregate command on namespace: bench.orders :: caused by :: operation exceeded time limit', 'code': 50, 'cod
```

## Evidencia original

- Crudo completo: `results/raw/mongodb_PROFILE_C_SEVERE_Q1_c50_r3.json`
- Telemetría de la ventana: `results/telemetry/mongodb_PROFILE_C_SEVERE_Q1_c50_r3.json`
- Plan de ejecución (R-31, solo en c=1): `no se captura en esta celda`
- Serie de 1 s del cgroup: dentro del crudo, en `serie_cgroup_1s`

