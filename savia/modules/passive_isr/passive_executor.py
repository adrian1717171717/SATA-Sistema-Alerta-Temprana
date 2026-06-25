"""
S.A.V.I.A. — MÓDULO PASIVO ISR (Tier 1)
=========================================
Implementación de MisionExecutor para drones comerciales SIN SDK libre.
El operador vuela manualmente. El software se enfoca 100% en análisis.

Capacidades:
  ✓ Recepción de video (RTSP / captura de pantalla / archivo)
  ✓ Detección de objetivos con YOLO (bounding boxes, clases tácticas)
  ✓ Captura automática de fotogramas al detectar amenaza
  ✓ Log CSV SALUTE de todas las detecciones
  ✓ Reporte PDF post-vuelo

  ✗ Telemetría GPS (sin SDK)
  ✗ Control de vuelo
  ✗ Geolocalización de objetivos
  ✗ Loiter autónomo
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

from core.mission_executor import MisionExecutor
from core.data_models import (
    ConfigMision, Waypoint, TelemetriaFrame,
    ObjetivoDetectado, EstadoMision, NivelAmenaza
)

try:
    from ultralytics import YOLO
    YOLO_OK = True
except ImportError:
    YOLO_OK = False
    print("[!] ultralytics no instalado. Detección IA deshabilitada.")


# Mapa de clases a nivel de amenaza (personalizar según el modelo entrenado)
_NIVEL_AMENAZA_CLASES = {
    "Militar_Jaguar":   NivelAmenaza.CRITICA,
    "Vehiculo_Tactico": NivelAmenaza.ALTA,
    "Vehiculo_Civil":   NivelAmenaza.MEDIA,
    "Civil":            NivelAmenaza.BAJA,
    # COCO fallback
    "person":           NivelAmenaza.BAJA,
    "car":              NivelAmenaza.BAJA,
    "truck":            NivelAmenaza.MEDIA,
}


class SaviaPassivo(MisionExecutor):
    """
    Ejecutor Tier 1 — Solo análisis ISR sin control de vuelo.
    El operador vuela el dron manualmente; el software analiza el video.
    """

    TIER = "PASIVO"

    def __init__(self, config: ConfigMision):
        super().__init__(config)
        self._modelo_ia: Optional[object] = None
        self._cap:       Optional[cv2.VideoCapture] = None
        self._hilo_video: Optional[threading.Thread] = None
        self._corriendo   = False
        self._frame_actual = None
        self._frame_lock   = threading.Lock()
        self._cooldown_captura = 15.0   # segundos mínimos entre capturas
        self._ultima_captura   = 0.0
        self._carpeta_evidencia = "Evidencia_Seguridad"
        os.makedirs(self._carpeta_evidencia, exist_ok=True)

        # Cargar modelo IA
        if YOLO_OK:
            try:
                self._modelo_ia = YOLO(config.modelo_ia)
                print(f"[+] Savia PASIVO: modelo '{config.modelo_ia}' cargado.")
            except Exception as e:
                print(f"[!] No se pudo cargar el modelo: {e}")

    # ─── Ciclo de vida ────────────────────────────────────────────────────────

    def iniciar(self, fuente_video, waypoints: List[Waypoint]) -> None:
        """
        Inicia el análisis de video. Los waypoints se ignoran en el Tier Pasivo
        (el operador vuela manualmente), pero se registran para el reporte.
        """
        self._waypoints_ref = waypoints
        self._corriendo     = True
        self._emitir_estado(EstadoMision.EN_EJECUCION)

        # Abrir fuente de video
        if isinstance(fuente_video, str):
            self._cap = cv2.VideoCapture(fuente_video)
        else:
            self._cap = cv2.VideoCapture(int(fuente_video))

        if not self._cap.isOpened():
            self._emitir_estado(EstadoMision.ABORTADA)
            raise RuntimeError(f"No se pudo abrir la fuente de video: {fuente_video}")

        # Hilo de captura de frames
        self._hilo_video = threading.Thread(
            target=self._bucle_video, daemon=True, name="SaviaPassivo-Video"
        )
        self._hilo_video.start()
        print(f"[+] Savia PASIVO: análisis ISR iniciado — fuente: {fuente_video}")

    def detener(self) -> None:
        self._corriendo = False
        if self._hilo_video:
            self._hilo_video.join(timeout=3.0)
        if self._cap:
            self._cap.release()
        self._emitir_estado(EstadoMision.COMPLETADA)
        print("[+] Savia PASIVO: misión detenida.")

    def pausar(self) -> None:
        self._corriendo = False
        self._emitir_estado(EstadoMision.PAUSADA)

    def reanudar(self) -> None:
        self._corriendo = True
        self._emitir_estado(EstadoMision.EN_EJECUCION)
        self._hilo_video = threading.Thread(
            target=self._bucle_video, daemon=True, name="SaviaPassivo-Video"
        )
        self._hilo_video.start()

    # ─── Visión Artificial ────────────────────────────────────────────────────

    def procesar_frame(self, frame) -> List[ObjetivoDetectado]:
        """Ejecuta la inferencia YOLO sobre el frame y retorna las detecciones."""
        if not self._modelo_ia or frame is None:
            return []

        resultados = self._modelo_ia.predict(
            frame,
            conf=self._config.sensibilidad_ia,
            verbose=False,
            half=False   # FP32 en CPU (Tier Pasivo puede no tener GPU)
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

                objetivo = ObjetivoDetectado(
                    id_objetivo   = str(uuid.uuid4())[:8],
                    clase         = clase_nom,
                    confianza     = conf,
                    nivel_amenaza = _NIVEL_AMENAZA_CLASES.get(clase_nom, NivelAmenaza.BAJA),
                    bbox_x1=x1, bbox_y1=y1, bbox_x2=x2, bbox_y2=y2,
                    frame_numero  = 0,
                    altitud_dron  = 0.0   # Sin telemetría en Tier Pasivo
                )
                detectados.append(objetivo)

        return detectados

    def capturar_objetivo(self, objetivo: ObjetivoDetectado) -> str:
        """Guarda un JPG del frame actual con las coordenadas del objetivo marcadas."""
        with self._frame_lock:
            frame = self._frame_actual.copy() if self._frame_actual is not None else None

        if frame is None:
            return ""

        ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
        nombre = f"ALERTA_{ts}_{objetivo.clase}.jpg"
        ruta   = os.path.join(self._carpeta_evidencia, nombre)

        # Dibujar bounding box en la captura
        color = (0, 0, 255) if objetivo.nivel_amenaza.value >= 3 else (0, 200, 50)
        cv2.rectangle(frame,
                      (objetivo.bbox_x1, objetivo.bbox_y1),
                      (objetivo.bbox_x2, objetivo.bbox_y2), color, 2)
        cv2.putText(frame, f"{objetivo.clase} {objetivo.confianza:.0%}",
                    (objetivo.bbox_x1, max(objetivo.bbox_y1 - 8, 15)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

        cv2.imwrite(ruta, frame)
        objetivo.ruta_captura = ruta

        # Registrar en CSV SALUTE
        self._registrar_csv(objetivo, nombre)
        print(f"[!] Captura guardada: {ruta}")
        return ruta

    def generar_reporte_postflight(self) -> str:
        """Genera el reporte PDF de inteligencia post-vuelo."""
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
            "telemetria":        False,
            "control_vuelo":     False,
            "geolocalizacion":   False,
            "loiter_autonomo":   False,
            "failsafe_tactico":  False,
            "vision_artificial": YOLO_OK,
            "reporte_pdf":       True,
        }

    # ─── Internos ─────────────────────────────────────────────────────────────

    def _bucle_video(self):
        """Hilo de lectura de frames y análisis continuo."""
        while self._corriendo:
            ok, frame = self._cap.read()
            if not ok:
                time.sleep(0.05)
                continue

            with self._frame_lock:
                self._frame_actual = frame.copy()

            # Inferencia (cada frame en Pasivo — sin presión de telemetría)
            detecciones = self.procesar_frame(frame)

            for obj in detecciones:
                # Auto-captura si la amenaza es suficientemente alta
                if (obj.nivel_amenaza.value >= NivelAmenaza.ALTA.value and
                        time.time() - self._ultima_captura > self._cooldown_captura):
                    self._objetivos.append(obj)
                    self.capturar_objetivo(obj)
                    self._ultima_captura = time.time()
                    self._emitir_alerta(obj)

    def _registrar_csv(self, obj: ObjetivoDetectado, nombre_foto: str):
        """Registra la detección en el CSV SALUTE estándar."""
        csv_path = os.path.join(self._carpeta_evidencia, "registro_novedades.csv")
        existe   = os.path.exists(csv_path)
        fh       = datetime.now()
        with open(csv_path, "a", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            if not existe:
                w.writerow(["Archivo_Imagen", "Fecha", "Hora", "Size",
                            "Activity", "Location", "Unit", "Equipment"])
            w.writerow([
                nombre_foto,
                fh.strftime("%Y-%m-%d"),
                fh.strftime("%H:%M:%S"),
                1,
                f"Deteccion: {obj.clase} ({obj.confianza:.0%})",
                "N/A - Sin Telemetria",
                obj.clase,
                f"Savia PASIVO | {self._config.modelo_ia}",
            ])
