# ============================================================
# S.A.V.I.A. V7.0 — MÓDULO DE ANÁLISIS FORENSE (analisis_forense.py)
# Fusión de video .MP4 + telemetría .SRT del DJI Mini 4K
# con detección SAHI y generación de mapa táctico interactivo.
# ============================================================
#
# USO:
#   python analisis_forense.py --video ruta/video.mp4 --srt ruta/video.SRT
#                              --modelo modelo_tactico.pt --confianza 0.70
#
# SALIDA:
#   - mapa_tactico.html        (mapa interactivo Folium con marcadores)
#   - reporte_forense.csv      (índice de detecciones con coordenadas)
# ============================================================

import cv2
import os
import re
import csv
import argparse
import time
from datetime import datetime, timedelta

# --- Dependencias opcionales con verificación de instalación ---
try:
    import folium
    from folium.plugins import MarkerCluster
    FOLIUM_DISPONIBLE = True
except ImportError:
    FOLIUM_DISPONIBLE = False
    print("[!] ADVERTENCIA: folium no instalado. El mapa no se generará.")

try:
    from sahi import AutoDetectionModel
    from sahi.predict import get_sliced_prediction
    SAHI_DISPONIBLE = True
except ImportError:
    SAHI_DISPONIBLE = False
    print("[!] ADVERTENCIA: SAHI no instalado. Usando YOLO estándar.")
    from ultralytics import YOLO

import torch
import numpy as np


# ============================================================
# MAPA DE CLASES TÁCTICAS (sincronizado con radar.py)
# ============================================================
CLASES_TACTICAS = {
    0: "Civil",
    1: "Militar_Jaguar",
    2: "Vehiculo_Civil",
    3: "Vehiculo_Tactico",
}

# Colores de marcadores para el mapa (Folium usa nombres CSS)
COLORES_MAPA = {
    "Civil":            "blue",
    "Militar_Jaguar":   "red",      # Amenaza crítica → rojo
    "Vehiculo_Civil":   "white",
    "Vehiculo_Tactico": "orange",
}

# Umbral mínimo de confianza para registrar detección forense (porcentaje 0.0-1.0)
CONFIANZA_DEFAULT = 0.70

# Intervalo de muestreo: analizar 1 de cada N frames para acelerar el análisis
SAMPLE_RATE_DEFAULT = 30  # procesar ~1 frame/segundo a 30 FPS


# ============================================================
# MÓDULO 1: PARSEO DE ARCHIVOS SRT DEL DJI MINI 4K
# ============================================================

def parsear_srt(ruta_srt):
    """
    Parsea el archivo .SRT del DJI Mini 4K y construye un índice:
        {segundos_desde_inicio: {"lat": float, "lon": float, "alt": float, "texto": str}}

    Formato SRT del DJI Mini 4K:
        1
        00:00:01,000 --> 00:00:02,000
        F/2.8, SS 1000, ISO 100, EV 0, GPS (-1.234567, -78.123456, 2800), D 0.00m, ...

    El GPS puede tener formato alternativo: GPS(−1.234567,−78.123456,2800)
    """
    if not os.path.exists(ruta_srt):
        print(f"[!] Archivo SRT no encontrado: {ruta_srt}")
        return {}

    indice_gps = {}

    # Regex flexible para capturar el timestamp de inicio del bloque
    re_tiempo = re.compile(
        r'(\d{2}):(\d{2}):(\d{2})[,.](\d{3})\s*-->'
    )
    # Regex para extraer coordenadas GPS del DJI (varios formatos posibles)
    re_gps = re.compile(
        r'GPS\s*[\(\[]?\s*'
        r'([−\-]?\d+\.\d+)\s*,\s*'   # Latitud (puede tener − unicode)
        r'([−\-]?\d+\.\d+)\s*,?\s*'  # Longitud
        r'(\d*\.?\d*)\s*'             # Altitud (opcional)
        r'[\)\]]?',
        re.IGNORECASE
    )

    with open(ruta_srt, 'r', encoding='utf-8', errors='ignore') as f:
        contenido = f.read()

    # Dividir en bloques por doble salto de línea
    bloques = re.split(r'\n\s*\n', contenido.strip())

    for bloque in bloques:
        lineas = bloque.strip().splitlines()
        if len(lineas) < 2:
            continue

        # Buscar línea de tiempo
        tiempo_match = None
        texto_datos = ""
        for linea in lineas:
            m = re_tiempo.search(linea)
            if m:
                tiempo_match = m
            elif re_tiempo.search(linea) is None and '-->' not in linea:
                texto_datos += linea + " "

        if not tiempo_match:
            continue

        # Calcular segundos desde el inicio del video
        h, mi, s, ms = (int(x) for x in tiempo_match.groups())
        segundos = h * 3600 + mi * 60 + s + ms / 1000.0

        # Extraer coordenadas GPS
        # Reemplazar guión unicode por ASCII antes del regex
        texto_limpio = texto_datos.replace('−', '-')
        gps_match = re_gps.search(texto_limpio)

        if gps_match:
            lat = float(gps_match.group(1).replace('−', '-'))
            lon = float(gps_match.group(2).replace('−', '-'))
            alt_str = gps_match.group(3)
            alt = float(alt_str) if alt_str else 0.0

            indice_gps[segundos] = {
                "lat": lat,
                "lon": lon,
                "alt": alt,
                "texto": texto_datos.strip()
            }

    print(f"[+] SRT parseado: {len(indice_gps)} entradas GPS indexadas.")
    return indice_gps


