"""
S.A.V.I.A. — PLANIFICADOR CENTRAL DE MISIONES ISR
Implementa el patrón Strategy: genera listas de Waypoints para cualquier
patrón de vuelo sin depender del ejecutor (Pasivo o Activo).

Patrones soportados:
  - Cuadrícula (Grid Scan / Lawnmower): barrido sistemático de un área
  - Perímetro: vuelo alrededor del perímetro del área
  - Punto a punto: lista manual de waypoints
  - Loiter sobre objetivo: generación de waypoints circulares de orbita
"""
from __future__ import annotations
import math
import uuid
from typing import List, Optional, Callable
from .data_models import (
    Waypoint, AreaMision, ConfigMision, TipoMision,
    EstadoMision, ObjetivoDetectado
)


class PlanificadorMision:
    """
    Planificador central de misiones ISR.
    
    Responsabilidades:
      - Generar trayectorias de vuelo (Waypoints) a partir del área y tipo de misión
      - Calcular distancia total y tiempo estimado de vuelo
      - Insertar waypoints de Loiter cuando se detecta un objetivo de alto valor
      - Exportar planes en formatos compatibles (lista Python, dict para MAVLink)
    
    Patrón de diseño: Strategy — el planificador es independiente del ejecutor.
    El mismo plan puede ser consumido por SaviaPassivo (análisis manual) o
    SaviaActivo (ejecución autónoma MAVLink).
    """
    
    def __init__(self):
        self._estado: EstadoMision = EstadoMision.PLANIFICANDO
        self._config: Optional[ConfigMision] = None
        self._waypoints: List[Waypoint] = []
        self._callbacks_cambio: List[Callable] = []
    
    # ─── API pública ──────────────────────────────────────────────────────────
    
    def configurar(self, config: ConfigMision) -> 'PlanificadorMision':
        """Configura la misión. Retorna self para encadenamiento fluente."""
        self._config  = config
        self._estado  = EstadoMision.PLANIFICANDO
        self._waypoints = []
        return self
    
    def planificar(self) -> List[Waypoint]:
        """
        Genera la lista de waypoints según el tipo de misión configurado.
        Retorna la lista de Waypoints ordenada para su ejecución.
        """
        if not self._config:
            raise ValueError("Misión no configurada. Llame a configurar() primero.")
        
        tipo = self._config.tipo
        
        if tipo == TipoMision.CUADRICULA:
            self._waypoints = self._generar_cuadricula()
        elif tipo == TipoMision.PERIMETRO:
            self._waypoints = self._generar_perimetro()
        elif tipo == TipoMision.PUNTO_A_PUNTO:
            self._waypoints = list(self._config.waypoints)  # Usar los WPs del usuario
        elif tipo == TipoMision.LOITER:
            if not self._config.waypoints:
                raise ValueError("LOITER requiere al menos un waypoint central.")
            wp_centro = self._config.waypoints[0]
            self._waypoints = self._generar_loiter(
                wp_centro.latitud, wp_centro.longitud,
                wp_centro.altitud, self._config.loiter_radio
            )
        else:
            raise NotImplementedError(f"Tipo de misión no soportado: {tipo}")
        
        self._estado = EstadoMision.LISTA
        self._notificar_cambio()
        return self._waypoints
    
    def insertar_loiter_objetivo(self, objetivo: ObjetivoDetectado,
                                  altitud: float = 40.0,
                                  radio: float = 30.0) -> List[Waypoint]:
        """
        Genera waypoints de Loiter sobre un objetivo detectado.
        Usado por el módulo Activo cuando detecta una amenaza de alto valor.
        Interrumpe la misión actual e inserta la órbita como nueva ruta.
        
        Args:
            objetivo: Objetivo detectado con coordenadas GPS calculadas
            altitud: Altitud de órbita en metros AGL
            radio: Radio de órbita en metros
        
        Returns:
            Lista de waypoints de la órbita (8 puntos uniformes en círculo)
        """
        if not objetivo.tiene_gps:
            raise ValueError("El objetivo no tiene coordenadas GPS calculadas.")
        
        wps_loiter = self._generar_loiter(
            objetivo.lat_objetivo, objetivo.lon_objetivo,
            altitud, radio, n_puntos=8
        )
        # Marcar todos como loiter=True para señalizar al ejecutor
        for wp in wps_loiter:
            wp.loiter = True
        return wps_loiter
    
    def calcular_metricas(self) -> dict:
        """
        Calcula métricas de vuelo del plan actual:
          - Distancia total en km
          - Tiempo estimado de vuelo en minutos
          - Número de waypoints
          - Área cubierta aproximada en hectáreas
        """
        if not self._waypoints:
            return {"error": "Sin waypoints generados"}
        
        distancia_total_m = 0.0
        for i in range(1, len(self._waypoints)):
            distancia_total_m += self._distancia_wp(
                self._waypoints[i-1], self._waypoints[i]
            )
        
        velocidad = self._config.velocidad_crucero if self._config else 5.0
        tiempo_s  = distancia_total_m / max(velocidad, 0.1)
        
        return {
            "n_waypoints":       len(self._waypoints),
            "distancia_km":      round(distancia_total_m / 1000, 2),
            "tiempo_min":        round(tiempo_s / 60, 1),
            "area_ha":           self._calcular_area_ha(),
            "altitud_m":         self._config.altitud_escaneo if self._config else 0,
        }
    
    def exportar_mavlink(self) -> List[dict]:
        """
        Exporta los waypoints en formato compatible con MAVLink/QGroundControl.
        Cada waypoint se convierte a un dict con campos MAVLink Mission Item.
        """
        items = []
        # Item 0: Home position (posición del primer WP)
        if self._waypoints:
            home = self._waypoints[0]
            items.append({
                "seq": 0, "frame": 0, "command": 16,  # MAV_CMD_NAV_WAYPOINT
                "current": 1, "autocontinue": 1,
                "param1": 0, "param2": 0, "param3": 0, "param4": 0,
                "x": home.latitud, "y": home.longitud, "z": home.altitud
            })
        for i, wp in enumerate(self._waypoints):
            cmd = 31  # MAV_CMD_NAV_LOITER_UNLIM si loiter, si no 16 = WAYPOINT
            if wp.loiter:
                cmd = 31
                p3 = wp.radio_loiter
            else:
                cmd = 16
                p3 = 0
            items.append({
                "seq":  i + 1,
                "frame": 3,         # MAV_FRAME_GLOBAL_RELATIVE_ALT
                "command": cmd,
                "current": 0,
                "autocontinue": 1,
                "param1": 0,        # Hold time (seconds)
                "param2": 2.0,      # Acceptance radius (meters)
                "param3": p3,       # Loiter radius
                "param4": float("nan"),  # Yaw (NaN = unchanged)
                "x": wp.latitud,
                "y": wp.longitud,
                "z": wp.altitud
            })
        return items
    
    @property
    def waypoints(self) -> List[Waypoint]:
        return list(self._waypoints)
    
    @property
    def estado(self) -> EstadoMision:
        return self._estado
    
    def on_cambio(self, callback: Callable) -> None:
        """Registra un callback para notificaciones de cambio de estado."""
        self._callbacks_cambio.append(callback)
    
    # ─── Generadores de trayectorias ──────────────────────────────────────────
    
    def _generar_cuadricula(self) -> List[Waypoint]:
        """
        Genera un patrón de cuadrícula (Lawnmower / Boustrophedon).
        La ruta barre el área en líneas paralelas con solapamiento mínimo.
        
        Dirección: Norte a Sur en columnas, de Oeste a Este.
        El patrón se optimiza para minimizar distancia total recorrida
        alternando la dirección en cada pasada (zigzag).
        """
        cfg  = self._config
        area = cfg.area
        if not area:
            raise ValueError("CUADRICULA requiere un AreaMision definida.")
        
        alt  = cfg.altitud_escaneo
        vel  = cfg.velocidad_crucero
        sep  = cfg.separacion_lineas  # metros entre líneas de barrido
        
        # Número de líneas de barrido (columnas Este-Oeste)
        # Se usa el ancho del área dividido por la separación
        # con corrección por latitud para longitud
        lat_centro = (area.lat_min + area.lat_max) / 2
        metros_por_grado_lon = 111_320 * math.cos(math.radians(lat_centro))
        
        # Separación en grados
        sep_lat = sep / 111_320.0         # Separación en grados de latitud
        sep_lon = sep / metros_por_grado_lon  # Separación en grados de longitud
        
        waypoints: List[Waypoint] = []
        
        # Iterar columnas de Oeste a Este
        lon = area.lon_min
        columna = 0
        while lon <= area.lon_max + sep_lon:
            lon_actual = min(lon, area.lon_max)
            
            # Alternar dirección Norte-Sur y Sur-Norte (zigzag)
            if columna % 2 == 0:
                lat_inicio, lat_fin = area.lat_max, area.lat_min
            else:
                lat_inicio, lat_fin = area.lat_min, area.lat_max
            
            waypoints.append(Waypoint(
                latitud=lat_inicio, longitud=lon_actual,
                altitud=alt, velocidad=vel
            ))
            waypoints.append(Waypoint(
                latitud=lat_fin, longitud=lon_actual,
                altitud=alt, velocidad=vel
            ))
            
            lon     += sep_lon
            columna += 1
        
        return waypoints
    
    def _generar_perimetro(self) -> List[Waypoint]:
        """
        Genera waypoints para vuelo perimetral del área de interés.
        Vuelo en sentido horario: NO → NE → SE → SO → NO
        """
        cfg  = self._config
        area = cfg.area
        if not area:
            raise ValueError("PERIMETRO requiere un AreaMision definida.")
        
        alt = cfg.altitud_escaneo
        vel = cfg.velocidad_crucero
        
        esquinas = [
            (area.lat_max, area.lon_min),   # NO
            (area.lat_max, area.lon_max),   # NE
            (area.lat_min, area.lon_max),   # SE
            (area.lat_min, area.lon_min),   # SO
            (area.lat_max, area.lon_min),   # Volver al origen
        ]
        return [Waypoint(lat, lon, alt, vel) for lat, lon in esquinas]
    
    def _generar_loiter(self, lat_c: float, lon_c: float,
                         alt: float, radio: float,
                         n_puntos: int = 8) -> List[Waypoint]:
        """
        Genera waypoints circulares para órbita alrededor de un punto.
        
        Args:
            lat_c, lon_c: Centro de la órbita
            alt: Altitud de vuelo en metros AGL
            radio: Radio de la órbita en metros
            n_puntos: Número de waypoints que forman el círculo
        """
        from .target_geolocator import GeolocalizadorObjetivos
        wps = []
        for i in range(n_puntos):
            rumbo = (360.0 / n_puntos) * i  # Ángulos uniformes en el círculo
            lat_wp, lon_wp = GeolocalizadorObjetivos.desplazar_punto(
                lat_c, lon_c, radio, rumbo
            )
            wps.append(Waypoint(
                latitud=lat_wp, longitud=lon_wp,
                altitud=alt, velocidad=5.0,
                loiter=True, radio_loiter=radio
            ))
        # Cerrar el círculo
        wps.append(wps[0])
        return wps
    
    # ─── Utilidades internas ──────────────────────────────────────────────────
    
    @staticmethod
    def _distancia_wp(wp1: Waypoint, wp2: Waypoint) -> float:
        """Distancia 3D entre dos waypoints en metros."""
        from .target_geolocator import GeolocalizadorObjetivos
        dist_h = GeolocalizadorObjetivos.distancia_haversine(
            wp1.latitud, wp1.longitud, wp2.latitud, wp2.longitud
        )
        dist_v = abs(wp2.altitud - wp1.altitud)
        return math.sqrt(dist_h**2 + dist_v**2)
    
    def _calcular_area_ha(self) -> float:
        """Área del bounding box de la misión en hectáreas."""
        if self._config and self._config.area:
            a = self._config.area
            return round(a.alto_m * a.ancho_m / 10_000, 2)
        return 0.0
    
    def _notificar_cambio(self):
        for cb in self._callbacks_cambio:
            try:
                cb(self._estado, self._waypoints)
            except Exception:
                pass
