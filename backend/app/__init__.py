"""
Monitor IA — backend.

Paquete principal de la aplicación FastAPI. Los submódulos están agrupados por
responsabilidad:

- ``app.config``   : configuración por variables de entorno (.env).
- ``app.core``     : modelos, cálculos puros (testeables), settings runtime, tokens y alertas.
- ``app.metrics``  : capas de abstracción para GPU (NVML/rocm-smi/Apple) y sistema (psutil).
- ``app.inference``: integración con servidores OpenAI-compatibles (monitor + proxy).
- ``app.telemetry``: bucle de muestreo, simulación, hub WebSocket y webhook de alertas.
- ``app.storage``  : persistencia SQLite (histórico + settings runtime).
- ``app.api``      : rutas REST/WebSocket expuestas al frontend.
"""

__version__ = "1.0.0"
