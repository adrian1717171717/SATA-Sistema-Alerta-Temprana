"""
S.A.V.I.A. — GESTOR DE FAILSAFE TÁCTICO (Tier 2)
===================================================
Monitorea continuamente la telemetría del dron y activa protocolos
de Retorno a Base (RTB) cuando se detectan condiciones de riesgo:

  1. BINGO FUEL:  Batería crítica (< umbral configurado)
  2. JAMMING:     Pérdida de enlace RC / RSSI degradado
  3. GEOFENCE:    Dron fuera del área de misión autorizada
  4. MANUAL:      RTB ordenado por el operador

El módulo corre en un hilo daemon independiente para no bloquear
el bucle de video ni la telemetría.
"""
from __future__ import annotations
import threading
import time
import math
from typing import Optional, Callable
from core.data_models import (
    TelemetriaFrame, AreaMision, ConfigMision,
    CausaFailsafe, EstadoMision
)


class GestorFailsafe:
    """
    Monitor de failsafe táctico para el Tier Activo.

    Patrones de riesgo vigilados:
      - Batería <= umbral_bateria_pct  → BINGO FUEL
      - RSSI    <= umbral_rssi_dbm     → JAMMING detectado
      - GPS fuera del área de misión   → GEOFENCE violation
      - Contador de pérdida de enlace  → SIGNAL LOST (>3s sin trama)

    Al activarse, invoca el callback cb_rtb(causa) para que el
    ejecutor activo envíe el comando RTB al dron.
    """

    # Hysteresis: cuántas muestras consecutivas deben cumplir la condición
    # antes de disparar el failsafe (evitar falsos positivos)
    MUESTRAS_CONFIRMACION = 3

    def __init__(self,
                 config: ConfigMision,
                 cb_rtb: Callable[[CausaFailsafe], None]):
        """
        Args:
            config:  Configuración de la misión (contiene umbrales de failsafe)
            cb_rtb:  Callback que se invoca cuando se activa el RTB
        """
        self._config     = config
        self._cb_rtb     = cb_rtb
        self._activo     = False
        self._hilo:      Optional[threading.Thread] = None
        self._telemetria: Optional[TelemetriaFrame] = None
        self._lock       = threading.Lock()

        # Estado interno de hysteresis
        self._cnt_bateria = 0
        self._cnt_rssi    = 0
        self._cnt_geofence = 0
        self._ultima_trama = time.time()

        # Estado
        self._rtb_activado      = False
        self._causa_rtb: CausaFailsafe = CausaFailsafe.NINGUNA

    # ─── Control del hilo ─────────────────────────────────────────────────────

    def iniciar(self) -> None:
        """Inicia el hilo de monitoreo de failsafe."""
        self._activo = True
        self._hilo = threading.Thread(
            target=self._bucle_monitoreo,
            daemon=True,
            name="Failsafe-Monitor"
        )
        self._hilo.start()
        print("[+] Failsafe Táctico: monitor activo.")

    def detener(self) -> None:
        """Detiene el hilo de monitoreo."""
        self._activo = False
        if self._hilo:
            self._hilo.join(timeout=2.0)

    def actualizar_telemetria(self, trama: TelemetriaFrame) -> None:
        """
        Recibe la última trama de telemetría del dron.
        Llamar desde el hilo de telemetría del ejecutor activo.
        """
        with self._lock:
            self._telemetria   = trama
            self._ultima_trama = time.time()

    def activar_rtb_manual(self) -> None:
        """El operador ordena RTB manualmente."""
        if not self._rtb_activado:
            self._disparar_failsafe(CausaFailsafe.COMANDO_OPERADOR)

    @property
    def rtb_activado(self) -> bool:
        return self._rtb_activado

    @property
    def causa(self) -> CausaFailsafe:
        return self._causa_rtb

    # ─── Bucle de monitoreo ───────────────────────────────────────────────────

    def _bucle_monitoreo(self) -> None:
        """
        Hilo de monitoreo continuo. Evalúa las condiciones de failsafe
        cada 500ms usando hysteresis para evitar falsos positivos.
        """
        while self._activo:
            time.sleep(0.5)

            if self._rtb_activado:
                continue  # Ya está en RTB, no re-evaluar

            with self._lock:
                trama = self._telemetria

            if trama is None:
                # Sin telemetría — verificar timeout de enlace
                tiempo_sin_trama = time.time() - self._ultima_trama
                if tiempo_sin_trama > 5.0:  # 5 segundos sin trama = enlace perdido
                    self._cnt_rssi += 1
                    if self._cnt_rssi >= self.MUESTRAS_CONFIRMACION:
                        self._disparar_failsafe(CausaFailsafe.PERDIDA_ENLACE)
                continue

            # Resetear contador de timeout si hay telemetría
            self._cnt_rssi = max(0, self._cnt_rssi - 1)

            # ── Verificar BINGO FUEL ──────────────────────────────────────────
            if trama.bateria_pct <= self._config.umbral_bateria:
                self._cnt_bateria += 1
                if self._cnt_bateria >= self.MUESTRAS_CONFIRMACION:
                    self._disparar_failsafe(CausaFailsafe.BATERIA_CRITICA)
            else:
                self._cnt_bateria = max(0, self._cnt_bateria - 1)

            # ── Verificar JAMMING (RSSI degradado) ────────────────────────────
            if trama.rssi <= self._config.umbral_rssi:
                self._cnt_rssi += 1
                if self._cnt_rssi >= self.MUESTRAS_CONFIRMACION:
                    self._disparar_failsafe(CausaFailsafe.PERDIDA_ENLACE)
            else:
                self._cnt_rssi = max(0, self._cnt_rssi - 1)

            # ── Verificar GEOFENCE ────────────────────────────────────────────
            if self._config.area:
                if not self._dentro_de_area(trama, self._config.area):
                    self._cnt_geofence += 1
                    if self._cnt_geofence >= self.MUESTRAS_CONFIRMACION * 2:
                        self._disparar_failsafe(CausaFailsafe.GEOFENCE)
                else:
                    self._cnt_geofence = max(0, self._cnt_geofence - 1)

    def _disparar_failsafe(self, causa: CausaFailsafe) -> None:
        """
        Activa el failsafe táctico. Solo se puede disparar una vez por misión.
        Imprime el evento y llama al callback del ejecutor activo.
        """
        if self._rtb_activado:
            return  # Ya activado, ignorar

        self._rtb_activado = True
        self._causa_rtb    = causa

        nombres = {
            CausaFailsafe.BATERIA_CRITICA:  "BINGO FUEL — Batería crítica",
            CausaFailsafe.PERDIDA_ENLACE:   "JAMMING/SIGNAL LOST — Enlace perdido",
            CausaFailsafe.GEOFENCE:         "GEOFENCE — Dron fuera del área autorizada",
            CausaFailsafe.COMANDO_OPERADOR: "RTB MANUAL — Ordenado por operador",
        }
        print(f"\n[!!!] FAILSAFE TÁCTICO ACTIVADO: {nombres.get(causa, causa.name)}")

        try:
            self._cb_rtb(causa)
        except Exception as e:
            print(f"[!] Error en callback RTB: {e}")

    @staticmethod
    def _dentro_de_area(trama: TelemetriaFrame, area: AreaMision) -> bool:
        """
        Verifica si el dron está dentro del bounding box del área de misión.
        Agrega un margen del 10% para tolerancia de trayectoria.
        """
        margen_lat = (area.lat_max - area.lat_min) * 0.10
        margen_lon = (area.lon_max - area.lon_min) * 0.10
        return (
            (area.lat_min - margen_lat) <= trama.latitud  <= (area.lat_max + margen_lat) and
            (area.lon_min - margen_lon) <= trama.longitud <= (area.lon_max + margen_lon)
        )
