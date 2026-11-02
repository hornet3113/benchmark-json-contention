# postgresql_PROFILE_B_MEDIUM_Q1_c50_r2

`status=oom` · `disk_spill=true` · 2026-11-03T05:57:25Z · ventanas {'warmup_s': 60, 'measure_s': 300, 'cooldown_s': 60}

## La fila del CSV

| Columna | Valor |
|---|---|
| timestamp_epoch | 1793685521 |
| engine | postgresql |
| profile | PROFILE_B_MEDIUM |
| query_id | Q1 |
| concurrency | 50 |
| run_number | 2 |
| throughput_qps | 0.013333 |
| latency_p50_ms | 225384.192 |
| latency_p95_ms | 271569.485 |
| latency_p99_ms | 278084.866 |
| cpu_throttled_seconds | 582.005 |
| max_rss_mb | 1791.723 |
| disk_spill | true |
| status | oom |

## Por qué salió así

- baja densidad muestral: 4 completadas en la ventana (A4)
- 46 consulta(s) fallidas o con timeout dentro de la ventana
- datos censurados por la derecha: 92.0% de timeouts a 300 s (≥ 1%); percentiles válidos: ninguno
- 50 consulta(s) con error (no timeout) en toda la repetición
- OOM: oom_kill +0, OOMKilled=True
- DATASET DAÑADO tras el OOM: None filas en vez de 500000 (OperationalError: connection failed: connection to server at "127.0.0.1", port 5432 failed: FATAL:  the database system is in recovery mode)

## Consultas en la ventana (A4)

| Dato | Valor |
|---|---|
| Completadas en la ventana | 4 |
| Timeouts en la ventana | 46 |
| Errores en la ventana | 0 |
| Fracción de timeouts | 0.92 |
| Límite por consulta | 300 s |
| Percentiles válidos | {'p50': False, 'p95': False, 'p99': False} |
| Por tipo, toda la repetición | {'ok': 4, 'timeout': 46, 'error': 50} |
| Workers cortados al final | 0 |
| Baja densidad muestral | sí |

## OOM

| Dato | Valor |
|---|---|
| `oom_kill` del cgroup (inicio → fin) | 0 → 0 |
| `oom` del cgroup (inicio → fin) | 0 → 0 |
| `OOMKilled` de Docker | True |
| ¿El contenedor seguía corriendo? | True |
| Recuento del dataset tras el OOM (R-08) | None de 500000 filas en 0.55 s, NO INTACTO |
| `max_rss_mb` (anon) | 1791.7 MiB |

`OOMKilled=true` con `Running=true` significa que el kernel mató **algún** proceso del cgroup del motor, no necesariamente el motor entero (F6.3).

**El OOM ocurrió ANTES de la ventana de medición**, no dentro: el contador `oom_kill` del cgroup no se movió durante la ventana (0 → 0). Como el contenedor se recrea en cada repetición, la marca `OOMKilled` de Docker es de esta misma repetición: el motor se quedó sin memoria durante el calentamiento.

## Volcado a disco (A6)

| Contador | Δ en la ventana |
|---|---|
| temp_bytes | 20 692 918 272 |
| temp_files | 105 |

Son **20.7 GB** en 105 archivos temporales; con 4 consultas completadas, ~5.17 GB por consulta.

## Recursos y entorno

| Dato | Valor |
|---|---|
| Throttling de CPU | 582.0 s |
| `max_rss_mb` (anon) | 1791.7 MiB |
| Muestras de la serie de 1 s | 299 |
| `working_set` máximo (M3, SPEC A11) | 2038.3 MiB |
| `shmem` máximo (F6-A3) | 165.5 MiB |
| Flush de caché | liberó 354236 kB por la vía `ayudante_v7`, ok=True |
| Telemetría | completa |
| Límites reales del cgroup | {'cpu.max': '200000 100000', 'memory.max': '2147483648', 'memory.swap.max': '0', 'cpuset.cpus.effective': '0-7'} |
| Versión del motor | 18.6 (Debian 18.6-1.pgdg13+2) |

## Ejemplos de error del motor

```
worker 36: timeout: canceling statement due to statement timeout
worker 16: timeout: canceling statement due to statement timeout
worker 20: timeout: canceling statement due to statement timeout
worker 24: timeout: canceling statement due to statement timeout
worker 28: timeout: canceling statement due to statement timeout
```

## Evidencia original

- Crudo completo: `results/raw/postgresql_PROFILE_B_MEDIUM_Q1_c50_r2.json`
- Telemetría de la ventana: `results/telemetry/postgresql_PROFILE_B_MEDIUM_Q1_c50_r2.json`
- Plan de ejecución (R-31, solo en c=1): `no se captura en esta celda`
- Serie de 1 s del cgroup: dentro del crudo, en `serie_cgroup_1s`

