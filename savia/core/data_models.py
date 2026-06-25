"""
S.A.V.I.A. — Sistema de Asistencia Visual e Inteligencia Artificial
=====================================================================
Módulo CORE: Modelos de datos tácticos compartidos.
Todas las estructuras de datos que circulan entre el Planificador,
el Motor de Visión y los Ejecutores de Misión se definen aquí.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional, List
from enum import Enum, auto
import time


# ─────────────────────────────────────────────────────────────────────────────
# ENUMERACIONES TÁCTICAS
# ─────────────────────────────────────────────────────────────────────────────

class TipoMision(Enum):
    """Tipo de patrón de vuelo a ejecutar."""
    PUNTO_A_PUNTO  = auto()   # Waypoints lineales simples
    CUADRICULA     = auto()   # Grid scan (barrido de área)
    PERIMETRO      = auto()   # Perímetro de zona de interés
    LOITER         = auto()   # Merodeo/Orbita sobre objetivo

class EstadoMision(Enum):
    """Estado de ciclo de vida de la misión."""
    PLANIFICANDO   = auto()
    LISTA          = auto()
    EN_EJECUCION   = auto()
    PAUSADA        = auto()
    COMPLETADA     = auto()
    ABORTADA       = auto()
    RTB            = auto()   # Return To Base — Failsafe activado

class NivelAmenaza(Enum):
    """Clasificación de amenaza del objetivo detectado."""
    NINGUNA   = 0
    BAJA      = 1
    MEDIA     = 2
    ALTA      = 3
    CRITICA   = 4

class CausaFailsafe(Enum):
    """Causa que dispara el protocolo de Failsafe Táctico."""
    NINGUNA          = auto()
    BATERIA_CRITICA  = auto()   # Bingo Fuel — < umbral de batería
    PERDIDA_ENLACE   = auto()   # Signal Lost / Jamming detectado
    GEOFENCE         = auto()   # Dron fuera de zona autorizada
    COMANDO_OPERADOR = auto()   # RTB manual ordenado por el operador


# ─────────────────────────────────────────────────────────────────────────────
# DATACLASSES: ESTRUCTURAS DE DATOS PRIMARIAS
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class Waypoint:
    """
    Punto de referencia geoespacial de la misión.
    Unidades: latitud/longitud en grados decimales, altitud en metros AGL.
    """
    latitud:   float
    longitud:  float
    altitud:   float          # Altitud sobre el nivel del suelo (AGL) en metros
    velocidad: float  = 5.0   # Velocidad de tránsito al WP (m/s)
    loiter:    bool   = False  # Si True, orbitar en este punto hasta nueva orden
    radio_loiter: float = 30.0 # Radio de órbita en metros
    accion_llegada: str = ""   # Acción al llegar: "FOTO", "VIDEO", "INFORME", ""

    def __str__(self) -> str:
        return (f"WP[{self.latitud:.6f}, {self.longitud:.6f}, "
                f"{self.altitud:.1f}m] loiter={self.loiter}")


@dataclass
class AreaMision:
    """Define el polígono o bounding box del área de interés (AO)."""
    nombre:       str
    lat_min:      float
    lat_max:      float
    lon_min:      float
    lon_max:      float
    altitud_base: float = 50.0   # Altitud de escaneo por defecto en metros

    @property
    def centro(self) -> tuple[float, float]:
        return ((self.lat_min + self.lat_max) / 2,
                (self.lon_min + self.lon_max) / 2)

    @property
    def ancho_m(self) -> float:
        """Ancho aproximado del área en metros (Ecuación de Haversine simplificada)."""
        return abs(self.lon_max - self.lon_min) * 111_320 * 0.9  # Corrección latitud

    @property
    def alto_m(self) -> float:
        """Alto aproximado del área en metros."""
        return abs(self.lat_max - self.lat_min) * 111_320


@dataclass
class ParametrosCamara:
    """
    Parámetros ópticos de la cámara del dron.
    Necesarios para el cálculo de Geolocalización de Objetivos.
    """
    fov_horizontal: float = 84.0   # Campo visual horizontal en grados (DJI Mini 4K: 84°)
    fov_vertical:   float = 48.0   # Campo visual vertical en grados
    resolucion_w:   int   = 3840   # Resolución horizontal en píxeles (4K)
    resolucion_h:   int   = 2160   # Resolución vertical en píxeles
    gimbal_pitch:   float = -90.0  # Ángulo del gimbal en grados (−90 = nadir/vertical)

    @property
    def focal_equiv_px_h(self) -> float:
        """Longitud focal equivalente en píxeles (eje horizontal)."""
        import math
        return self.resolucion_w / (2 * math.tan(math.radians(self.fov_horizontal / 2)))

    @property
    def focal_equiv_px_v(self) -> float:
        """Longitud focal equivalente en píxeles (eje vertical)."""
        import math
        return self.resolucion_h / (2 * math.tan(math.radians(self.fov_vertical / 2)))


@dataclass
class TelemetriaFrame:
    """
    Snapshot de telemetría del dron en un instante de tiempo.
    Compatible con MAVLink (PX4/ArduPilot) y MAVSDK.
    """
    timestamp:      float = field(default_factory=time.time)
    latitud:        float = 0.0
    longitud:       float = 0.0
    altitud_rel:    float = 0.0    # Altitud AGL (metros)
    altitud_abs:    float = 0.0    # Altitud AMSL (metros)
    roll:           float = 0.0    # Balanceo (grados)
    pitch:          float = 0.0    # Cabeceo (grados)
    yaw:            float = 0.0    # Rumbo magnético (grados 0–360)
    velocidad:      float = 0.0    # Velocidad de tierra (m/s)
    bateria_pct:    int   = 100    # Porcentaje de batería (0–100)
    bateria_v:      float = 0.0    # Voltaje de batería
    rssi:           int   = -70    # Intensidad de señal RC (dBm)
    modo_vuelo:     str   = "MANUAL"
    satelites:      int   = 0
    gimbal_pitch:   float = -90.0  # Ángulo del gimbal en grados
    wp_actual:      int   = 0      # Índice del waypoint actual en misión

    @property
    def bateria_critica(self) -> bool:
        """True si la batería está en nivel Bingo Fuel (<= 20%)."""
        return self.bateria_pct <= 20

    @property
    def enlace_degradado(self) -> bool:
        """True si la señal RC está por debajo del umbral operativo (< -90 dBm)."""
        return self.rssi < -90

    @property
    def gps_valido(self) -> bool:
        """True si hay suficientes satélites para posicionamiento fiable."""
        return self.satelites >= 6

    def __str__(self) -> str:
        return (f"[{self.modo_vuelo}] "
                f"GPS({self.latitud:.6f},{self.longitud:.6f}) "
                f"Alt:{self.altitud_rel:.1f}m "
                f"Bat:{self.bateria_pct}% "
                f"RSSI:{self.rssi}dBm "
                f"Sats:{self.satelites}")


@dataclass
class ObjetivoDetectado:
    """
    Resultado de una detección de Visión Artificial.
    Incluye las coordenadas en pantalla Y las coordenadas GPS calculadas
    mediante el módulo de Geolocalización de Objetivos.
    """
    id_objetivo:    str              # UUID único por objetivo rastreado
    clase:          str              # Nombre de la clase detectada (ej. "Militar_Jaguar")
    confianza:      float            # Confianza del modelo 0.0–1.0
    nivel_amenaza:  NivelAmenaza     # Clasificación táctica

    # Coordenadas en píxeles (frame de video)
    bbox_x1:  int = 0
    bbox_y1:  int = 0
    bbox_x2:  int = 0
    bbox_y2:  int = 0

    # Coordenadas GPS calculadas (geolocalización)
    lat_objetivo: Optional[float] = None
    lon_objetivo: Optional[float] = None
    precision_m:  Optional[float] = None   # Error estimado en metros

    # Contexto de la detección
    timestamp:      float = field(default_factory=time.time)
    frame_numero:   int   = 0
    altitud_dron:   float = 0.0
    ruta_captura:   str   = ""     # Ruta al JPG de la captura automática

    @property
    def centro_px(self) -> tuple[int, int]:
        return ((self.bbox_x1 + self.bbox_x2) // 2,
                (self.bbox_y1 + self.bbox_y2) // 2)

    @property
    def tiene_gps(self) -> bool:
        return self.lat_objetivo is not None and self.lon_objetivo is not None

    def __str__(self) -> str:
        gps_str = (f"GPS({self.lat_objetivo:.6f},{self.lon_objetivo:.6f})"
                   if self.tiene_gps else "GPS:N/A")
        return (f"[{self.clase}] conf={self.confianza:.0%} "
                f"amenaza={self.nivel_amenaza.name} {gps_str}")


@dataclass
class ConfigMision:
    """
    Configuración completa de una misión ISR.
    Pasada al Planificador y luego al Ejecutor correspondiente.
    """
    nombre:             str
    tipo:               TipoMision
    area:               Optional[AreaMision]     = None
    waypoints:          List[Waypoint]            = field(default_factory=list)
    camara:             ParametrosCamara          = field(default_factory=ParametrosCamara)
    modelo_ia:          str                       = "yolov8n.pt"
    sensibilidad_ia:    float                     = 0.60
    altitud_escaneo:    float                     = 50.0    # metros AGL
    separacion_lineas:  float                     = 30.0    # metros (grid scan)
    velocidad_crucero:  float                     = 5.0     # m/s
    loiter_radio:       float                     = 30.0    # metros
    rtb_automatico:     bool                      = True
    umbral_bateria:     int                       = 25      # % para Bingo Fuel
    umbral_rssi:        int                       = -90     # dBm para detección Jamming