def buscar_coords_en_timestamp(indice_gps, segundos_video, tolerancia=1.5):
    """
    Busca las coordenadas GPS más cercanas a un timestamp dado.
    Retorna dict con lat/lon/alt o None si no hay datos en el rango de tolerancia.
    """
    if not indice_gps:
        return None

    mejor_clave = min(indice_gps.keys(), key=lambda k: abs(k - segundos_video))
    if abs(mejor_clave - segundos_video) <= tolerancia:
        return indice_gps[mejor_clave]
    return None


# ============================================================
# MÓDULO 2: INFERENCIA SAHI SOBRE VIDEO
# ============================================================

def _inicializar_modelo(ruta_modelo, confianza, dispositivo):
    """
    Inicializa el motor de inferencia (SAHI o YOLO estándar).
    Retorna (sahi_model, yolo_fallback).
    """
    if SAHI_DISPONIBLE:
        print(f"[+] Cargando modelo SAHI: {ruta_modelo} en {dispositivo}")
        sahi_model = AutoDetectionModel.from_pretrained(
            model_type="yolov8",
            model_path=ruta_modelo,
            confidence_threshold=confianza,
            device=dispositivo,
        )
        return sahi_model, None
    else:
        print(f"[+] Cargando modelo YOLO estándar (fallback): {ruta_modelo}")
        model = YOLO(ruta_modelo)
        if dispositivo == 'cuda':
            model.to('cuda')
        return None, model


def _inferir_frame(sahi_model, yolo_model, frame_bgr, confianza, dispositivo):
    """
    Ejecuta inferencia sobre un frame BGR y retorna lista de dicts:
    [{"cls": int, "nombre": str, "conf": float, "bbox": (x1,y1,x2,y2)}]
    """
    detecciones = []

    if sahi_model is not None:
        frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        resultado = get_sliced_prediction(
            frame_rgb,
            sahi_model,
            slice_height=512,
            slice_width=512,
            overlap_height_ratio=0.2,
            overlap_width_ratio=0.2,
            perform_standard_pred=True,
            postprocess_type="NMM",
            verbose=0
        )
        for pred in resultado.object_prediction_list:
            if pred.score.value < confianza:
                continue
            cls_id = pred.category.id
            detecciones.append({
                "cls": cls_id,
                "nombre": CLASES_TACTICAS.get(cls_id, pred.category.name),
                "conf": pred.score.value,
                "bbox": (
                    int(pred.bbox.minx), int(pred.bbox.miny),
                    int(pred.bbox.maxx), int(pred.bbox.maxy)
                )
            })
    elif yolo_model is not None:
        resultados = yolo_model.predict(
            frame_bgr, conf=confianza, verbose=False,
            device=0 if dispositivo == 'cuda' else 'cpu'
        )
        for r in resultados:
            if r.boxes:
                for b in r.boxes:
                    cls_id = int(b.cls[0])
                    x1, y1, x2, y2 = map(int, b.xyxy[0])
                    detecciones.append({
                        "cls": cls_id,
                        "nombre": CLASES_TACTICAS.get(cls_id, f"cls_{cls_id}"),
                        "conf": float(b.conf[0]),
                        "bbox": (x1, y1, x2, y2)
                    })

    return detecciones


