# Monitor IA — App iOS (iPhone 16 Pro)

App nativa **SwiftUI** que consume el backend de Monitor IA para ver en el iPhone, en
tiempo real, el estado de tu inferencia local: tokens, contexto, GPU, potencia, coste
energético y seguridad del servidor.

> Requiere el repo principal de Monitor IA en el servidor y iOS 17 o superior
> (iPhone 16 Pro con iOS 18+ funciona sin cambios). No usa dependencias externas:
> solo SwiftUI, Swift Charts y URLSession.

## Características

- **Resumen**
  - KPIs: tokens/s, contexto %, GPU %, potencia W, €/h y RAM %.
  - Gráficas nativas (Swift Charts) con selector 1 min / 15 min / 1 h / 24 h y métrica
    Tokens / Recursos / Potencia.
  - Gauges circulares de GPU (una tarjeta por tarjeta gráfica), TDP y RAM.
  - Panel de contexto con barra semáforo y datos de la última petición.
  - Coste de sesión/día, proyecciones hora/día/mes y €/1.000 tokens.
  - Alertas visuales y **haptic warning** al aparecer una alerta crítica nueva.
  - WebSocket en vivo con reconexión exponencial y pausa en segundo plano.
- **Seguridad**
  - Intentos SSH, logins, escaneos y bloqueos de firewall.
  - Clasificación **bot / humano / desconocido** y países con banderas (GeoIP).
  - Top IPs, usuarios objetivo, puertos y rutas escaneadas, eventos recientes.
  - Selector 1 h / 24 h / 7 días y refresco automático cada 10 s.
- **Ajustes**
  - URL del servidor (LAN `192.168.1.35:8080` o VPN `100.115.55.87:8080`) con validación.
  - Precio kWh, presupuesto diario, URL de inferencia, ventana de contexto, API key,
    modo simulación, fuente de tokens, proveedor GPU, webhook y umbrales de alerta.
  - Exportar histórico a CSV con share sheet nativo.
  - Reiniciar sesión y restaurar defaults del `.env`.

## Requisitos

- Mac con **Xcode 16+** (iOS 18 SDK; deployment target iOS 17).
- [**XcodeGen**](https://github.com/yonaskolb/XcodeGen): `brew install xcodegen`.
- iPhone 16 Pro (o simulador iPhone 16 Pro) con acceso a la red del servidor
  (misma Wi-Fi/LAN o VPN Tailscale 100.x).
- El backend de Monitor IA actualizado y accesible por HTTP en el puerto 8080
  (`http://192.168.1.35:8080`).

## Generar y ejecutar

```bash
cd ios
xcodegen generate
open MonitorIA.xcodeproj
```

En Xcode:

1. Selecciona el target **MonitorIA** → pestaña *Signing & Capabilities*.
2. Elige tu **Team** y cambia el *Bundle Identifier* si quieres
   (`com.yorch.monitoria` por defecto).
3. Destino **iPhone 16 Pro** (o un iPhone físico con iOS 17+).
4. Run (⌘R). La primera vez iOS pedirá permiso de **red local**: permite la conexión.
5. En la pestaña **Ajustes**, comprueba la URL del servidor (botones LAN / VPN) y pulsa
   **Aplicar**. En el primer arranque la URL por defecto es `http://192.168.1.35:8080`.

> El proyecto Xcode **no se versiona** (`ios/*.xcodeproj` está en .gitignore): se regenera
> con XcodeGen a partir de `project.yml`. Así se evitan conflictos del pbxproj.

## Estructura

```
ios/
├── project.yml                     # Proyecto XcodeGen (target iPhone, iOS 17)
├── Info.plist                      # ATS para HTTP en LAN/VPN + red local
├── README.md
└── MonitorIA/
    ├── App/
    │   ├── MonitorIAApp.swift      # @main + ciclo de vida / scenePhase
    │   └── RootView.swift          # TabView Resumen · Seguridad · Ajustes
    ├── Core/
    │   ├── APIClient.swift         # REST + CSV (snake_case ↔ camelCase)
    │   ├── MonitorStore.swift      # WebSocket, histórico, seguridad, ajustes, reintentos
    │   ├── Theme.swift             # tema dark, cards, botones
    │   └── Formatting.swift        # formato es-ES de unidades y fechas
    ├── Models/
    │   ├── TelemetryModels.swift   # espejo de /api/telemetry y /api/history
    │   ├── SecurityModels.swift    # espejo de /api/security
    │   └── SettingsModels.swift    # /api/settings + borrador editable
    ├── Views/
    │   ├── DashboardView.swift
    │   ├── SecurityView.swift
    │   ├── SettingsView.swift
    │   └── Components/
    │       ├── UIComponents.swift
    │       ├── Gauges.swift
    │       └── TelemetryChartsPanel.swift
    └── Resources/
        ├── Assets.xcassets         # icono 1024 + accent + launch color
        └── PrivacyInfo.xcprivacy
```

## Conexión con el backend

| Función | Endpoint |
|---|---|
| Snapshot inicial | `GET /api/telemetry` |
| Tiempo real | `WS /ws/telemetry` |
| Histórico | `GET /api/history?range=1m\|15m\|1h\|24h` |
| Seguridad | `GET /api/security?range=1h\|24h\|7d` |
| Ajustes | `GET/PUT /api/settings`, `POST /api/settings/reset` |
| Acciones | `POST /api/session/reset` |
| CSV | `GET /api/export.csv?range=…` |

La app deriva la URL del WebSocket de la URL del servidor (`http → ws`, `https → wss`) y
usa el mismo host/puerto, por lo que funciona igual a través de nginx (`:8080`) que
directamente contra FastAPI (`:8000`, expuesto).

## Notas de seguridad y App Store

- `Info.plist` incluye `NSAllowsArbitraryLoads` porque el backend se sirve por **HTTP**
  en LAN/VPN. Para publicar en App Store, sirve el dashboard por HTTPS (reverse proxy)
  y elimina esa excepción de ATS.
- La app no almacena credenciales del backend (no hay autenticación propia). La API key
  de inferencia se envía al servidor y se guarda allí; nunca se devuelve a la app.
- `PrivacyInfo.xcprivacy` declara el uso de `UserDefaults` (URL del servidor y preferencias).
- Uso interno: mantén el puerto 8080 restringido a tu LAN/Tailscale.

## Problemas típicos

| Síntoma | Solución |
|---|---|
| "No se puede conectar…" | Comprueba que el iPhone está en la misma red/VPN y que `http://IP:8080/api/health` abre en Safari. |
| Funciona en Safari y no en la app | Acepta el permiso de Red Local; revisa Ajustes → URL. |
| Gráficas sin datos | El backend está en modo live sin tráfico de tokens; usa el proxy `/proxy/v1` o el modo simulación. |
| Pantalla Seguridad vacía | El servidor necesita montar `/var/log` y `nginx-logs`; revisa las fuentes en la web. |
| Error de firma | Configura un Team y un bundle ID único en Xcode. |

## Compilación y CI

[![iOS build](https://github.com/Yorch82/monitor-ia/actions/workflows/ios-build.yml/badge.svg)](https://github.com/Yorch82/monitor-ia/actions/workflows/ios-build.yml)

La app se compila de forma automática en **GitHub Actions** sobre macOS 15 con
**Xcode 16.4**, destino iOS Simulator y sin firma (`.github/workflows/ios-build.yml`).
El proyecto usa SwiftUI/Swift Charts estándar y no tiene dependencias externas.
