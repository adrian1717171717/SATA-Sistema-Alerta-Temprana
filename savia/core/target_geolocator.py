"""
S.A.V.I.A. — MÓDULO DE GEOLOCALIZACIÓN DE OBJETIVOS
Calcula las coordenadas GPS de un objetivo en tierra a partir de:
  - Posición GPS del dron (latitud, longitud, altitud AGL)
  - Ángulo del gimbal (pitch en grados, -90 = nadir)
  - Parámetros de la cámara (FOV horizontal/vertical, resolución)
  - Posición en píxeles del objetivo en el frame de video

Método matemático:
  1. Convertir desplazamiento en píxeles a ángulos de offset desde el boresight
  2. Construir el vector de la cámara en coordenadas locales (NED)
  3. Calcular la distancia al suelo en X e Y (metros)
  4. Convertir desplazamiento en metros a delta de lat/lon
"""
from __future__ import annotations
import math
from typing import Optional, Tuple
from dataclasses import dataclass

# Earth radius in meters
EARTH_RADIUS_M = 6_371_000.0


@dataclass
class ResultadoGeolocacion:
    latitud:     float
    longitud:    float
    precision_m: float   # estimated error radius in meters
    delta_n_m:   float   # northing offset from drone in meters
    delta_e_m:   float   # easting offset from drone in meters
    angulo_nadir_deg: float  # angle from nadir to target
    
    def __str__(self):
        return (f"GPS({self.latitud:.7f}, {self.longitud:.7f}) "
                f"±{self.precision_m:.1f}m  offset=N{self.delta_n_m:+.1f}m E{self.delta_e_m:+.1f}m")


