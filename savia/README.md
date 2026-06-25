# S.A.V.I.A. — Módulo de Misión Táctica

Arquitectura modular para sistemas ISR no tripulados.
Implementa los patrones **Strategy** y **Factory** para separar la planificación de la ejecución.

## Estructura del Proyecto

```
savia/
├── core/                        # Contratos y lógica central
│   ├── data_models.py           # Waypoint, Telemetría, Detección, ConfigMisión
│   ├── mission_planner.py       # Planificador: Cuadrícula, Perímetro, Loiter
│   ├── mission_executor.py      # Interfaz abstracta (Strategy Pattern)
│   └── target_geolocator.py    # Trigonometría: GPS del objetivo desde píxeles
│
├── modules/
│   ├── passive_isr/             # TIER 1: Solo análisis ISR
│   │   └── passive_executor.py  # YOLO + captura + CSV SALUTE
│   │
│   └── active_isr/              # TIER 2: Control completo de vuelo
│       ├── active_executor.py   # MAVLink + Geolocalización + Loiter + Failsafe
│       └── failsafe_manager.py  # Monitor: Bingo Fuel, Jamming, Geofence
│
├── main.py                      # Punto de entrada CLI
└── README.md
```

## Uso

### Modo Demostración (sin hardware)
```bash
python savia/main.py --demo --plan cuadricula --lat-min 4.70 --lat-max 4.72 --lon-min -74.08 --lon-max -74.06
```

### Tier 1 — Savia Pasivo (video USB)
```bash
python savia/main.py --tier pasivo --video 0 --modelo yolov8n.pt
```

### Tier 2 — Savia Activo (dron MAVLink)
```bash
python savia/main.py --tier activo --video rtsp://192.168.1.1/stream --mavlink udp://:14540 --modelo yolov8n.pt
```

## Patrones de Vuelo

| Patrón | Descripción |
|---|---|
| `cuadricula` | Barrido sistemático Boustrophedon (Lawnmower) |
| `perimetro` | Vuelo perimetral del área de interés |
| `punto` | Lista manual de waypoints |

## Capacidades por Tier

| Capacidad | Pasivo | Activo |
|---|:---:|:---:|
| Video RTSP / USB | ✓ | ✓ |
| Detección YOLO | ✓ | ✓ |
| Captura automática | ✓ | ✓ |
| Reporte PDF SALUTE | ✓ | ✓ |
| Telemetría GPS/IMU | ✗ | ✓ |
| Control de vuelo MAVLink | ✗ | ✓ |
| Geolocalización de objetivos | ✗ | ✓ |
| Loiter on Target | ✗ | ✓ |
| Failsafe Táctico (RTB) | ✗ | ✓ |

## Dependencias

```bash
pip install ultralytics opencv-python pymavlink numpy
# GPU: pip install torch --index-url https://download.pytorch.org/whl/cu121
```