# ============================================================
# MÓDULO 3: GENERACIÓN DE MAPA TÁCTICO CON FOLIUM
# ============================================================

def generar_mapa_tactico(eventos, ruta_salida="mapa_tactico.html"):
    """
    Genera un mapa HTML interactivo con Folium.
    Marca cada detección con un marcador coloreado según la clase táctica.
    """
    if not FOLIUM_DISPONIBLE:
        print("[!] Folium no disponible. No se puede generar el mapa.")
        return None

    if not eventos:
        print("[!] Sin eventos para mapear.")
        return None

    # Calcular centro del mapa (promedio de coordenadas)
    lats = [e["lat"] for e in eventos if e.get("lat")]
    lons = [e["lon"] for e in eventos if e.get("lon")]
    if not lats:
        print("[!] No hay coordenadas GPS válidas para el mapa.")
        return None

    centro_lat = sum(lats) / len(lats)
    centro_lon = sum(lons) / len(lons)

    # Crear mapa base con tema oscuro (operación nocturna)
    mapa = folium.Map(
        location=[centro_lat, centro_lon],
        zoom_start=17,
        tiles="CartoDB dark_matter",
        control_scale=True
    )

    # Añadir capa satelital alternativa para visión diurna
    folium.TileLayer(
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        attr="Esri World Imagery",
        name="Vista Satelital",
        overlay=False
    ).add_to(mapa)

    folium.TileLayer("CartoDB dark_matter", name="Vista Táctica Nocturna").add_to(mapa)

    # Cluster de marcadores para vista general
    cluster = MarkerCluster(name="Todas las Detecciones").add_to(mapa)

    # Capa separada para amenazas críticas (Militar_Jaguar)
    capa_amenazas = folium.FeatureGroup(name="⚠ Amenazas Críticas (Militar_Jaguar)")

    for evento in eventos:
        lat = evento.get("lat")
        lon = evento.get("lon")
        if not lat or not lon:
            continue

        nombre_clase = evento.get("clase", "Desconocido")
        confianza_pct = int(evento.get("conf", 0) * 100)
        timestamp = evento.get("timestamp_str", "N/A")
        frame_num = evento.get("frame", "N/A")
        alt = evento.get("alt", 0)

        color_marcador = COLORES_MAPA.get(nombre_clase, "gray")

        # Popup HTML enriquecido
        popup_html = f"""
        <div style="font-family: monospace; background:#1a1a1a; color:#00ff88;
                    padding:10px; border:1px solid #00ff88; border-radius:5px; min-width:220px;">
            <b style="color:#ff4444; font-size:14px;">★ DETECCIÓN TÁCTICA</b><br>
            <hr style="border-color:#333;">
            <b>Clase:</b> {nombre_clase}<br>
            <b>Confianza:</b> {confianza_pct}%<br>
            <b>Timestamp:</b> {timestamp}<br>
            <b>Frame:</b> #{frame_num}<br>
            <hr style="border-color:#333;">
            <b>Coordenadas:</b><br>
            LAT: {lat:.6f}<br>
            LON: {lon:.6f}<br>
            ALT: {alt:.0f} m
        </div>
        """

        icono = folium.Icon(
            color=color_marcador,
            icon="exclamation-triangle" if nombre_clase == "Militar_Jaguar" else "eye",
            prefix="fa"
        )

        marcador = folium.Marker(
            location=[lat, lon],
            popup=folium.Popup(popup_html, max_width=280),
            tooltip=f"{nombre_clase} ({confianza_pct}%) — {timestamp}",
            icon=icono
        )

        # Amenazas críticas van a su propia capa además del cluster
        if nombre_clase == "Militar_Jaguar":
            marcador.add_to(capa_amenazas)
            # Círculo de alerta
            folium.Circle(
                location=[lat, lon],
                radius=15,
                color="red",
                fill=True,
                fill_color="red",
                fill_opacity=0.2,
                tooltip=f"Zona de alerta — {nombre_clase}"
            ).add_to(capa_amenazas)
        else:
            marcador.add_to(cluster)

    capa_amenazas.add_to(mapa)
    folium.LayerControl(collapsed=False).add_to(mapa)

    # Título del mapa (HTML incrustado)
    titulo_html = """
    <div style="position:fixed; top:10px; left:50%; transform:translateX(-50%);
                z-index:1000; background:#0a1a0a; border:2px solid #00ff88;
                padding:8px 20px; border-radius:5px; font-family:monospace;">
        <span style="color:#ff4444; font-weight:bold;">★ RESERVADO</span>
        <span style="color:#00ff88; font-weight:bold; margin:0 15px;">
            S.A.V.I.A. V7.0 — MAPA TÁCTICO DE INTELIGENCIA
        </span>
        <span style="color:#ff4444; font-weight:bold;">★ RESERVADO</span>
    </div>
    """
    mapa.get_root().html.add_child(folium.Element(titulo_html))

    mapa.save(ruta_salida)
    print(f"[+] Mapa táctico generado: {ruta_salida}")
    return ruta_salida


