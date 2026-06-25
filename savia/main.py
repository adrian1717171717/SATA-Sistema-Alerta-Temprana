"""
S.A.V.I.A. — Punto de Entrada Principal del Módulo Savia
=========================================================
Demostración del patrón Strategy/Factory para selección automática
del Tier de ejecución según el hardware disponible.

Uso:
    python savia/main.py --demo --plan cuadricula
    python savia/main.py --tier pasivo --video 0 --modelo yolov8n.pt
    python savia/main.py --tier activo --video rtsp://... --mavlink udp://:14540
"""
from __future__ import annotations
import argparse
import sys
import os

# Asegura que el directorio raíz del proyecto esté en sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.data_models import (
    ConfigMision, AreaMision, ParametrosCamara, TipoMision
)
from core.mission_planner import PlanificadorMision
from core.mission_executor import SaviaFactory


def main():
    parser = argparse.ArgumentParser(
        description="S.A.V.I.A. — Sistema de Asistencia Visual e Inteligencia Artificial",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--tier",    choices=["pasivo", "activo"], default="pasivo")
    parser.add_argument("--plan",    choices=["cuadricula", "perimetro", "punto"],
                        default="cuadricula")
    parser.add_argument("--video",   default="0")
    parser.add_argument("--modelo",  default="yolov8n.pt")
    parser.add_argument("--mavlink", default="udp://:14540")
    parser.add_argument("--lat-min", type=float, default=4.700)
    parser.add_argument("--lat-max", type=float, default=4.720)
    parser.add_argument("--lon-min", type=float, default=-74.080)
    parser.add_argument("--lon-max", type=float, default=-74.060)
    parser.add_argument("--altitud", type=float, default=50.0)
    parser.add_argument("--separacion", type=float, default=30.0)
    parser.add_argument("--demo",    action="store_true",
                        help="Solo planifica y muestra métricas, sin ejecutar.")
    args = parser.parse_args()

    print("=" * 60)
    print("  S.A.V.I.A. v7.0 — Modulo de Mision Tactica ISR")
    print("=" * 60)

    # ── 1. Configurar la misión ──────────────────────────────────────────────
    tipo_map = {
        "cuadricula": TipoMision.CUADRICULA,
        "perimetro":  TipoMision.PERIMETRO,
        "punto":      TipoMision.PUNTO_A_PUNTO,
    }

    area = AreaMision(
        nombre="AO_ALPHA",
        lat_min=args.lat_min, lat_max=args.lat_max,
        lon_min=args.lon_min, lon_max=args.lon_max,
        altitud_base=args.altitud
    )

    config = ConfigMision(
        nombre=f"MISION_{args.plan.upper()}_{args.tier.upper()}",
        tipo=tipo_map[args.plan],
        area=area,
        camara=ParametrosCamara(),
        modelo_ia=args.modelo,
        altitud_escaneo=args.altitud,
        separacion_lineas=args.separacion,
        velocidad_crucero=5.0
    )

    # ── 2. Planificar ────────────────────────────────────────────────────────
    planner = PlanificadorMision()
    planner.configurar(config)
    waypoints = planner.planificar()
    metricas  = planner.calcular_metricas()

    print(f"\n[PLAN] {config.nombre}")
    print(f"  Tipo:            {config.tipo.name}")
    print(f"  Waypoints:       {metricas['n_waypoints']}")
    print(f"  Distancia:       {metricas['distancia_km']} km")
    print(f"  Tiempo estimado: {metricas['tiempo_min']} min")
    print(f"  Area cubierta:   {metricas['area_ha']} ha")
    print(f"  Altitud:         {metricas['altitud_m']} m AGL")

    if args.demo:
        print("\n[DEMO] Primeros 5 waypoints generados:")
        for i, wp in enumerate(waypoints[:5]):
            print(f"  WP{i+1}: {wp}")
        if len(waypoints) > 5:
            print(f"  ... y {len(waypoints)-5} mas.")

        print("\n[DEMO] Formato MAVLink (primeros 3):")
        for item in planner.exportar_mavlink()[:3]:
            print(f"  seq={item['seq']} cmd={item['command']} "
                  f"lat={item['x']:.6f} lon={item['y']:.6f} alt={item['z']}m")

        print(f"\n[*] Modo DEMO — Sistema no desplegado.")
        return

    # ── 3. Ejecutor via Factory ──────────────────────────────────────────────
    print(f"\n[*] Inicializando Savia {args.tier.upper()}...")
    try:
        fuente_video = int(args.video) if args.video.isdigit() else args.video
        ejecutor = SaviaFactory.crear(
            config=config,
            intentar_activo=(args.tier == "activo"),
            conexion_mavlink=args.mavlink
        )
    except Exception as e:
        print(f"[!] Error inicializando ejecutor: {e}")
        sys.exit(1)

    print(f"\n[OK] Ejecutor: Savia {ejecutor.tier}")
    print(f"[OK] Capacidades: {ejecutor.capacidades}")

    ejecutor.on_alerta(lambda obj: print(f"\n[!!!] ALERTA: {obj}"))
    ejecutor.on_cambio_estado(lambda est: print(f"[*] Estado: {est.name}"))

    # ── 4. Ejecutar ──────────────────────────────────────────────────────────
    try:
        ejecutor.iniciar(fuente_video, waypoints)
        print("\n[*] Mision activa. Ctrl+C para detener.")
        import time
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[*] Detencion solicitada por operador.")
    finally:
        ejecutor.detener()
        ruta_pdf = ejecutor.generar_reporte_postflight()
        if ruta_pdf:
            print(f"\n[+] Reporte post-vuelo: {ruta_pdf}")


if __name__ == "__main__":
    main()
