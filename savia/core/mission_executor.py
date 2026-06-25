"""
S.A.V.I.A. — INTERFAZ BASE: EJECUTOR DE MISIÓN (Strategy Pattern)
==================================================================
Define el contrato que deben implementar SaviaPassivo y SaviaActivo.
El Planificador no sabe ni le importa cuál Tier está activo;
habla siempre con la misma interfaz MisionExecutor.

Patrón de diseño: Strategy
  - MisionExecutor    → Interfaz abstracta (el contrato)
  - SaviaPassivo      → Estrategia concreta Tier 1 (análisis ISR)
  - SaviaActivo       → Estrategia concreta Tier 2 (C2 autónomo)
"""
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import List, Optional, Callable
from .data_models import (
    ConfigMision, Waypoint, TelemetriaFrame,
    ObjetivoDetectado, EstadoMision, CausaFailsafe
)


class MisionExecutor(ABC):
    """
    Interfaz abstracta para la ejecución de misiones ISR.

    Toda la lógica de análisis (visión artificial, alertas) es común.
    La diferencia entre Tier 1 y Tier 2 está en si pueden enviar comandos
    de vuelo al dron o solo analizar el video recibido.
    """

    def __init__(self, config: ConfigMision):
        self._config     = config
        self._estado     = EstadoMision.LISTA
        self._objetivos  : List[ObjetivoDetectado] = []
        self._telemetria : Optional[TelemetriaFrame] = None
        self._cb_alerta  : Optional[Callable] = None   # callback nueva detección
        self._cb_estado  : Optional[Callable] = None   # callback cambio de estado

    # ─── Ciclo de vida ────────────────────────────────────────────────────────

    @abstractmethod
    def iniciar(self, fuente_video, waypoints: List[Waypoint]) -> None:
        """
        Inicia la ejecución de la misión.

        Args:
            fuente_video: Fuente de video (int para cámara USB,
                          str para RTSP/RTMP/ruta de archivo)
            waypoints:    Lista de Waypoints generada por el Planificador
        """
        ...

    @abstractmethod
    def detener(self) -> None:
        """Detiene la misión limpiamente y libera recursos."""
        ...

    @abstractmethod
    def pausar(self) -> None:
        """Pausa la misión (dron en hover si es Activo, análisis en pausa si Pasivo)."""
        ...

    @abstractmethod
    def reanudar(self) -> None:
        """Reanuda la misión desde el punto de pausa."""
        ...

    # ─── Capacidades de visión artificial (comunes a ambos Tiers) ────────────

    @abstractmethod
    def procesar_frame(self, frame) -> List[ObjetivoDetectado]:
        """
        Procesa un frame de video con el modelo de IA.

        Args:
            frame: np.ndarray BGR del frame actual

        Returns:
            Lista de objetivos detectados en este frame
        """
        ...

    @abstractmethod
    def capturar_objetivo(self, objetivo: ObjetivoDetectado) -> str:
        """
        Guarda un fotograma del objetivo y lo registra en el log SALUTE.

        Returns:
            Ruta al archivo guardado
        """
        ...

    @abstractmethod
    def generar_reporte_postflight(self) -> str:
        """
        Genera el reporte de inteligencia post-vuelo en PDF.

        Returns:
            Ruta al PDF generado
        """
        ...

    # ─── Callbacks de eventos ─────────────────────────────────────────────────

    def on_alerta(self, callback: Callable[[ObjetivoDetectado], None]) -> None:
        """Registra un callback que se llamará cuando se detecte una nueva amenaza."""
        self._cb_alerta = callback

    def on_cambio_estado(self, callback: Callable[[EstadoMision], None]) -> None:
        """Registra un callback para cambios de estado de la misión."""
        self._cb_estado = callback

    def _emitir_alerta(self, objetivo: ObjetivoDetectado) -> None:
        if self._cb_alerta:
            try:
                self._cb_alerta(objetivo)
            except Exception:
                pass

    def _emitir_estado(self, estado: EstadoMision) -> None:
        self._estado = estado
        if self._cb_estado:
            try:
                self._cb_estado(estado)
            except Exception:
                pass

    # ─── Propiedades de consulta ──────────────────────────────────────────────

    @property
    def estado(self) -> EstadoMision:
        return self._estado

    @property
    def objetivos(self) -> List[ObjetivoDetectado]:
        return list(self._objetivos)

    @property
    def telemetria(self) -> Optional[TelemetriaFrame]:
        return self._telemetria

    @property
    @abstractmethod
    def tier(self) -> str:
        """Retorna el Tier del ejecutor: 'PASIVO' o 'ACTIVO'."""
        ...

    @property
    @abstractmethod
    def capacidades(self) -> dict:
        """
        Diccionario de capacidades del ejecutor.

        Ejemplo:
            {
                'telemetria':    False,
                'control_vuelo': False,
                'geolocalizacion': False,
                'loiter':        False,
                'failsafe_tactico': False,
            }
        """
        ...


