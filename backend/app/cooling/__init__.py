"""Control y monitorización de refrigeración del servidor.

- ``profiles``  : curvas/perfiles de ventilación (seguros y testeables).
- ``hwmon``     : lectura y escritura de sensores/fans vía sysfs (Linux).
- ``gpu_fans``  : ventiladores de GPU vía NVML (opcional).
- ``simulator`` : datos sintéticos para probar el panel sin hardware.
- ``service``   : orquestación, seguridad térmica y snapshot para la API.
"""
