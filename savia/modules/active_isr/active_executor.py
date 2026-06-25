"""
S.A.V.I.A. — EJECUTOR ACTIVO ISR (Tier 2)
==========================================
Implementación de MisionExecutorActivo para drones con SDK libre,
PX4/ArduPilot vía MAVLink, o DJI con SDK habilitado.

Extiende todas las capacidades del Tier Pasivo añadiendo:
  ✓ Telemetría GPS/IMU en tiempo real (MAVSDK / pymavlink)
  ✓ Carga y ejecución de misiones autónomas (lista de Waypoints)
  ✓ Geolocalización de objetivos (trigonometría + altitud + FOV)
  ✓ Loiter on Target: órbita autónoma sobre objetivo detectado
  ✓ Failsafe Táctico: RTB por Bingo Fuel, Jamming o Geofence
"""
from __future__ import annotations
import cv2
import os
import csv
import threading
import time
import uuid
from datetime import datetime
from typing import List, Optional

from core.mission_executor import MisionExecutorActivo
from core.data_models import (
    ConfigMision, Waypoint, TelemetriaFrame,
    ObjetivoDetectado, EstadoMision, NivelAmenaza, CausaFailsafe
)
from core.target_geolocator import GeolocalizadorObjetivos
from .failsafe_manager import GestorFailsafe

try:
    from ultralytics import YOLO
    import torch
    YOLO_OK = True
    CUDA_OK = torch.cuda.is_available()
except ImportError:
    YOLO_OK = False
    CUDA_OK = False

# Intentar importar MAVSDK (puede no estar instalado)
try:
    import asyncio
    import mavsdk
    from mavsdk import System as MavSystem
    from mavsdk.mission import MissionItem, MissionPlan
    MAVSDK_OK = True
except ImportError:
    MAVSDK_OK = False
    print("[!] mavsdk no instalado. Control de vuelo deshabilitado.")

# Intentar pymavlink como alternativa
try:
    from pymavlink import mavutil
    PYMAVLINK_OK = True
except ImportError:
    PYMAVLINK_OK = False

# Nivel de amenaza mínimo para activar Loiter on Target automáticamente
UMBRAL_LOITER_AUTO = NivelAmenaza.CRITICA

# Nivel de amenaza mínimo para captura automática de fotograma
UMBRAL_CAPTURA = NivelAmenaza.ALTA

# Mapa de clases a nivel de amenaza
_NIVEL_AMENAZA = {
    "Militar_Jaguar":   NivelAmenaza.CRITICA,
    "Vehiculo_Tactico": NivelAmenaza.ALTA,
    "Vehiculo_Civil":   NivelAmenaza.MEDIA,
    "Civil":            NivelAmenaza.BAJA,
    "person":           NivelAmenaza.BAJA,
    "car":              NivelAmenaza.BAJA,
    "truck":            NivelAmenaza.MEDIA,
}