# ============================================================
# FUNCIÓN PRINCIPAL DE ANÁLISIS FORENSE
# ============================================================

def analizar_video_forense(
    ruta_video,
    ruta_srt,
    ruta_modelo,
    confianza=CONFIANZA_DEFAULT,
    sample_rate=SAMPLE_RATE_DEFAULT,
    clases_objetivo=None,        # None = todas las clases tácticas
    ruta_mapa="mapa_tactico.html",
    ruta_csv="reporte_forense.csv"
):
    """
    Función principal de análisis post-vuelo forense.

    Args:
        ruta_video:    Ruta al archivo .MP4 del dron
        ruta_srt:      Ruta al archivo .SRT de telemetría
        ruta_modelo:   Ruta al modelo .pt (táctico personalizado)
        confianza:     Umbral de confianza mínimo (0.0 - 1.0)
        sample_rate:   Procesar 1 de cada N frames
        clases_objetivo: Lista de cls_id a detectar (None = todas)
        ruta_mapa:     Ruta de salida del HTML del mapa
        ruta_csv:      Ruta de salida del CSV forense
    """
    print("\n" + "=" * 60)
    print("  S.A.V.I.A. V7.0 — MÓDULO DE ANÁLISIS FORENSE")
    print("=" * 60)
    print(f"  Video:    {ruta_video}")
    print(f"  SRT:      {ruta_srt}")
    print(f"  Modelo:   {ruta_modelo}")
    print(f"  Confianza mínima: {int(confianza * 100)}%")
    print("=" * 60 + "\n")

    # --- Validaciones ---
    if not os.path.exists(ruta_video):
        print(f"[!] Error: Video no encontrado → {ruta_video}")
        return
    if not os.path.exists(ruta_modelo):
        print(f"[!] Error: Modelo no encontrado → {ruta_modelo}")
        return

    # --- Parseo del SRT ---
    indice_gps = parsear_srt(ruta_srt) if ruta_srt else {}

    # --- Configurar dispositivo ---
    dispositivo = 'cuda' if torch.cuda.is_available() else 'cpu'
    print(f"[+] Dispositivo de cómputo: {dispositivo.upper()}")

    # --- Inicializar modelo ---
    sahi_model, yolo_model = _inicializar_modelo(ruta_modelo, confianza, dispositivo)

    # --- Abrir video ---
    cap = cv2.VideoCapture(ruta_video)
    if not cap.isOpened():
        print(f"[!] Error: No se puede abrir el video → {ruta_video}")
        return

    fps_video = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    duracion_s = total_frames / fps_video

    print(f"[+] Video: {total_frames} frames | {fps_video:.1f} FPS | {duracion_s:.1f}s de duración")
    print(f"[+] Analizando 1 de cada {sample_rate} frames (~{fps_video/sample_rate:.1f} fps de análisis)\n")

    # --- Procesamiento frame a frame ---
    eventos_detectados = []
    frame_idx = 0
    frames_procesados = 0
    inicio_analisis = time.time()

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        frame_idx += 1

        # Frame skip para acelerar el análisis
        if frame_idx % sample_rate != 0:
            continue

        frames_procesados += 1
        segundos_video = frame_idx / fps_video
        timestamp_str = str(timedelta(seconds=int(segundos_video)))

        # --- Inferencia ---
        detecciones = _inferir_frame(sahi_model, yolo_model, frame, confianza, dispositivo)

        # Filtrar por clases de interés
        if clases_objetivo:
            detecciones = [d for d in detecciones if d["cls"] in clases_objetivo]

        # --- Correlación GPS ---
        for det in detecciones:
            coords = buscar_coords_en_timestamp(indice_gps, segundos_video)

            evento = {
                "frame": frame_idx,
                "timestamp_str": timestamp_str,
                "segundos": segundos_video,
                "cls": det["cls"],
                "clase": det["nombre"],
                "conf": det["conf"],
                "lat": coords["lat"] if coords else None,
                "lon": coords["lon"] if coords else None,
                "alt": coords["alt"] if coords else None,
                "bbox": det["bbox"],
            }
            eventos_detectados.append(evento)

            icono_clase = "⚠" if det["nombre"] == "Militar_Jaguar" else "•"
            gps_txt = (
                f"GPS: {coords['lat']:.5f}, {coords['lon']:.5f}"
                if coords else "GPS: sin datos"
            )
            print(
                f"  [{timestamp_str}] {icono_clase} {det['nombre']} "
                f"({int(det['conf']*100)}%) | {gps_txt}"
            )

        # Progreso
        if frames_procesados % 10 == 0:
            progreso = (frame_idx / total_frames) * 100
            tiempo_transcurrido = time.time() - inicio_analisis
            print(f"  [...] Progreso: {progreso:.1f}% | Eventos: {len(eventos_detectados)} | "
                  f"Tiempo: {tiempo_transcurrido:.0f}s")

    cap.release()

    tiempo_total = time.time() - inicio_analisis
    print(f"\n[+] Análisis completado: {frames_procesados} frames procesados en {tiempo_total:.1f}s")
    print(f"[+] Total de eventos detectados: {len(eventos_detectados)}")

    # --- Guardar CSV forense ---
    with open(ruta_csv, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=[
            "frame", "timestamp_str", "segundos", "cls",
            "clase", "conf", "lat", "lon", "alt", "bbox"
        ])
        writer.writeheader()
        for e in eventos_detectados:
            writer.writerow({k: v for k, v in e.items()})
    print(f"[+] Reporte CSV guardado: {ruta_csv}")

    # --- Generar mapa táctico ---
    if eventos_detectados:
        generar_mapa_tactico(eventos_detectados, ruta_salida=ruta_mapa)
        # Abrir el mapa automáticamente
        try:
            os.startfile(ruta_mapa)
        except Exception:
            print(f"[!] Abre manualmente: {os.path.abspath(ruta_mapa)}")
    else:
        print("[!] No se detectaron amenazas. Mapa no generado.")

    print("\n[✓] Misión de análisis forense completada.\n")
    return eventos_detectados


