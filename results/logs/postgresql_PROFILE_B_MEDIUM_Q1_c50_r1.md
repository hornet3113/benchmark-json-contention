# postgresql_PROFILE_B_MEDIUM_Q1_c50_r1

`status=oom` · `disk_spill=true` · 2026-11-03T05:50:04Z · ventanas {'warmup_s': 60, 'measure_s': 300, 'cooldown_s': 60}

## La fila del CSV

| Columna | Valor |
|---|---|
| timestamp_epoch | 1793685084 |
| engine | postgresql |
| profile | PROFILE_B_MEDIUM |
| query_id | Q1 |
| concurrency | 50 |
| run_number | 1 |
| throughput_qps | 0.013333 |
| latency_p50_ms | 179392.337 |
| latency_p95_ms | 233865.987 |
| latency_p99_ms | 241555.427 |
| cpu_throttled_seconds | 1529.231 |
| max_rss_mb | 1806.062 |
| disk_spill | true |
| status | oom |

## Por qué salió así

- baja densidad muestral: 4 completadas en la ventana (A4)
- 46 consulta(s) fallidas o con timeout dentro de la ventana
- datos censurados por la derecha: 92.0% de timeouts a 300 s (≥ 1%); percentiles válidos: ninguno
- 602 consulta(s) con error (no timeout) en toda la repetición
- OOM: oom_kill +0, OOMKilled=True

## Consultas en la ventana (A4)

| Dato | Valor |
|---|---|
| Completadas en la ventana | 4 |
| Timeouts en la ventana | 46 |
| Errores en la ventana | 0 |
| Fracción de timeouts | 0.92 |
| Límite por consulta | 300 s |
| Percentiles válidos | {'p50': False, 'p95': False, 'p99': False} |
| Por tipo, toda la repetición | {'ok': 4, 'timeout': 46, 'error': 602} |
| Workers cortados al final | 0 |
| Baja densidad muestral | sí |

## OOM

| Dato | Valor |
|---|---|
| `oom_kill` del cgroup (inicio → fin) | 0 → 0 |
| `oom` del cgroup (inicio → fin) | 0 → 0 |
| `OOMKilled` de Docker | True |
| ¿El contenedor seguía corriendo? | True |
| Recuento del dataset tras el OOM (R-08) | 500000 de 500000 filas en 1.01 s, intacto |
| `max_rss_mb` (anon) | 1806.1 MiB |

`OOMKilled=true` con `Running=true` significa que el kernel mató **algún** proceso del cgroup del motor, no necesariamente el motor entero (F6.3).

**El OOM ocurrió ANTES de la ventana de medición**, no dentro: el contador `oom_kill` del cgroup no se movió durante la ventana (0 → 0). Como el contenedor se recrea en cada repetición, la marca `OOMKilled` de Docker es de esta misma repetición: el motor se quedó sin memoria durante el calentamiento.

## Volcado a disco (A6)

| Contador | Δ en la ventana |
|---|---|
| temp_bytes | 21 113 864 192 |
| temp_files | 113 |

Son **21.1 GB** en 113 archivos temporales; con 4 consultas completadas, ~5.28 GB por consulta.

## Recursos y entorno

| Dato | Valor |
|---|---|
| Throttling de CPU | 1529.2 s |
| `max_rss_mb` (anon) | 1806.1 MiB |
| Muestras de la serie de 1 s | 323 |
| `working_set` máximo (M3, SPEC A11) | 2046.9 MiB |
| `shmem` máximo (F6-A3) | 172.5 MiB |
| Flush de caché | liberó 1074004 kB por la vía `ayudante_v7`, ok=True |
| Telemetría | completa |
| Límites reales del cgroup | {'cpu.max': '200000 100000', 'memory.max': '2147483648', 'memory.swap.max': '0', 'cpuset.cpus.effective': '0-7'} |
| Versión del motor | 18.6 (Debian 18.6-1.pgdg13+2) |

## Ejemplos de error del motor

```
worker 14: timeout: canceling statement due to statement timeout
worker 22: timeout: canceling statement due to statement timeout
worker 27: timeout: canceling statement due to statement timeout
worker 7: timeout: canceling statement due to statement timeout
worker 28: timeout: canceling statement due to statement timeout
```

## Evidencia original

- Crudo completo: `results/raw/postgresql_PROFILE_B_MEDIUM_Q1_c50_r1.json`
- Telemetría de la ventana: `results/telemetry/postgresql_PROFILE_B_MEDIUM_Q1_c50_r1.json`
- Plan de ejecución (R-31, solo en c=1): `no se captura en esta celda`
- Serie de 1 s del cgroup: dentro del crudo, en `serie_cgroup_1s`