class GeolocalizadorObjetivos:
    """
    Calcula coordenadas GPS de objetivos detectados en el frame de video.
    
    Implementa el modelo pinhole camera + ray-ground intersection.
    Válido para ángulos de gimbal entre -45° y -90° (desde oblicuo hasta nadir).
    """
    
    def __init__(self, fov_h_deg: float = 84.0, fov_v_deg: float = 48.0,
                 res_w: int = 3840, res_h: int = 2160):
        # Camera parameters
        self.fov_h = math.radians(fov_h_deg)
        self.fov_v = math.radians(fov_v_deg)
        self.res_w = res_w
        self.res_h = res_h
        # Focal length in pixels (pinhole model)
        self.f_px_h = res_w / (2 * math.tan(self.fov_h / 2))
        self.f_px_v = res_h / (2 * math.tan(self.fov_v / 2))
    
    def calcular(self,
                 lat_dron: float, lon_dron: float, alt_agl_m: float,
                 gimbal_pitch_deg: float,
                 yaw_dron_deg: float,
                 px_objetivo: int, py_objetivo: int) -> Optional[ResultadoGeolocacion]:
        """
        Calcula la posición GPS del objetivo.
        
        Args:
            lat_dron: Latitud del dron en grados decimales
            lon_dron: Longitud del dron en grados decimales
            alt_agl_m: Altitud del dron sobre el suelo en metros
            gimbal_pitch_deg: Ángulo del gimbal en grados (-90=nadir, 0=horizontal)
            yaw_dron_deg: Rumbo magnético del dron (0=Norte, 90=Este)
            px_objetivo: Coordenada X del objetivo en píxeles
            py_objetivo: Coordenada Y del objetivo en píxeles
        
        Returns:
            ResultadoGeolocacion o None si no es calculable
        """
        # Validate inputs
        if alt_agl_m <= 0.5:
            return None  # Altitude too low to compute reliably
        if gimbal_pitch_deg > -5:
            return None  # Camera nearly horizontal — ray may not hit ground
        
        # Step 1: Convert pixel offset from image center to angles (radians)
        # Image center coordinates
        cx = self.res_w / 2.0
        cy = self.res_h / 2.0
        # Pixel offsets (positive X = right, positive Y = down in image)
        dx_px = px_objetivo - cx
        dy_px = py_objetivo - cy  # positive = lower in frame = farther from drone
        
        # Angular offset from boresight
        theta_x = math.atan(dx_px / self.f_px_h)  # horizontal angle offset
        theta_y = math.atan(dy_px / self.f_px_v)   # vertical angle offset
        
        # Step 2: Build the look-ray in camera frame then rotate to NED.
        #
        # Camera frame convention (body-fixed to gimbal):
        #   cam_x = right   (positive = image right)
        #   cam_y = forward (boresight at zero offset)
        #   cam_z = up      (positive = image top)
        #
        # A pixel at (dx_px, dy_px) from the image centre corresponds to a unit
        # ray in camera frame:
        #   ray_cam = ( sin(theta_x),  cos(theta_x)*cos(theta_y), -cos(theta_x)*sin(theta_y) )
        # (normalised; the minus on z because image-Y-down maps to cam-Z-down = negative cam_z)
        pitch_cam_rad = math.radians(gimbal_pitch_deg)  # -π/2 = straight down
        yaw_rad       = math.radians(yaw_dron_deg)

        # Ray components in camera frame (unit vector):
        ray_cx =  math.sin(theta_x)
        ray_cy =  math.cos(theta_x) * math.cos(theta_y)   # forward component
        ray_cz = -math.cos(theta_x) * math.sin(theta_y)   # up component (negative = downward pixel)

        # Rotate camera frame → gimbal frame by gimbal pitch (rotation about cam_x axis).
        # Pitch rotation matrix (right-hand, positive = nose up):
        #   [1,      0,           0      ]
        #   [0,  cos(p),     -sin(p)     ]
        #   [0,  sin(p),      cos(p)     ]
        # After rotation, gimbal_y points toward the ground when pitch = -90°.
        cp = math.cos(pitch_cam_rad)
        sp = math.sin(pitch_cam_rad)
        ray_gx =  ray_cx
        ray_gy =  cp * ray_cy - sp * ray_cz
        ray_gz =  sp * ray_cy + cp * ray_cz

        # Map gimbal frame → NED frame:
        #   gimbal_x → East  (E)
        #   gimbal_y → North (N)
        #   gimbal_z → Up    (−D, so Down = −gimbal_z)
        # Therefore the Down (D) component of the ray in NED is −ray_gz.
        ray_ned_n =  ray_gy   # North
        ray_ned_e =  ray_gx   # East
        ray_ned_d = -ray_gz   # Down (positive = toward ground)

        # The Down component must be positive for the ray to intersect the ground.
        if ray_ned_d <= 0:
            return None  # Ray points upward, won't intersect ground

        # Step 3: Scale factor — how far along the ray to reach the ground plane.
        # Ground is at Down = alt_agl_m in NED (flat-earth assumption).
        scale = alt_agl_m / ray_ned_d

        # Step 4: Ground offset in camera-forward NED frame (before drone yaw rotation).
        # These are offsets in the drone-body NED frame (yaw = 0 means nose = North).
        forward_m = ray_ned_n * scale   # forward (North when yaw=0)
        right_m   = ray_ned_e * scale   # right   (East  when yaw=0)
        
        # Rotate by drone yaw to convert body-frame offsets to true NED offsets.
        # Standard 2-D yaw rotation (clockwise positive, 0 = North):
        delta_n_m = forward_m * math.cos(yaw_rad) - right_m * math.sin(yaw_rad)
        delta_e_m = forward_m * math.sin(yaw_rad) + right_m * math.cos(yaw_rad)
        
        # Step 5: Convert meter offsets to lat/lon deltas
        # 1 degree latitude ≈ 111,320 m (constant)
        # 1 degree longitude ≈ 111,320 * cos(lat) m
        delta_lat = delta_n_m / 111_320.0
        delta_lon = delta_e_m / (111_320.0 * math.cos(math.radians(lat_dron)))
        
        lat_objetivo = lat_dron + delta_lat
        lon_objetivo = lon_dron + delta_lon
        
        # Step 6: Estimate accuracy (function of altitude and gimbal angle)
        # Higher altitude = larger pixel footprint = less accurate
        angulo_nadir = abs(gimbal_pitch_deg + 90)  # 0 = pure nadir
        # GSD (Ground Sample Distance) in meters/pixel
        gsd_h = (2 * alt_agl_m * math.tan(self.fov_h / 2)) / self.res_w
        precision_m = gsd_h * 5  # ~5 pixel uncertainty footprint
        
        return ResultadoGeolocacion(
            latitud=lat_objetivo,
            longitud=lon_objetivo,
            precision_m=precision_m,
            delta_n_m=delta_n_m,
            delta_e_m=delta_e_m,
            angulo_nadir_deg=angulo_nadir
        )
    
    @staticmethod
    def distancia_haversine(lat1: float, lon1: float,
                             lat2: float, lon2: float) -> float:
        """Calcula la distancia en metros entre dos coordenadas GPS (Haversine)."""
        R = EARTH_RADIUS_M
        phi1, phi2 = math.radians(lat1), math.radians(lat2)
        dphi = math.radians(lat2 - lat1)
        dlam = math.radians(lon2 - lon1)
        a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlam/2)**2
        return 2 * R * math.asin(math.sqrt(a))
    
    @staticmethod
    def rumbo_entre_puntos(lat1: float, lon1: float,
                           lat2: float, lon2: float) -> float:
        """Calcula el rumbo (bearing) en grados de lat1/lon1 a lat2/lon2."""
        phi1, phi2 = math.radians(lat1), math.radians(lat2)
        dlam = math.radians(lon2 - lon1)
        x = math.sin(dlam) * math.cos(phi2)
        y = math.cos(phi1)*math.sin(phi2) - math.sin(phi1)*math.cos(phi2)*math.cos(dlam)
        bearing = math.degrees(math.atan2(x, y))
        return (bearing + 360) % 360
    
    @staticmethod
    def desplazar_punto(lat: float, lon: float,
                        distancia_m: float, rumbo_deg: float) -> Tuple[float, float]:
        """
        Desplaza un punto GPS una distancia dada en una dirección.
        Útil para generar waypoints de patrullaje alrededor de un objetivo.
        """
        R = EARTH_RADIUS_M
        d = distancia_m / R
        theta = math.radians(rumbo_deg)
        phi1  = math.radians(lat)
        lam1  = math.radians(lon)
        phi2  = math.asin(math.sin(phi1)*math.cos(d) +
                          math.cos(phi1)*math.sin(d)*math.cos(theta))
        lam2  = lam1 + math.atan2(math.sin(theta)*math.sin(d)*math.cos(phi1),
                                   math.cos(d) - math.sin(phi1)*math.sin(phi2))
        return math.degrees(phi2), math.degrees(lam2)


# ─── Self-test ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    geo = GeolocalizadorObjetivos(fov_h_deg=84, fov_v_deg=48, res_w=3840, res_h=2160)
    
    # Scenario: drone at 50m AGL, looking straight down (nadir), target at image center
    result = geo.calcular(
        lat_dron=4.710989, lon_dron=-74.072092, alt_agl_m=50.0,
        gimbal_pitch_deg=-90.0, yaw_dron_deg=0.0,
        px_objetivo=1920, py_objetivo=1080  # center of frame
    )
    print(f"Centro de frame (debe ser posición del dron):")
    print(f"  {result}")
    
    # Target 500 pixels to the right of center
    result2 = geo.calcular(
        lat_dron=4.710989, lon_dron=-74.072092, alt_agl_m=50.0,
        gimbal_pitch_deg=-90.0, yaw_dron_deg=0.0,
        px_objetivo=2420, py_objetivo=1080  # 500px right
    )
    print(f"\nObjetivo 500px a la derecha (Norte=0, debe ser al Este):")
    print(f"  {result2}")
