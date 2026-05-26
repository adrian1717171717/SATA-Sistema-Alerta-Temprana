# SATA - Sistema de Alerta Temprana

SATA es un sistema de asistencia para vigilancia y alerta temprana orientado a la detección de amenazas en perímetros de seguridad mediante visión por computador e inteligencia artificial. Su propósito es apoyar la vigilancia humana a través del análisis de video en tiempo real, la detección de objetos de interés y la emisión de alertas operativas, sin reemplazar la toma de decisiones del operador. [file:2]

## Características principales

- Interfaz gráfica de operación desarrollada en Python.
- Procesamiento de video en tiempo real con OpenCV.
- Integración con modelos YOLO mediante Ultralytics.
- Soporte para diferentes fuentes de video, como cámara local, flujos IP y otras entradas operativas. [file:2]
- Arquitectura modular para cambiar de motor de inferencia sin rediseñar todo el sistema. [file:2]
- Enfoque de asistencia al operador bajo esquema human-in-the-loop. [file:2]

## Arquitectura general

El sistema se organiza en dos bloques funcionales:

### 1. Módulo de control
Gestiona la configuración de la operación, la selección del modo de vigilancia, el modelo de IA y parámetros de sensibilidad desde una interfaz de usuario. [file:2]

### 2. Módulo de inferencia
Procesa el flujo de video, ejecuta la detección de objetos mediante YOLO, evalúa zonas de interés y genera alertas cuando se detectan eventos relevantes. [file:2]

## Tecnologías utilizadas

- Python
- Tkinter [file:2]
- OpenCV [file:2]
- Ultralytics YOLO [file:2][web:15]
- CUDA (opcional, para aceleración por GPU) [file:2]

## Modelos base compatibles

### YOLOv8
Ultralytics documenta como modelos base de detección:
- `yolov8n.pt`
- `yolov8s.pt`
- `yolov8m.pt`
- `yolov8l.pt`
- `yolov8x.pt` [page:1]

### YOLOv10
Si el código está preparado para cambio de backend o de pesos, pueden documentarse como variantes base:
- `yolov10n.pt`
- `yolov10s.pt`
- `yolov10m.pt`
- `yolov10b.pt`
- `yolov10l.pt`
- `yolov10x.pt`

> La disponibilidad real dependerá de cómo el código cargue los pesos y del formato esperado por la versión instalada de Ultralytics o del backend implementado. [file:2][web:15]

## Requisitos

- Python 3.10 o superior
- pip
- Entorno Windows recomendado si se usa captura específica del escritorio o integración con APIs nativas. [file:2]
- GPU NVIDIA con CUDA opcional para mejorar el rendimiento de inferencia. [file:2]

## Instalación

```bash
git clone https://github.com/adrian1717171717/SATA-Sistema-Alerta-Temprana.git
cd SATA-Sistema-Alerta-Temprana
pip install -r requirements.txt
```

## Ejecución

```bash
python main.py
```

> Si el archivo principal tiene otro nombre, reemplazar `main.py` por el script de arranque real del proyecto.

## Modos de operación

- **Modo dinámico:** pensado para flujos de video transmitidos en red, por ejemplo RTMP. [file:2]
- **Modo centinela:** pensado para cámara local, webcam o fuente IP/RTSP. [file:2]
- **Modo garita:** pensado para capturar visualización de sistemas preexistentes en una estación operativa. [file:2]

## Flujo básico de uso

1. Iniciar el sistema.
2. Seleccionar el modo de vigilancia.
3. Elegir el modelo de detección.
4. Configurar fuente de video.
5. Definir parámetros de sensibilidad o zonas de interés.
6. Ejecutar monitoreo en tiempo real.
7. Atender alertas generadas por el sistema.

## Casos de uso

- Vigilancia perimetral.
- Supervisión de accesos restringidos.
- Apoyo a puestos de guardia.
- Monitoreo con cámaras fijas o plataformas móviles. [file:2]

## Consideraciones

SATA es un sistema de apoyo a la observación y alerta temprana. No sustituye la evaluación humana ni constituye por sí mismo un sistema autónomo de decisión táctica. [file:2]

## Licencia

Definir según el repositorio: MIT, GPL, uso académico o licencia institucional.