# ============================================================
# INTERFAZ DE LÍNEA DE COMANDOS (CLI)
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description="S.A.V.I.A. V7.0 — Análisis Forense Post-Vuelo DJI Mini 4K",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos de uso:
  python analisis_forense.py --video mision_01.mp4 --srt mision_01.SRT --modelo modelo_tactico.pt
  python analisis_forense.py --video vuelo.mp4 --srt vuelo.SRT --modelo yolov8n.pt --confianza 0.65
  python analisis_forense.py --video vuelo.mp4 --srt vuelo.SRT --modelo tactico.pt --solo-amenazas
        """
    )
    parser.add_argument("--video",      required=True, help="Ruta al archivo .MP4 del dron")
    parser.add_argument("--srt",        required=True, help="Ruta al archivo .SRT de telemetría DJI")
    parser.add_argument("--modelo",     required=True, help="Ruta al modelo YOLO (.pt)")
    parser.add_argument("--confianza",  type=float, default=CONFIANZA_DEFAULT,
                        help=f"Umbral de confianza mínima (default: {CONFIANZA_DEFAULT})")
    parser.add_argument("--sample-rate", type=int, default=SAMPLE_RATE_DEFAULT,
                        help=f"Procesar 1 de cada N frames (default: {SAMPLE_RATE_DEFAULT})")
    parser.add_argument("--solo-amenazas", action="store_true",
                        help="Solo detectar Militar_Jaguar (cls=1)")
    parser.add_argument("--mapa",       default="mapa_tactico.html",
                        help="Ruta de salida del mapa HTML")
    parser.add_argument("--csv",        default="reporte_forense.csv",
                        help="Ruta de salida del CSV forense")

    args = parser.parse_args()

    clases_filtro = [1] if args.solo_amenazas else None  # 1 = Militar_Jaguar

    analizar_video_forense(
        ruta_video=args.video,
        ruta_srt=args.srt,
        ruta_modelo=args.modelo,
        confianza=args.confianza,
        sample_rate=args.sample_rate,
        clases_objetivo=clases_filtro,
        ruta_mapa=args.mapa,
        ruta_csv=args.csv
    )


if __name__ == "__main__":
    main()
