# postgresql_PROFILE_C_SEVERE_Q1_c50_r1

`status=oom` · `disk_spill=false` · 2026-11-03T08:55:25Z · ventanas {'warmup_s': 60, 'measure_s': 300, 'cooldown_s': 60}

## La fila del CSV

| Columna | Valor |
|---|---|
| timestamp_epoch | 1793696200 |
| engine | postgresql |
| profile | PROFILE_C_SEVERE |
| query_id | Q1 |
| concurrency | 50 |
| run_number | 1 |
| throughput_qps | 0.000000 |
| latency_p50_ms |  |
| latency_p95_ms |  |
| latency_p99_ms |  |
| cpu_throttled_seconds | 0.035 |
| max_rss_mb | 8.234 |
| disk_spill | false |
| status | oom |

## Por qué salió así

- 0 muestra(s) completada(s) en la ventana; se necesitan al menos 2 para un percentil (A4)
- 14992 consulta(s) fallidas o con timeout dentro de la ventana
- 19401 consulta(s) con error (no timeout) en toda la repetición
- OOM: oom_kill +0, OOMKilled=True

## Consultas en la ventana (A4)

| Dato | Valor |
|---|---|
| Completadas en la ventana | 0 |
| Timeouts en la ventana | 0 |
| Errores en la ventana | 14992 |
| Fracción de timeouts | None |
| Límite por consulta | 300 s |
| Percentiles válidos | {'p50': False, 'p95': False, 'p99': False} |
| Por tipo, toda la repetición | {'ok': 0, 'timeout': 0, 'error': 19401} |
| Workers cortados al final | 0 |
| Baja densidad muestral | sí |

## OOM

| Dato | Valor |
|---|---|
| `oom_kill` del cgroup (inicio → fin) | 4 → 4 |
| `oom` del cgroup (inicio → fin) | 156 → 156 |
| `OOMKilled` de Docker | True |
| ¿El contenedor seguía corriendo? | True |
| Recuento del dataset tras el OOM (R-08) | 500000 de 500000 filas en 1.1 s, intacto (intentos: 1) |
| `max_rss_mb` (anon) | 8.2 MiB |

`OOMKilled=true` con `Running=true` significa que el kernel mató **algún** proceso del cgroup del motor, no necesariamente el motor entero (F6.3).

**El OOM ocurrió ANTES de la ventana de medición**, no dentro: el contador `oom_kill` del cgroup no se movió durante la ventana (4 → 4). Como el contenedor se recrea en cada repetición, la marca `OOMKilled` de Docker es de esta misma repetición: el motor se quedó sin memoria durante el calentamiento.

**Cómo leer las columnas de recursos de esta fila:** con 0 consultas completadas, `cpu_throttled_seconds` (0.035) y `max_rss_mb` (8.234) describen un motor **ya colapsado**, no el costo de atender la carga. No se pueden citar como "lo que consumió el motor": lo que dicen es que durante la ventana el motor no estaba trabajando. Los errores registrados son conexiones rechazadas, no consultas ejecutadas.

## Recursos y entorno

| Dato | Valor |
|---|---|
| Throttling de CPU | 0.0 s |
| `max_rss_mb` (anon) | 8.2 MiB |
| Muestras de la serie de 1 s | 300 |
| `working_set` máximo (M3, SPEC A11) | 50.5 MiB |
| `shmem` máximo (F6-A3) | 15.1 MiB |
| Flush de caché | liberó 1068372 kB por la vía `ayudante_v7`, ok=True |
| Telemetría | completa |
| Límites reales del cgroup | {'cpu.max': '100000 100000', 'memory.max': '1073741824', 'memory.swap.max': '0', 'cpuset.cpus.effective': '0-7'} |
| Versión del motor | 18.6 (Debian 18.6-1.pgdg13+2) |

## Ejemplos de error del motor

```
worker 5: error: OperationalError: consuming input failed: server closed the connection unexpectedly
	This probably means the server terminated abnormally
	before or while processing the request.
worker 5: error: OperationalError: the connection is closed
worker 5: error: OperationalError: the connection is closed
worker 37: error: OperationalError: consuming input failed: server closed the connection unexpectedly
	This probably means the server terminated abnormally
	before or while processing the request.
worker 5: error: OperationalError: the connection is closed
```

## Evidencia original

- Crudo completo: `results/raw/postgresql_PROFILE_C_SEVERE_Q1_c50_r1.json`
- Telemetría de la ventana: `results/telemetry/postgresql_PROFILE_C_SEVERE_Q1_c50_r1.json`
- Plan de ejecución (R-31, solo en c=1): `no se captura en esta celda`
- Serie de 1 s del cgroup: dentro del crudo, en `serie_cgroup_1s`

