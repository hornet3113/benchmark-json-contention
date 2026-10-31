# F0 — Salidas de comandos observadas

**Qué es este archivo.** Transcripción de las salidas de los comandos de la
fase F0, ejecutados por Alix el **2026-10-31** en su equipo y registrados
durante la sesión de planificación.

**Qué NO es.** No es la captura automática de un `tee`: los comandos de F0 se
corrieron de forma interactiva, antes de que existiera el repositorio, y su
salida se recogió en pantalla. Se transcribe aquí para que la evidencia viva
junto al proyecto, como promete `PLAN.md`.

Las capturas de pantalla originales son el respaldo primario. Si un revisor
necesita verificar cualquiera de estos valores, los comandos son reejecutables
y están todos anotados.

Entorno: Windows 11 + WSL2 (distribuciones `Ubuntu` y `docker-desktop`) +
Docker Desktop. Los comandos de Linux se ejecutaron en `Ubuntu`.

---

## Hardware y sistema anfitrión

```
Get-CimInstance Win32_Processor | Select-Object Name, NumberOfCores, NumberOfLogicalProcessors

Name                                  NumberOfCores  NumberOfLogicalProcessors
AMD Ryzen 5 PRO 5675U with Radeon Graphics        6                         12
```

```
Get-CimInstance Win32_ComputerSystem | ... RAM_GB
RAM_GB
------
  14.8
```

```
[math]::Round((Get-PSDrive C).Free / 1GB, 2)
473.06
```

## WSL2

```
wsl --version
Versión de WSL: 2.6.3.0
Versión de kernel: 6.6.87.2-1
Versión de WSLg: 1.0.71
Versión de MSRDC: 1.2.6353
Versión de Direct3D: 1.611.1-81528511
Versión de DXCore: 10.0.26100.1-240331-1435.ge-release
Versión de Windows: 10.0.26200.9711
```

```
wsl --status
Distribución predeterminada: docker-desktop
Versión predeterminada: 2

wsl -l -v
  NAME              STATE      VERSION
* docker-desktop    Stopped    2
  Ubuntu            Stopped    2
```

```
if (Test-Path "$env:USERPROFILE\.wslconfig") { Get-Content ... } else { "Sin configuracion WSL personalizada" }
Sin configuracion WSL personalizada
```

→ La VM usa los valores por defecto. Decisión D-WSL1: se conserva así.

```
wsl -d Ubuntu -- bash -lc "uname -r; stat -fc %T /sys/fs/cgroup; free -h; command -v sudo"
6.6.87.2-microsoft-standard-WSL2
cgroup2fs
               total        used        free      shared  buff/cache   available
Mem:           7.2Gi       994Mi       5.8Gi       4.5Mi       616Mi       6.2Gi
Swap:          2.0Gi          0B       2.0Gi
/usr/bin/sudo
```

→ **cgroups v2 confirmado** (`cgroup2fs`). `sudo` disponible.

## Docker

```
docker --version
Docker version 29.4.1, build 055a478

docker compose version
Docker Compose version v5.1.3
```

```
docker info | Select-String "OSType|Cgroup Version|CPUs:|Total Memory:"
Cgroup Version: 2
OSType: linux
CPUs: 12
Total Memory: 7.159GiB
```

```
wsl -d Ubuntu -- docker version
Client:  Version 29.4.1 · API 1.54 · go1.26.2 · linux/amd64 · Context default
Server:  Docker Desktop 4.71.0 (225177)
  Engine:      29.4.1 · API 1.54 (minimum 1.40) · linux/amd64
  containerd:  v2.2.3
  runc:        1.3.5
  docker-init: 0.19.0
```

→ Docker accesible desde la distribución `Ubuntu`: ahí correrán Python y los scripts.

---

## Prueba de aplicación real de límites

La prueba que decide si el proyecto es viable: si Docker no impusiera los
límites, el experimento correría sin contención y los números no medirían nada.

```
docker run --rm --cpus=1 --memory=1024m --memory-swap=1024m alpine:3.20 sh -c \
  'test -f /sys/fs/cgroup/cgroup.controllers && echo cgroups_v2=OK; \
   cat /sys/fs/cgroup/cpu.max; cat /sys/fs/cgroup/memory.max; cat /sys/fs/cgroup/memory.swap.max'

Digest: sha256:d9e853e87e55526f6b2917df91a2115c36dd7c696a35be12163d44e6e2a4b6bc
Status: Downloaded newer image for alpine:3.20

cgroups_v2=OK
100000 100000
1073741824
0
```

| Valor | Esperado | Obtenido |
|---|---|---|
| `cpu.max` | `100000 100000` (1 CPU) | `100000 100000` ✔ |
| `memory.max` | `1073741824` (1024 m) | `1073741824` ✔ |
| `memory.swap.max` | `0` | `0` ✔ |

→ **Los límites se aplican de verdad**, leídos desde dentro del contenedor.
`memswap_limit = mem_limit` deja el swap del contenedor en 0 (SPEC A7).

