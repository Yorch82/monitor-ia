# Monitor IA — Panel de observabilidad para inferencia local

[![iOS build](https://github.com/Yorch82/monitor-ia/actions/workflows/ios-build.yml/badge.svg)](https://github.com/Yorch82/monitor-ia/actions/workflows/ios-build.yml)
[![Backend & frontend](https://github.com/Yorch82/monitor-ia/actions/workflows/ci.yml/badge.svg)](https://github.com/Yorch82/monitor-ia/actions/workflows/ci.yml)

Dashboard en tiempo real para **monitorizar un modelo de IA que se ejecuta en tu propio servidor**
(Ollama, llama.cpp, vLLM, LM Studio…): tokens, ocupación de contexto, GPU/VRAM, temperatura,
ventilador, **potencia eléctrica**, **coste energético en euros** y RAM del sistema.

- **Backend** en el servidor (192.168.1.35 en LAN, **100.115.55.87** en VPN): Python + FastAPI + SQLite.
- **Frontend** accesible desde cualquier equipo externo (PC de escritorio, portátil…) con un navegador:
  React + Tailwind + Recharts, tema oscuro tipo panel de control.
- **Pestaña Seguridad**: intentos SSH, bloqueos de firewall, escaneos web, clasificación bot/usuario,
  país/ciudad/ISP de origen y métricas de amenaza del servidor.
- **Pestaña Refrigeración**: temperaturas CPU/GPU, RPM y PWM de ventiladores, perfiles
  silencioso/equilibrado/máximo/automático y control manual (opt-in, fail-safe).
- **App iOS nativa** (SwiftUI, iPhone 16 Pro): el mismo dashboard, refrigeración, seguridad y
  ajustes con gráficas Swift Charts, gauges y WebSocket en vivo — ver [`ios/README.md`](ios/README.md).
- **Modo simulación** con datos sintéticos realistas para probar todo sin hardware ni modelo.

---

## 1. Arquitectura

```
┌─────────────────────────── servidor local (192.168.1.35 / 100.115.55.87) ───────────────────────────┐
│                                                                                                    │
│   docker compose up -d                                                                             │
│   ┌───────────────────────────┐         ┌────────────────────────────┐                             │
│   │  frontend (nginx:80)      │  /api,  │  backend (FastAPI:8000)    │                             │
│   │  React + Tailwind +       │ /proxy, ├────────────────────────────┤     ┌─────────────────────┐ │
│   │  Recharts  ◄──────────────┼──/ws────┤ • sampler async (N ms)     │────►│ SQLite (histórico)  │ │
│   └───────────────────────────┘         │ • GpuProvider (NVML/rocm)  │     └─────────────────────┘ │
│              ▲                          │ • SystemSampler (psutil)   │                             │
│              │ WebSocket (1 s)          │ • InferenceMonitor (health │        proxies UP            │
│              │                          │   + /metrics Prometheus)   │ ┌────────┐  ┌─────────────┐ │
│   PC externo ┘                          │ • AlertManager + webhook   │ │Ollama/ │  │ llama.cpp / │ │
│   (LAN o VPN)                           └──────────┬─────────────────┘ │vLLM/LM │  │ vLLM        │ │
│                                                    │ /proxy/v1/*       │Studio  │  └─────────────┘ │
│                                                    └───────►  captura `usage` de cada respuesta      │
└────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

**Cómo fluyen los datos (resumen en 5 líneas):**

1. Un **bucle de muestreo asíncrono** (intervalo configurable, 1 s por defecto) agrega 4 capas de proveedores desacoplados: GPU (NVML/rocm-smi/Apple), sistema (psutil), monitor de inferencia (salud + Prometheus) y agregador de tokens.
2. El **proxy OpenAI-compatible** `/proxy/v1/chat/completions` reenvía las peticiones del cliente de IA al servidor real y captura el campo `usage` (streaming y no-streaming) → tokens por petición, tokens/s y ocupación de contexto.
3. Cada tick produce un `TelemetryFrame` tipado que se **persiste en SQLite** y se difunde por **WebSocket** a todos los dashboards conectados.
4. Los **umbrales de alerta** se evalúan en el backend (contexto, temp GPU, VRAM, RAM, coste diario) con cooldown y webhook opcional; el frontend muestra banner y toasts.
5. El frontend es un conjunto de KPIs + gauges SVG + gráficas Recharts con selector de rango (1 m/15 m/1 h/24 h) y **export CSV**; nginx del frontend hace proxy de `/api`, `/ws` y `/proxy` al backend.

> Nota de despliegue: el **backend se instala en el propio servidor**; el frontend solo sirve el build de React (nginx). Se puede incluso separar el frontend en otro PC apuntando `VITE_API_BASE` a la IP del servidor.

---

## 2. Métricas monitorizadas

| Grupo | Qué se muestra |
|---|---|
| **Tokens** | input/output/total acumulados de sesión y por petición, **tokens/s instantánea (ventana 5 s)** y **media móvil (60 s)**, velocidad de la última petición, histórico en gráficas |
| **Contexto** | `tokens usados / ventana máxima`, % con barra semáforo (verde <70 %, ámbar 70-90 %, rojo >90 %), auto-detección de la ventana en Ollama (`/api/ps`) y llama.cpp (`/props`) |
| **GPU** | por tarjeta (multi-GPU): uso %, VRAM usada/total, temperatura, ventilador, potencia y límite/TDP |
| **Potencia** | W actuales / límite (TDP) sumando GPUs, **energía integrada de sesión en Wh/kWh** |
| **Coste** | € en tiempo real y acumulado (`kWh × precio`), proyección hora/día/mes al ritmo actual, **€ por 1.000 tokens generados**, presupuesto diario con alerta |
| **Sistema** | RAM usada/total (GB, %), CPU %, swap, uptime |
| **Seguridad** | intentos SSH (fallidos/exitosos/escaneos), bloqueos de firewall y puertos, escaneos web, IPs únicas, países/ciudad/ISP, usuarios objetivo, rutas escaneadas, bots vs humanos |
| **Refrigeración** | temperatura CPU/GPU/sensores, RPM y PWM por ventilador, perfiles (silencioso/equilibrado/máximo/automático), control manual y emergencia térmica |

### Fuentes de datos
- **GPU y potencia**: NVIDIA **NVML** (`nvidia-ml-py`), con capa de abstracción preparada para **AMD** (`rocm-smi --json`) y **Apple Silicon** (`powermetrics`). Multi-GPU: una tarjeta por GPU.
- **RAM/CPU/swap**: `psutil`.
- **Tokens y contexto**: proxy OpenAI-compatible (recomendado, captura `usage`) y/o counters Prometheus de llama.cpp (`llamacpp:tokens_*_total`) y vLLM (`vllm:prompt_tokens_total`, `vllm:generation_tokens_total`).
- **Seguridad**: `auth.log`/`secure` (SSH), `ufw.log` (firewall), access log de nginx (escaneos web) y geolocalización de IPs con ip-api.com + caché SQLite.
- **Refrigeración**: sensores y PWM vía **hwmon** (`/sys/class/hwmon`, lm-sensors), **NVML** para GPU y un simulador para probar sin hardware. Control opt-in con escritura en sysfs.
- **Simulación**: máquina de estados sintética (idle→prompt→generate) con inercia térmica y ruido, totalmente realista.

---

## 3. Arranque rápido (un comando)

```bash
git clone <este-repo> monitor-ia && cd monitor-ia
cp .env.example .env            # revisa precio €/kWh y ajusta lo que quieras
docker compose up -d --build    # construye y arranca backend + frontend
```

- Dashboard: **http://localhost:8080** (en el servidor) o **http://192.168.1.35:8080** / **http://100.115.55.87:8080** desde otro equipo (LAN/VPN).
  > ⚠️ En el servidor, abre el puerto 8080 (y 8000 si quieres usar el proxy directo) en el firewall de red local.
- Arranca en **modo simulación** (`SIMULATION_MODE=true`) para ver todo funcionando sin hardware.

### Pasar a modo REAL con GPU NVIDIA

1. Edita `.env`:
   ```env
   SIMULATION_MODE=false
   GPU_PROVIDER=nvidia
   INFERENCE_BASE_URL=http://host.docker.internal:11434/v1   # Ollama (o el puerto de tu engine)
   CONTEXT_WINDOW=8192
   ```
2. Sube con el overlay de GPU (para NVML):
   ```bash
   docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d --build
   ```
   Requiere Docker con soporte GPU (Docker Desktop o NVIDIA Container Toolkit) y driver NVIDIA en el anfitrión. Si algo falla, el dashboard muestra "GPU sin datos" con el motivo en lugar de romperse.

### Actualizar los contenedores
```bash
git pull && docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d --build
```

> **AMD (rocm-smi)**: instala el driver ROCm en el anfitrión y monta el binario, o ejecuta el backend fuera de Docker. **Apple Silicon**: `sudo powermetrics` requiere permisos (ver `app/metrics/apple.py`).

---

## 4. Integración con tu servidor de inferencia

### Opción A — Proxy (recomendada: métricas por petición)

Apunta tu cliente de IA (curl, LiteLLM, openhands, app… ) al **backend** en lugar del engine:

```
http://192.168.1.35:8080/proxy/v1     ← vía frontend (nginx)
http://192.168.1.35:8000/proxy/v1     ← directamente al backend
```

Ejemplo con Ollama en el host:

```bash
curl http://192.168.1.35:8080/proxy/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"qwen2.5-coder:32b","messages":[{"role":"user","content":"¿Cómo está el clima?"}]}'
```

El backend reenvía al engine configurado (`INFERENCE_BASE_URL`), registra el `usage` de cada
respuesta (soporta **streaming** si el engine incluye `usage` en el último chunk o acepta
`stream_options.include_usage`) y muestra: tokens por petición, tokens/s, ocupación de contexto…

### Opción B — Prometheus `/metrics` (sin tocar el cliente)

Si usas **llama.cpp** o **vLLM**, deja vacía `INFERENCE_METRICS_URL` y el backend sondeará
`{base−/v1}/metrics` cada 5 s sumando los counters (`tokens_predicted_total`, `prompt_tokens_total`…).
En la página de Ajustes puedes forzar `token_source=proxy|prometheus|auto`.

### Modo simulación (por defecto)

No requiere nada: sirve datos sintéticos coherentes (GPU sintética, peticiones con fases…) para
probar táctilmente el dashboard, las alertas y los ajustes desde cualquier PC.

---

## 5. Uso del dashboard

- **Fila KPI superior**: tokens/s, contexto %, GPU %, W, €/h, RAM %.
- **Gráficas** (tokens, recursos, potencia) con selector **1 m / 15 min / 1 h / 24 h** que también alimenta el **export CSV** del botón de la cabecera (`/api/export.csv?range=…`).
- **Gauges circulares** por GPU (tarjeta por GPU con VRAM, temp, fan, W), TDP y RAM.
- **Panel de coste**: sesión, diario, proyecciones a 1 h/día/mes y **€/1 k tokens** con barra de presupuesto diario.
- **Pestaña Seguridad** (`/security`): estado de las fuentes (SSH, firewall, nginx, GeoIP), intentos SSH,
  IPs/países con más actividad, bots vs humanos, usuarios objetivo, puertos y rutas escaneadas y eventos recientes.
- **Pestaña Refrigeración** (`/cooling`): temperaturas CPU/GPU, RPM/PWM de cada ventilador, perfiles
  silencioso/equilibrado/máximo/automático, slider manual, ventilación máxima inmediata y liberación del control a la BIOS.
- **Ajustes** (`/settings`): €/kWh, intervalo de refresco, URL del servidor de inferencia, ventana de contexto, fuente de tokens, webhook, retención, umbrales y toogles de simulación/proveedor.
- **Reiniciar sesión**: desde Ajustes, borra hueco de tokens/energía/coste de la sesión actual (el histórico en disco no se toca).
- **Alertas visuales**: banner superior + toasts automáticos cuando se activa un umbral.

### Seguridad del servidor

El backend lee los logs del host (solo lectura) mediante los volúmenes que ya trae `docker-compose.yml`:

| Fuente | Fichero por defecto | Datos |
|---|---|---|
| SSH | `/var/log/auth.log` o `/var/log/secure` | intentos fallidos, logins aceptados, escaneos SSH, usuarios objetivo |
| Firewall | `/var/log/ufw.log` | conexiones bloqueadas, IP origen y puerto destino |
| Nginx | volumen `nginx-logs` | rutas de escaneo (`.env`, `wp-admin`, `.git`…) y sondeos a la API |
| GeoIP | ip-api.com (caché 30 días) | país, ciudad, ISP; IPs privadas/CGNAT → «Red local» |

- Activa el logging de UFW si aún no lo está: `sudo ufw logging on`.
- Los logs se leen **de forma incremental** (offsets en SQLite, tolerante a rotación) y se agregan por hora/día.
- Retención configurable (`SECURITY_RETENTION_HOURS=168` → 7 días). La clasificación bot/humano es heurística:
  fallos SSH y patrones de escáner ⇒ bot; un login SSH correcto ⇒ humano.
- **Privacidad**: la geolocalización consulta `ip-api.com` (HTTP) solo para IPs públicas y cachea el resultado;
  puedes desactivarla con `GEOIP_ENABLED=false`. Las IPs de la LAN/Tailscale no salen del servidor.
- En sistemas sin `auth.log` (solo journald) instala `rsyslog` o apunta `SECURITY_LOG_PATHS` a otro fichero.
  En Windows/macOS con Docker Desktop `/var/log` no contiene los logs del host: la pestaña muestra "sin datos"
  con las fuentes en ámbar (no rompe nada).
- Endpoint: `GET /api/security?range=1h|24h|7d`.

### Refrigeración del servidor

La pestaña **Refrigeración** monitoriza y opcionalmente controla los ventiladores:

| Perfil | Uso recomendado | PWM |
|---|---|---|
| Silencioso | Invierno / mínimo ruido | 30 % |
| Equilibrado | Uso diario | 50 % |
| Máximo | Verano / cargas altas | 100 % |
| Automático | Curva según temperatura | 25–100 % |
| Personalizado | Ajuste manual por ventilador | slider |

- **Monitorización** (siempre): temperaturas por sensor (CPU, GPU NVIDIA, placa, NVMe), RPM, PWM y estado.
- **Control**: desactivado por defecto (`COOLING_CONTROL_ENABLED=false`, solo lectura). Para habilitarlo se
  necesita un servidor Linux con driver **hwmon** que exponga `pwm*` y montar `/sys` con permisos de escritura:

  ```bash
  docker compose -f docker-compose.yml -f docker-compose.gpu.yml \
                 -f docker-compose.cooling.yml up -d --build
  ```

  ⚠️ El overlay usa `privileged: true` y `/sys` en escritura; es potente y sensible. Úsalo solo en tu servidor.
  Comprueba antes con `sensors` y `ls /sys/class/hwmon/hwmon*/pwm*`. Si no aparecen canales PWM, el panel
  seguirá funcionando en **solo lectura**.
- **Ventiladores de GPU** (opcional): `COOLING_GPU_FANS_ENABLED=true` usa NVML; no todas las tarjetas/drivers
  lo permiten. Desactivado por defecto.
- **Seguridad térmica**: PWM mínimo 20 %, emergencia a 88 ºC (fuerza 100 %), liberación a 80 ºC y restauración
  del control de la BIOS al detener el backend (`COOLING_RESTORE_ON_EXIT=true`).
- El perfil y los ajustes manuales persisten en SQLite y se aplican al arrancar si el control está habilitado.
- Endpoints: `GET /api/cooling`, `PUT /api/cooling/profile`, `PUT /api/cooling/fans/{id}`,
  `POST /api/cooling/release`.

### Alertas configurables
contexto > 90 % · temperatura GPU > 80 ºC · VRAM > 95 % · RAM > 90 % · coste diario > límite €.
Con `WEBHOOK_URL` configurado, cada activación/escalado dispara un `POST` JSON:

```json
{ "app": "monitor-ia", "type": "alert",
  "alert": { "id": "gpu0_temp", "severity": "critical", "message": "GPU 0: 86 ºC …", "value": 86.0, "threshold": 80.0, "ts": 1762311000.0 } }
```

---

## 6. Estructura del proyecto

```
monitor-ia/
├── docker-compose.yml            # backend + frontend (nginx) + volúmenes de logs
├── docker-compose.gpu.yml        # overlay para NVML/GPU NVIDIA real
├── docker-compose.cooling.yml    # overlay de control PWM (privileged + /sys rw)
├── .env.example
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt          # + requirements-dev.txt (pytest)
│   ├── pytest.ini
│   ├── tests/                    # costes, contexto, alertas, settings, seguridad, refrigeración
│   └── app/
│       ├── config.py             # .env → AppConfig (pydantic-settings)
│       ├── main.py               # create_app + lifespan (wiring completo)
│       ├── core/                 # modelos tipados, cálculos puros, settings runtime,
│       │                         # agregadores de tokens y alertas (todo y solo esto)
│       ├── metrics/              # base.py (fábrica) + nvidia.py, amd.py, apple.py, system.py
│       ├── cooling/              # profiles.py, hwmon.py, gpu_fans.py, simulator.py, service.py
│       ├── inference/            # monitor.py (health+/metrics+contexto) y proxy.py (usage)
│       ├── security/             # parsers.py (SSH/UFW/nginx), middleware.py, service.py (GeoIP)
│       ├── telemetry/            # sampler.py, simulator.py, hub.py (WS), notifier.py (webhook)
│       ├── storage/database.py   # SQLite: samples, seguridad, settings, refrigeración, CSV
│       └── api/routes.py         # REST + WebSocket
└── frontend/
    ├── Dockerfile + nginx.conf   # nginx también escribe el access log de seguridad
    └── src/
        ├── state/MonitorContext.tsx   # WebSocket + histórico + rango compartido
        ├── lib/ (api, format, points) # fetch, unidades, mapeo snapshot→chart
        ├── components/ (layout, dashboard, charts, ui) # KPIs, gauges, charts, toasts
        └── pages/ (Dashboard, Cooling, Security, Settings)
```

Además, [`ios/`](ios/README.md) contiene la **app nativa SwiftUI** para iPhone 16 Pro
(proyecto XcodeGen, sin dependencias externas): Resumen, Refrigeración, Seguridad y Ajustes,
Swift Charts, gauges, WebSocket, hápticos y export CSV por share sheet. Se genera con
`cd ios && xcodegen generate`.

---

## 7. Endpoints del backend

| Método | Ruta | Descripción |
|---|---|---|
| GET | `/api/health` | estado del proceso (modo, uptime, clientes WS) |
| GET | `/api/telemetry` | último frame completo |
| **WS** | `/ws/telemetry` | stream de frames (≈ cada intervalo) |
| GET | `/api/history?range=1m\|15m\|1h\|24h` | puntos agregados para las gráficas |
| GET | `/api/export.csv?range=…` | descarga del histórico crudo en CSV |
| GET/PUT | `/api/settings` | settings runtime (precio, intervalo, inferencia, umbrales…) |
| POST | `/api/settings/reset` | vuelve a los defaults del `.env` |
| POST | `/api/session/reset` | reinicia tokens/energía/coste de sesión |
| GET | `/api/security?range=1h\|24h\|7d` | intentos SSH, firewall, escaneos web, países y bots |
| GET | `/api/cooling` | temperaturas, RPM/PWM, perfiles y estado del control |
| PUT | `/api/cooling/profile` | aplica un perfil (`silent`, `balanced`, `max`, `auto`) |
| PUT | `/api/cooling/fans/{id}` | PWM manual de un ventilador (`pwm_pct` 0-100) |
| POST | `/api/cooling/release` | devuelve el control a la BIOS/EC |
| POST | `/proxy/v1/chat/completions`, `/proxy/v1/completions`, `/proxy/v1/responses` | pasarela OpenAI-compatible con captura de usage |
| GET | `/docs` | Swagger/OpenAPI |

---

## 8. Tests

```bash
cd backend
python -m venv .venv && source .venv/bin/activate   # o activa .venv\Scripts\activate en Windows
pip install -r requirements-dev.txt
pytest        # → 52 tests: costes (€, kWh, proyecciones, €/1k), contexto (70/90, límites),
              #    alertas (umbrales, cooldown, escalado), settings, energía SQLite,
              #    parsers de seguridad y perfiles/curva de refrigeración
```

## 9. Desarrollo sin Docker

```bash
# Terminal 1 — backend
cd backend && pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# Terminal 2 — frontend (Vite con proxy a :8000)
cd frontend && npm install && npm run dev      # http://localhost:5173
```

Ajustes del frontend en dev: `VITE_BACKEND_URL`/`VITE_API_TARGET` (por defecto `http://localhost:8000`) o `VITE_API_BASE` para URLs absolutas (p. ej. `http://192.168.1.35:8000` cuando el backend corre en el servidor y el frontend en tu PC).

## 10. Notas y limitaciones

- **Potencia**: NVML mide el consumo del GPU; el coste se calcula con esa potencia integrada (Δt acotado a 10 s para evitar saltos tras hibernación). No incluye el resto del PC: la proyección es del consumo de GPUs.
- **Contexto**: se observa vía proxy/`usage`; con Prometheus no hay uso exacto de ventana (mostrará "sin datos" salvo simulación/proxy).
- **Streaming**: en engines que no emiten `usage` en el último chunk, la captura por streaming puede no estar disponible (usa no-streaming o Prometheus).
- **Seguridad**: no hay autenticación — mantén el acceso restringido a LAN/VPN/Tailscale.
- **Refrigeración**: el control PWM depende del hardware/driver. En Windows/Docker Desktop o sin canales
  `pwm*` solo se monitoriza. El overlay de control es `privileged` y monta `/sys` en escritura: úsalo con cuidado
  y revisa los perfiles/permissions antes de dejarlo en producción.
- Los ajustes de la UI se persisten en SQLite (`backend/data/` o volumen `monitor-data` en Docker) con prioridad sobre `.env`.

## 11. App iOS nativa (iPhone 16 Pro)

El directorio [`ios/`](ios/README.md) contiene una app **SwiftUI + Swift Charts** sin
dependencias externas que reutiliza la misma API y WebSocket del backend:

- **Resumen** (KPIs, gráficas 1m/15m/1h/24h, gauges GPU/TDP/RAM, coste, alertas con hápticos)
- **Refrigeración** (temperaturas, RPM/PWM, perfiles y control manual con seguridad térmica)
- **Seguridad** (SSH, firewall, escaneos web, bots, países, top IPs/usuarios/puertos/rutas)
- **Ajustes** (URL LAN/VPN, precio kWh, inferencia, umbrales, export CSV por share sheet)

Requisitos: Mac con Xcode 16+, XcodeGen (`brew install xcodegen`) y un iPhone con iOS 17+.
Generación del proyecto y ejecución:

```bash
cd ios
xcodegen generate
open MonitorIA.xcodeproj   # selecciona Team, destino iPhone 16 Pro y Run
```

La app viene configurada por defecto con `http://192.168.1.35:8080` y permite cambiar a
`http://100.115.55.87:8080` desde Ajustes. Incluye permiso de red local y excepción ATS
para HTTP en LAN/VPN (ver notas de App Store en `ios/README.md`).

## Licencia

MIT — ver [LICENSE](LICENSE).