class MisionExecutorActivo(MisionExecutor):
    """
    Extensión de la interfaz para Tier 2 (Savia Activo).
    Agrega métodos de control de vuelo que solo existen en este Tier.
    """

    @abstractmethod
    def actualizar_telemetria(self) -> TelemetriaFrame:
        """Lee y retorna el último frame de telemetría del dron."""
        ...

    @abstractmethod
    def enviar_waypoint(self, wp: Waypoint) -> bool:
        """
        Envía un waypoint individual a la controladora de vuelo.

        Returns:
            True si el waypoint fue aceptado por la controladora.
        """
        ...

    @abstractmethod
    def cargar_mision_completa(self, waypoints: List[Waypoint]) -> bool:
        """
        Carga la misión completa (lista de WPs) en la controladora.

        Returns:
            True si la controladora confirmó la misión.
        """
        ...

    @abstractmethod
    def activar_loiter_objetivo(self, objetivo: ObjetivoDetectado) -> bool:
        """
        Interrumpe la misión actual e inicia órbita sobre el objetivo.

        Returns:
            True si el dron confirmó el cambio a modo Loiter.
        """
        ...

    @abstractmethod
    def activar_rtb(self, causa: CausaFailsafe) -> bool:
        """
        Activa el protocolo de Return To Base (Failsafe Táctico).

        Args:
            causa: Causa del RTB (batería, jamming, orden operador)

        Returns:
            True si el dron aceptó el comando RTB.
        """
        ...


# ─── Factory: selección automática del Tier ───────────────────────────────────

class SaviaFactory:
    """
    Factory que instancia el ejecutor correcto según la disponibilidad
    de SDK/MAVLink en el hardware conectado.

    Uso:
        executor = SaviaFactory.crear(config, intentar_activo=True)
    """

    @staticmethod
    def crear(config: ConfigMision,
              intentar_activo: bool = True,
              conexion_mavlink: Optional[str] = None
              ) -> MisionExecutor:
        """
        Crea el ejecutor de misión apropiado.

        Args:
            config:            Configuración de la misión
            intentar_activo:   Si True, intenta conectar con MAVLink primero
            conexion_mavlink:  URL de conexión (ej. "udp://:14540", "tcp:127.0.0.1:5760")

        Returns:
            Instancia de SaviaActivo o SaviaPassivo según disponibilidad
        """
        from modules.active_isr.active_executor import SaviaActivo
        from modules.passive_isr.passive_executor import SaviaPassivo

        if intentar_activo and conexion_mavlink:
            try:
                executor = SaviaActivo(config, conexion_mavlink)
                print(f"[+] Savia ACTIVO inicializado — MAVLink: {conexion_mavlink}")
                return executor
            except Exception as e:
                print(f"[!] No se pudo conectar MAVLink ({e}). "
                      "Degradando a Savia PASIVO...")

        print("[*] Savia PASIVO inicializado — Solo análisis ISR.")
        return SaviaPassivo(config)