class SaviaActivo(MisionExecutorActivo):
    """
    Ejecutor Tier 2 — Control completo del dron + Análisis ISR.

    Arquitectura de hilos:
      Thread-1: Bucle de video (captura + YOLO)
      Thread-2: Bucle de telemetría (MAVLink polling)
      Thread-3: Bucle de failsafe (monitoreo de condiciones críticas)
      Thread-4: Bucle de misión (envío secuencial de WPs si modo manual WP)
    """

    TIER = "ACTIVO"

    def __init__(self, config: ConfigMision, conexion_mavlink: str):
        super().__init__(config)
        self._conexion    = conexion_mavlink
        self._modelo_ia:  Optional[object] = None
        self._cap:        Optional[cv2.VideoCapture] = None
        self._corriendo   = False
        self._frame_actual = None
        self._frame_lock   = threading.Lock()
        self._tele_lock    = threading.Lock()
        self._cooldown_captura = 10.0
        self._ultima_captura   = 0.0
        self._carpeta          = "Evidencia_Seguridad"
        os.makedirs(self._carpeta, exist_ok=True)
        self._geolocalizador = GeolocalizadorObjetivos(
            fov_h_deg=config.camara.fov_horizontal,
            fov_v_deg=config.camara.fov_vertical,
            res_w=config.camara.resolucion_w,
            res_h=config.camara.resolucion_h
        )

        # MAVLink connection handle (pymavlink)
        self._mav: Optional[object] = None
        self._loiter_activo = False
        self._wp_actual_idx = 0

        # Failsafe táctico
        self._failsafe = GestorFailsafe(config, self._on_failsafe)

        # Cargar modelo IA
        if YOLO_OK:
            try:
                self._modelo_ia = YOLO(config.modelo_ia)
                dispositivo = "cuda" if CUDA_OK else "cpu"
                if CUDA_OK:
                    self._modelo_ia.to("cuda")
                print(f"[+] Savia ACTIVO: modelo '{config.modelo_ia}' en {dispositivo}.")
            except Exception as e:
                print(f"[!] No se pudo cargar el modelo: {e}")

        # Conectar MAVLink
        self._conectar_mavlink()

    # ─── Ciclo de vida ────────────────────────────────────────────────────────

    def iniciar(self, fuente_video, waypoints: List[Waypoint]) -> None:
        self._waypoints_mision = list(waypoints)
        self._corriendo        = True
        self._wp_actual_idx    = 0
        self._emitir_estado(EstadoMision.EN_EJECUCION)

        # Abrir video
        self._cap = cv2.VideoCapture(
            fuente_video if isinstance(fuente_video, str) else int(fuente_video)
        )
        if not self._cap.isOpened():
            self._emitir_estado(EstadoMision.ABORTADA)
            raise RuntimeError(f"No se pudo abrir fuente de video: {fuente_video}")

        # Cargar misión en controladora de vuelo
        if waypoints and self._mav:
            self.cargar_mision_completa(waypoints)

        # Iniciar hilos
        threading.Thread(target=self._bucle_video,     daemon=True, name="Activo-Video").start()
        threading.Thread(target=self._bucle_telemetria, daemon=True, name="Activo-Tele").start()
        self._failsafe.iniciar()

        print(f"[+] Savia ACTIVO: misión iniciada — {len(waypoints)} waypoints cargados.")

    def detener(self) -> None:
        self._corriendo = False
        self._failsafe.detener()
        if self._cap:
            self._cap.release()
        self._emitir_estado(EstadoMision.COMPLETADA)
        print("[+] Savia ACTIVO: misión detenida.")

    def pausar(self) -> None:
        """Pausa la misión — envía comando HOLD a la controladora."""
        self._corriendo = False
        if self._mav and PYMAVLINK_OK:
            try:
                # MAVLink: HOLD mode (depende del firmware)
                self._mav.mav.command_long_send(
                    self._mav.target_system,
                    self._mav.target_component,
                    mavutil.mavlink.MAV_CMD_DO_PAUSE_CONTINUE,
                    0, 0, 0, 0, 0, 0, 0, 0
                )
            except Exception as e:
                print(f"[!] Error enviando HOLD: {e}")
        self._emitir_estado(EstadoMision.PAUSADA)

    def reanudar(self) -> None:
        self._corriendo = True
        self._emitir_estado(EstadoMision.EN_EJECUCION)
        threading.Thread(target=self._bucle_video, daemon=True).start()

    # ─── Telemetría MAVLink ───────────────────────────────────────────────────

    def actualizar_telemetria(self) -> TelemetriaFrame:
        """Lee la última trama disponible de MAVLink (non-blocking)."""
        with self._tele_lock:
            return self._telemetria or TelemetriaFrame()

    def _bucle_telemetria(self) -> None:
        """Hilo continuo de lectura de telemetría vía pymavlink."""
        if not PYMAVLINK_OK or not self._mav:
            print("[!] Sin MAVLink — bucle de telemetría inactivo.")
            return

        while self._corriendo:
            try:
                msg = self._mav.recv_match(blocking=True, timeout=1.0)
                if not msg:
                    continue

                tipo = msg.get_type()

                with self._tele_lock:
                    if self._telemetria is None:
                        self._telemetria = TelemetriaFrame()
                    t = self._telemetria

                    if tipo == "GLOBAL_POSITION_INT":
                        t.latitud      = msg.lat / 1e7
                        t.longitud     = msg.lon / 1e7
                        t.altitud_rel  = msg.relative_alt / 1000.0  # mm → m
                        t.altitud_abs  = msg.alt / 1000.0
                    elif tipo == "ATTITUDE":
                        t.roll  = msg.roll  * 57.2958   # rad → deg
                        t.pitch = msg.pitch * 57.2958
                        t.yaw   = (msg.yaw  * 57.2958) % 360
                    elif tipo == "SYS_STATUS":
                        t.bateria_pct = msg.battery_remaining  # 0–100
                        t.bateria_v   = msg.voltage_battery / 1000.0  # mV → V
                    elif tipo == "RC_CHANNELS":
                        t.rssi = msg.rssi - 200  # Convertir a dBm aprox
                    elif tipo == "GPS_RAW_INT":
                        t.satelites = msg.satellites_visible
                    elif tipo == "HEARTBEAT":
                        t.modo_vuelo  = str(msg.custom_mode)

                    t.timestamp = time.time()

                # Pasar trama al failsafe
                self._failsafe.actualizar_telemetria(self._telemetria)

            except Exception as e:
                time.sleep(0.1)

    # ─── Control de vuelo ─────────────────────────────────────────────────────

    def enviar_waypoint(self, wp: Waypoint) -> bool:
        """Envía un Waypoint individual a la controladora (modo override)."""
        if not self._mav or not PYMAVLINK_OK:
            return False
        try:
            self._mav.mav.mission_item_int_send(
                self._mav.target_system,
                self._mav.target_component,
                0,                                      # seq
                mavutil.mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT,
                mavutil.mavlink.MAV_CMD_NAV_WAYPOINT,
                2,                                      # current = 2 (guided mode WP)
                1,                                      # autocontinue
                0, 2.0, 0, float("nan"),                # params
                int(wp.latitud  * 1e7),
                int(wp.longitud * 1e7),
                wp.altitud
            )
            return True
        except Exception as e:
            print(f"[!] Error enviando waypoint: {e}")
            return False

    def cargar_mision_completa(self, waypoints: List[Waypoint]) -> bool:
        """
        Carga la lista completa de waypoints en la memoria de misión de la
        controladora de vuelo. Proceso:
          1. MISSION_CLEAR_ALL
          2. MISSION_COUNT
          3. MISSION_ITEM_INT * n
          4. Esperar MISSION_ACK
        """
        if not self._mav or not PYMAVLINK_OK:
            return False
        try:
            # Limpiar misión anterior
            self._mav.mav.mission_clear_all_send(
                self._mav.target_system, self._mav.target_component
            )
            time.sleep(0.2)

            # Enviar cantidad de items
            self._mav.mav.mission_count_send(
                self._mav.target_system, self._mav.target_component, len(waypoints)
            )
            time.sleep(0.1)

            # Enviar cada waypoint
            for i, wp in enumerate(waypoints):
                self._mav.mav.mission_item_int_send(
                    self._mav.target_system,
                    self._mav.target_component,
                    i,
                    mavutil.mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT,
                    mavutil.mavlink.MAV_CMD_NAV_WAYPOINT,
                    1 if i == 0 else 0,  # current
                    1,                   # autocontinue
                    0, 2.0, 0, float("nan"),
                    int(wp.latitud  * 1e7),
                    int(wp.longitud * 1e7),
                    wp.altitud
                )
                time.sleep(0.05)

            print(f"[+] Misión cargada: {len(waypoints)} waypoints.")
            return True
        except Exception as e:
            print(f"[!] Error cargando misión: {e}")
            return False

    def activar_loiter_objetivo(self, objetivo: ObjetivoDetectado) -> bool:
        """
        LOITER ON TARGET: interrumpe la misión y orbita sobre el objetivo.
        Calcula las coordenadas GPS del objetivo y envía el comando de loiter.
        """
        if not objetivo.tiene_gps:
            print("[!] Loiter: objetivo sin coordenadas GPS calculadas.")
            return False

        if not self._mav or not PYMAVLINK_OK:
            return False

        try:
            self._loiter_activo = True
            # Comando: Loiter indefinido sobre las coordenadas del objetivo
            self._mav.mav.command_long_send(
                self._mav.target_system,
                self._mav.target_component,
                mavutil.mavlink.MAV_CMD_NAV_LOITER_UNLIM,
                0,                          # confirmation
                0,                          # param1 (unused)
                0,                          # param2 (unused)
                self._config.loiter_radio,  # param3: radio
                0,                          # param4: yaw
                int(objetivo.lat_objetivo * 1e7),
                int(objetivo.lon_objetivo * 1e7),
                self._telemetria.altitud_rel if self._telemetria else 40.0
            )
            print(f"[+] LOITER ACTIVADO sobre {objetivo}")
            return True
        except Exception as e:
            print(f"[!] Error activando loiter: {e}")
            return False

    def activar_rtb(self, causa: CausaFailsafe) -> bool:
        """
        Activa el protocolo de Return To Base (Failsafe Táctico).
        Envía MAV_CMD_NAV_RETURN_TO_LAUNCH a la controladora.
        """
        if not self._mav or not PYMAVLINK_OK:
            return False
        try:
            self._mav.mav.command_long_send(
                self._mav.target_system,
                self._mav.target_component,
                mavutil.mavlink.MAV_CMD_NAV_RETURN_TO_LAUNCH,
                0, 0, 0, 0, 0, 0, 0, 0
            )
            self._emitir_estado(EstadoMision.RTB)
            print(f"[!!!] RTB ACTIVADO — Causa: {causa.name}")
            return True
        except Exception as e:
            print(f"[!] Error enviando RTB: {e}")
            return False

    # ─── Visión Artificial con Geolocalización ────────────────────────────────

    def procesar_frame(self, frame) -> List[ObjetivoDetectado]:
        """
        Ejecuta YOLO y, para cada detección, calcula sus coordenadas GPS
        usando la telemetría actual y el GeolocalizadorObjetivos.
        """
        if not self._modelo_ia or frame is None:
            return []

        tele = self.actualizar_telemetria()
        dev  = 0 if CUDA_OK else "cpu"

        resultados = self._modelo_ia.predict(
            frame, conf=self._config.sensibilidad_ia,
            verbose=False, device=dev, half=CUDA_OK
        )

        detectados: List[ObjetivoDetectado] = []
        for r in resultados:
            if not r.boxes:
                continue
            for box in r.boxes:
                clase_id  = int(box.cls[0])
                clase_nom = self._modelo_ia.names.get(clase_id, f"cls_{clase_id}")
                conf      = float(box.conf[0])
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                cx, cy = (x1 + x2) // 2, (y1 + y2) // 2

                # ── Geolocalización del objetivo ──────────────────────────────
                geo = None
                if tele.altitud_rel > 2.0 and tele.gps_valido:
                    geo = self._geolocalizador.calcular(
                        lat_dron=tele.latitud,
                        lon_dron=tele.longitud,
                        alt_agl_m=tele.altitud_rel,
                        gimbal_pitch_deg=tele.gimbal_pitch,
                        yaw_dron_deg=tele.yaw,
                        px_objetivo=cx,
                        py_objetivo=cy
                    )

                objetivo = ObjetivoDetectado(
                    id_objetivo   = str(uuid.uuid4())[:8],
                    clase         = clase_nom,
                    confianza     = conf,
                    nivel_amenaza = _NIVEL_AMENAZA.get(clase_nom, NivelAmenaza.BAJA),
                    bbox_x1=x1, bbox_y1=y1, bbox_x2=x2, bbox_y2=y2,
                    lat_objetivo  = geo.latitud     if geo else None,
                    lon_objetivo  = geo.longitud    if geo else None,
                    precision_m   = geo.precision_m if geo else None,
                    altitud_dron  = tele.altitud_rel
                )
                detectados.append(objetivo)

        return detectados

    def capturar_objetivo(self, objetivo: ObjetivoDetectado) -> str:
        """Captura el frame actual, anota las coordenadas GPS y guarda el JPG."""
        with self._frame_lock:
            frame = self._frame_actual.copy() if self._frame_actual is not None else None
        if frame is None:
            return ""

        ts     = datetime.now().strftime("%Y%m%d_%H%M%S")
        nombre = f"ALERTA_{ts}_{objetivo.clase}.jpg"
        ruta   = os.path.join(self._carpeta, nombre)

        color = (0, 0, 255) if objetivo.nivel_amenaza.value >= 3 else (0, 200, 50)
        cv2.rectangle(frame,
                      (objetivo.bbox_x1, objetivo.bbox_y1),
                      (objetivo.bbox_x2, objetivo.bbox_y2), color, 2)
        # Mostrar coords GPS si disponibles
        gps_str = (f"GPS:{objetivo.lat_objetivo:.6f},{objetivo.lon_objetivo:.6f}"
                   if objetivo.tiene_gps else "GPS:N/A")
        label = f"{objetivo.clase} {objetivo.confianza:.0%} | {gps_str}"
        cv2.putText(frame, label,
                    (objetivo.bbox_x1, max(objetivo.bbox_y1 - 8, 15)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)

        cv2.imwrite(ruta, frame)
        objetivo.ruta_captura = ruta
        self._registrar_csv(objetivo, nombre)
        print(f"[!] Captura: {ruta} | {objetivo}")
        return ruta

    def generar_reporte_postflight(self) -> str:
        try:
            import reporteador
            return reporteador.generar_reporte()
        except Exception as e:
            print(f"[!] Error generando reporte: {e}")
            return ""

    # ─── Propiedades ──────────────────────────────────────────────────────────

    @property
    def tier(self) -> str:
        return self.TIER

    @property
    def capacidades(self) -> dict:
        return {
            "telemetria":        PYMAVLINK_OK,
            "control_vuelo":     PYMAVLINK_OK and self._mav is not None,
            "geolocalizacion":   True,
            "loiter_autonomo":   PYMAVLINK_OK and self._mav is not None,
            "failsafe_tactico":  True,
            "vision_artificial": YOLO_OK,
            "reporte_pdf":       True,
        }

    # ─── Internos ─────────────────────────────────────────────────────────────

    def _conectar_mavlink(self) -> None:
        """Establece la conexión MAVLink con la controladora de vuelo."""
        if not PYMAVLINK_OK:
            return
        try:
            self._mav = mavutil.mavlink_connection(self._conexion)
            self._mav.wait_heartbeat(timeout=5)
            print(f"[+] MAVLink conectado: {self._conexion} "
                  f"(sys={self._mav.target_system}, comp={self._mav.target_component})")
        except Exception as e:
            print(f"[!] No se pudo conectar MAVLink ({self._conexion}): {e}")
            self._mav = None

    def _bucle_video(self) -> None:
        """Hilo de captura de frames y análisis IA continuo."""
        frame_cnt   = 0
        frame_skip  = 1 if CUDA_OK else 2  # Más agresivo en CPU

        while self._corriendo:
            ok, frame = self._cap.read()
            if not ok:
                time.sleep(0.05)
                continue

            with self._frame_lock:
                self._frame_actual = frame.copy()

            frame_cnt += 1
            if frame_cnt % (frame_skip + 1) != 0:
                continue

            detecciones = self.procesar_frame(frame)

            for obj in detecciones:
                if (obj.nivel_amenaza.value >= UMBRAL_CAPTURA.value and
                        time.time() - self._ultima_captura > self._cooldown_captura):
                    self._objetivos.append(obj)
                    self.capturar_objetivo(obj)
                    self._ultima_captura = time.time()
                    self._emitir_alerta(obj)

                    # Loiter on Target automático si amenaza CRÍTICA
                    if (obj.nivel_amenaza == NivelAmenaza.CRITICA and
                            not self._loiter_activo and obj.tiene_gps):
                        print(f"[!] AUTO-LOITER: amenaza crítica detectada — {obj.clase}")
                        self.activar_loiter_objetivo(obj)

    def _on_failsafe(self, causa: CausaFailsafe) -> None:
        """Callback del GestorFailsafe — activa RTB en la controladora."""
        self.activar_rtb(causa)

    def _registrar_csv(self, obj: ObjetivoDetectado, nombre_foto: str) -> None:
        """Registra la detección en el CSV SALUTE con coordenadas GPS."""
        csv_path = os.path.join(self._carpeta, "registro_novedades.csv")
        existe   = os.path.exists(csv_path)
        fh       = datetime.now()
        gps_str  = (f"LAT {obj.lat_objetivo:.6f}, LON {obj.lon_objetivo:.6f} "
                    f"(±{obj.precision_m:.1f}m)"
                    if obj.tiene_gps else "N/A - Sin geolocalización")
        with open(csv_path, "a", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            if not existe:
                w.writerow(["Archivo_Imagen", "Fecha", "Hora", "Size",
                            "Activity", "Location", "Unit", "Equipment"])
            w.writerow([
                nombre_foto, fh.strftime("%Y-%m-%d"), fh.strftime("%H:%M:%S"),
                1,
                f"Deteccion: {obj.clase} ({obj.confianza:.0%}) | {obj.nivel_amenaza.name}",
                gps_str,
                obj.clase,
                f"Savia ACTIVO | {self._config.modelo_ia} | CUDA={CUDA_OK}",
            ])