## Archivos de métricas que alimentan el CSV

```
docker run --rm alpine:3.20 sh -c 'for f in cpu.stat memory.stat memory.peak memory.events memory.swap.max; do test -f /sys/fs/cgroup/$f || exit 1; done; echo metric_files=OK'
metric_files=OK
```

---

## V1 — Alcance real de `drop_caches`

```
docker run --rm alpine sh -c 'dd if=/dev/zero of=/tmp/f bs=1M count=512; cat /tmp/f > /dev/null'
536870912 bytes (512.0MB) copied, 2.436584 seconds, 210.1MB/s

--- ANTES ---
Mem:  7331  999  5738  4  787  6331
sudo sh -c 'sync; echo 3 > /proc/sys/vm/drop_caches'
[sudo: authenticate] Password:
--- DESPUES ---
Mem:  7331  954  6141  4  387  6376
```

(columnas: total · used · free · shared · **buff/cache** · available, en MB)

| Momento | `buff/cache` |
|---|---|
| Antes | 787 MB |
| Después | 387 MB |

→ **Limpieza efectiva, NO caché frío.** El flush desde `Ubuntu` sí afecta al
caché de páginas que usan los contenedores de `docker-desktop`, porque
comparten el kernel de la VM. Quedaron 387 MB sin liberar y la capa de caché de
Windows sobre el `.vhdx` permanece intacta. Alcance declarado en SPEC A5.

→ **Incidencia operativa:** `sudo` pidió contraseña. Una corrida desatendida se
colgaría ahí. Pendiente **V7**, diseño en SPEC A5, sin aplicar.

## V3 — Sistema de archivos de trabajo

```
cd ~ && pwd && df -h .
/home/alix_anahi
Filesystem  Size  Used  Avail  Use%  Mounted on
/dev/sdf    1007G  2.1G   954G    1%  /
```

→ ext4 nativo de WSL2, no `/mnt/c/`. Evita L6.

## V4 — Espacio y consumo de Docker

```
df -h /; docker system df
Filesystem  Size  Used  Avail  Use%  Mounted on
/dev/sdf    1007G  2.1G   954G    1%  /

TYPE            TOTAL  ACTIVE  SIZE     RECLAIMABLE
Images          12     9       29.13GB  7.563GB (25%)
Containers      10     0       398.2MB  398.2MB (100%)
Local Volumes   10     8       2.237GB  772.7MB (34%)
Build Cache     127    0       19.01GB  1.578GB
```

→ 954 GB libres dentro de la VM, acotados en la práctica por los 473 GB libres
de C:. El proyecto necesita ~25 GB estimados. Docker ya ocupa ~51 GB de otros
proyectos: **no ejecutar `docker system prune -a`**, borraría trabajo ajeno a
este proyecto.

## V5 — Ruido en reposo

```
cat /proc/loadavg; free -h
0.38 0.12 0.04 1/436 1597
               total   used   free   shared  buff/cache  available
Mem:           7.2Gi  999Mi  5.7Gi    4.6Mi       679Mi       6.2Gi
Swap:          2.0Gi     0B  2.0Gi
```

→ Línea base contra la que se compara el ruido durante las corridas. Swap sin tocar.

## V6 — El throttling de CFS es observable

```
docker run --rm --cpus=0.5 alpine sh -c \
  'timeout 10 sh -c "while :; do :; done"; grep throttled_usec /sys/fs/cgroup/cpu.stat'
Terminated
throttled_usec 5022196
```

→ 5 022 196 µs ≈ **5.02 s estrangulados de 10 s** de carga continua con
`--cpus=0.5`. La aritmética cuadra con el límite impuesto: el instrumento mide
lo que dice medir. Es la verificación más importante de F0 junto con la de
límites.

---

## Estado de F0

| Verificación | Estado |
|---|---|
| Plataforma y hardware | ✔ medido |
| cgroups v2 | ✔ `cgroup2fs` |
| Límites aplicados de verdad | ✔ verificado desde dentro del contenedor |
| Archivos de métricas presentes | ✔ `metric_files=OK` |
| V1 — alcance de `drop_caches` | ✔ limpieza efectiva (787 → 387 MB) |
| V2 — ruta de respaldo del flush | **documentada, NO ejecutada** |
| V3 — sistema de archivos nativo | ✔ `/home/alix_anahi` en ext4 |
| V4 — espacio suficiente | ✔ 954 GB libres |
| V5 — ruido en reposo | ✔ loadavg 0.38 |
| V6 — throttling observable | ✔ 5.02 s de 10 s |
| V7 — `sudo` no interactivo | **diseñado, NO aplicado** |
| V8 — `mem_swappiness` en cgroups v2 | **abierta**, detectada en F1 |

F0 queda **cerrada con reservas explícitas**. V2 y V7 no se marcan porque no se
ejecutaron. V8 se abrió después, al construir F1.
