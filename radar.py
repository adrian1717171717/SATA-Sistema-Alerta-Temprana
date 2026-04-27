import cv2
import os
import time
import numpy as np
import torch
import threading
from datetime import datetime
from ultralytics import YOLO
import winsound
import win32gui
import win32ui
import ctypes
import telemetria
import csv
from cryptography.fernet import Fernet

# LLAVE DE CIFRADO TÁCTICO (S.A.T.A. v6.2)
SATA_KEY = b'cYaPITSeO2gj2QiSrLiVTVagbATv7BstuzSaAXPYD3o='
cipher_suite = Fernet(SATA_KEY)

puntos_zona = []

def registrar_novedad(modo, confianza, frame):
    """ Guarda una captura CIFRADA y registra la novedad en el CSV """
    carpeta_evidencia = "Evidencia_Seguridad"
    if not os.path.exists(carpeta_evidencia): os.makedirs(carpeta_evidencia)
    
    fecha_hora = datetime.now()
    nombre_foto = f"ALERTA_{fecha_hora.strftime('%Y%m%d_%H%M%S')}.sata_enc"
    ruta_foto = os.path.join(carpeta_evidencia, nombre_foto)
    
    # CIFRADO DE IMAGEN EN MEMORIA
    exito, buffer = cv2.imencode('.jpg', frame)
    if exito:
        img_bytes = buffer.tobytes()
        img_encriptada = cipher_suite.encrypt(img_bytes)
        with open(ruta_foto, 'wb') as f:
            f.write(img_encriptada)
    
    archivo_csv = os.path.join(carpeta_evidencia, "registro_novedades.csv")
    existe = os.path.exists(archivo_csv)
    
    with open(archivo_csv, mode='a', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        if not existe:
            writer.writerow(["Fecha", "Hora", "Modo de Operación", "Nivel de Confianza (%)", "Archivo de Foto"])
        writer.writerow([
            fecha_hora.strftime("%Y-%m-%d"),
            fecha_hora.strftime("%H:%M:%S"),
            modo,
            f"{confianza}%" if isinstance(confianza, (int, float)) else str(confianza),
            nombre_foto
        ])
    print(f"[!] Registro táctico cifrado completado: {nombre_foto}")

class VideoStream:
    """ Clase para lectura de video multihilo (Elimina el LAG del búfer de OpenCV) """
    def __init__(self, src, backend=cv2.CAP_ANY):
        self.cap = cv2.VideoCapture(src, backend)
        if backend == cv2.CAP_FFMPEG:
            # Forzamos latencia mínima en el backend
            self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        
        self.ret, self.frame = self.cap.read()
        self.stopped = False
        self.lock = threading.Lock()

    def start(self):
        t = threading.Thread(target=self.update, args=(), daemon=True)
        t.start()
        return self

    def update(self):
        while not self.stopped:
            if not self.ret:
                self.stopped = True
                continue
            
            ret, frame = self.cap.read()
            with self.lock:
                self.ret, self.frame = ret, frame

    def read(self):
        with self.lock:
            return self.ret, self.frame

    def release(self):
        self.stopped = True
        self.cap.release()

def sonar_alarma():
    try:
        winsound.Beep(1500, 100)
    except:
        pass

def seleccionar_puntos(event, x, y, flags, param):
    global puntos_zona
    if event == cv2.EVENT_LBUTTONDOWN:
        puntos_zona.append((x, y))
    elif event == cv2.EVENT_RBUTTONDOWN:
        puntos_zona = []

def dibujar_texto_legible(imagen, texto, posicion, fuente, escala, color, grosor=1):
    cv2.putText(imagen, texto, posicion, fuente, escala, (0, 0, 0), grosor + 1)
    cv2.putText(imagen, texto, posicion, fuente, escala, color, grosor)

def capturar_ventana_especifica(titulo_ventana):
    hwnd = win32gui.FindWindow(None, titulo_ventana)
    if not hwnd: return None 
    left, top, right, bot = win32gui.GetClientRect(hwnd)
    w, h = right - left, bot - top
    if w <= 0 or h <= 0: return None
    hwndDC = win32gui.GetWindowDC(hwnd)
    mfcDC  = win32ui.CreateDCFromHandle(hwndDC)
    saveDC = mfcDC.CreateCompatibleDC()
    saveBitMap = win32ui.CreateBitmap()
    saveBitMap.CreateCompatibleBitmap(mfcDC, w, h)
    saveDC.SelectObject(saveBitMap)
    ctypes.windll.user32.PrintWindow(hwnd, saveDC.GetSafeHdc(), 2)
    bmpinfo = saveBitMap.GetInfo()
    bmpstr = saveBitMap.GetBitmapBits(True)
    img = np.frombuffer(bmpstr, dtype='uint8').reshape((bmpinfo['bmHeight'], bmpinfo['bmWidth'], 4))
    img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
    win32gui.DeleteObject(saveBitMap.GetHandle())
    saveDC.DeleteDC()
    mfcDC.DeleteDC()
    win32gui.ReleaseDC(hwnd, hwndDC)
    if w > 1280 or h > 720:
        img = cv2.resize(img, (1280, 720))
    return img

def parse_zona_gps(zona_gps):
    if not zona_gps: return None
    coords = []
    try:
        for p in zona_gps.split(";"):
            p = p.strip()
            if not p: continue
            lat, lon = p.split(",")
            coords.append((float(lat.strip()), float(lon.strip())))
    except: return None
    return coords

def punto_en_poligono(point, polygon):
    x, y = point
    inside = False
    n = len(polygon)
    for i in range(n):
        x1, y1 = polygon[i]
        x2, y2 = polygon[(i + 1) % n]
        if ((y1 > y) != (y2 > y)) and (x < (x2 - x1) * (y - y1) / (y2 - y1) + x1):
            inside = not inside
    return inside

def iniciar_radar(fuente_video=0, modelo_ia='yolov8n.pt', modo_estatico=True, modo_garita=False, modo_silencioso_global=False, usar_telemetria=False, sdk_url=None, zona_gps=None, sensibilidad=0.6):
    carpeta_evidencia = "Evidencia_Seguridad"
    if not os.path.exists(carpeta_evidencia): os.makedirs(carpeta_evidencia)
    
    print(f"\n[+] Cargando modelo táctico: {modelo_ia}")
    dispositivo = 0 if torch.cuda.is_available() else 'cpu'
    
    # MÁXIMA CAPACIDAD NVIDIA (Si hay CUDA disponible)
    if dispositivo == 0:
        torch.backends.cudnn.benchmark = True  # Acelera convoluciones en tamaños estables
        torch.backends.cudnn.deterministic = False # Permite elegir el algoritmo más rápido
        print("[+] Optimización Extrema NVIDIA (CUDA+CuDNN Benchmark): ACTIVADA")

    model = YOLO(modelo_ia)
    if dispositivo == 0: 
        model.to('cuda')
        # OPTIMIZACIÓN: Calentamiento de GPU para evitar tirones iniciales
        dummy_frame = np.zeros((640, 640, 3), dtype=np.uint8)
        model.predict(dummy_frame, device=dispositivo, verbose=False, half=True)

    ultimo_guardado = 0
    tiempo_anterior = 0
    alarma_silenciada_temporal = False
    silencio_global = modo_silencioso_global
    cv2.namedWindow("S.A.T.A. - Visor de Operaciones", cv2.WINDOW_NORMAL)
    if modo_estatico and not modo_garita: cv2.setMouseCallback("S.A.T.A. - Visor de Operaciones", seleccionar_puntos)

    telemetria_data = None
    geocerca_coords = parse_zona_gps(zona_gps) if zona_gps else None
    if usar_telemetria:
        telemetria_data = telemetria.DroneTelemetry(sdk_url or "udp://:14540")
        telemetria_data.start()

    vs = None
    if not modo_garita:
        attempts = 0
        while attempts < 30:
            attempts += 1
            # Usamos FFMPEG para streams y CAP_ANY para webcams
            backend = cv2.CAP_FFMPEG if isinstance(fuente_video, str) else cv2.CAP_ANY
            vs = VideoStream(fuente_video, backend)
            if vs.ret: break
            vs.release()
            print(f"[+] Esperando dron... ({attempts}/30)")
            time.sleep(1)
        if not vs or not vs.ret:
            print("[!] Error de conexión."); return
        vs.start() # Iniciamos el hilo de lectura

    CLASES_INTERES = [0, 2, 3, 5, 7, 15, 16, 17, 19]
    modo_txt = "DRON" if not modo_estatico else ("GARITA" if modo_garita else "CENTINELA")

    while True:
        if modo_garita:
            frame = capturar_ventana_especifica(fuente_video)
        else:
            exito, frame = vs.read()
            if not exito:
                # RECONEXIÓN AUTOMÁTICA
                black_frame = np.zeros((720, 1280, 3), dtype=np.uint8)
                msg = "[!] PERDIDA DE SENAL DE TELEMETRIA - RECONECTANDO..."
                cv2.putText(black_frame, msg, (100, 360), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)
                cv2.imshow("S.A.T.A. - Visor de Operaciones", black_frame)
                cv2.waitKey(2000)
                
                print("[!] Intentando reconectar stream...")
                vs.release()
                backend = cv2.CAP_FFMPEG if isinstance(fuente_video, str) else cv2.CAP_ANY
                vs = VideoStream(fuente_video, backend)
                if vs.ret: vs.start()
                continue

        if frame is None:
            if modo_garita: break
            continue

        # REDUCCIÓN DE RESOLUCIÓN PARA VELOCIDAD IA
        h_orig, w_orig = frame.shape[:2]
        if w_orig > 1024:
            scale = 1024 / w_orig
            frame = cv2.resize(frame, (0,0), fx=scale, fy=scale, interpolation=cv2.INTER_LINEAR)
        
        h_proc, w_proc = frame.shape[:2]
        
        # INFERENCIA OPTIMIZADA (FP16 si hay GPU)
        # half=True reduce el uso de memoria y acelera el proceso en RTX
        resultados = model.track(frame, persist=True, classes=CLASES_INTERES, conf=sensibilidad, verbose=False, device=dispositivo, half=(dispositivo == 0))

        total_personas, intrusos, amenaza_critica = 0, 0, False
        
        if modo_estatico and not modo_garita and len(puntos_zona) > 0:
            for pt in puntos_zona: cv2.circle(frame, pt, 5, (0, 0, 255), -1)
            if len(puntos_zona) > 1:
                pts = np.array(puntos_zona, np.int32).reshape((-1, 1, 2))
                cv2.polylines(frame, [pts], isClosed=True, color=(0, 0, 255), thickness=2)

        for r in resultados:
            if r.boxes:
                for caja in r.boxes:
                    x1, y1, x2, y2 = map(int, caja.xyxy[0])
                    cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
                    conf, cls = int(caja.conf[0] * 100), int(caja.cls[0])

                    if cls == 0:
                        tipo, col = "PERSONA", (0, 255, 0)
                        total_personas += 1
                        # Lógica de geocerca
                        if modo_estatico and not modo_garita:
                            if len(puntos_zona) > 2 and cv2.pointPolygonTest(np.array(puntos_zona, np.int32), (cx, cy), False) >= 0:
                                col, amenaza_critica = (0, 0, 255), True
                                intrusos += 1
                        else: col, amenaza_critica, intrusos = (0, 0, 255), True, intrusos + 1
                    elif cls in [2,3,5,7]: tipo, col = "VEHICULO", (255, 150, 0)
                    else: tipo, col = "ANIMAL", (0, 255, 255)

                    cv2.rectangle(frame, (x1, y1), (x2, y2), col, 2)
                    dibujar_texto_legible(frame, f"{tipo} {conf}%", (x1, y1 - 10), cv2.FONT_HERSHEY_DUPLEX, 0.6, col, 1)

        # Alarmas asíncronas y Registro de Evidencia
        if amenaza_critica:
            if not silencio_global and not alarma_silenciada_temporal:
                threading.Thread(target=sonar_alarma, daemon=True).start()
                alarma_silenciada_temporal = True 
            
            # MÓDULO DE BITÁCORA AUTOMÁTICA (Cooldown 15s)
            if time.time() - ultimo_guardado > 15:
                # Buscar confianza máxima entre intrusos
                conf_max = 0
                for r in resultados:
                    if r.boxes:
                        for b in r.boxes:
                            if int(b.cls[0]) == 0:
                                c = int(b.conf[0] * 100)
                                if c > conf_max: conf_max = c
                
                threading.Thread(target=registrar_novedad, args=(modo_txt, conf_max, frame.copy()), daemon=True).start()
                ultimo_guardado = time.time()
        elif not amenaza_critica: alarma_silenciada_temporal = False

        # HUD TÁCTICO MINIMALISTA - Panel Superior Pequeño
        panel = frame.copy()
        alto_panel = 55
        cv2.rectangle(panel, (0, 0), (w_proc, alto_panel), (10, 15, 10), -1)
        cv2.addWeighted(panel, 0.85, frame, 0.15, 0, frame)

        t_act = time.time()
        fps = 1 / (t_act - tiempo_anterior) if tiempo_anterior > 0 else 0
        tiempo_anterior = t_act
        
        # Estilo Minimalista
        fuente = cv2.FONT_HERSHEY_SIMPLEX
        escala = 0.45
        
        # Línea 1: Info General (Izquierda)
        info_txt = f"S.A.T.A. v6.0 | MODELO: {modelo_ia[:6].upper()} | {int(fps)} FPS | {'GPU' if dispositivo==0 else 'CPU'}"
        dibujar_texto_legible(frame, info_txt, (10, 20), fuente, escala, (255, 255, 255), 1)
        
        # Línea 2: Estado (Izquierda)
        estado_txt = "ALERTA CRITICA" if amenaza_critica else "OPERATIVO"
        color_estado = (0, 0, 255) if amenaza_critica else (0, 255, 0)
        dibujar_texto_legible(frame, f"ESTADO: {estado_txt} | OBJETIVOS: {intrusos}", (10, 42), fuente, escala, color_estado, 1)

        # Instrucciones de Navegación (Derecha)
        nav_txt_1 = "[C] FOTO MANUAL | [V] MENU | [Q] SALIR"
        if modo_estatico and not modo_garita:
            nav_txt_2 = "[M] SILENCIAR | [Click Izq] ZONA | [Click Der] BORRAR"
        else:
            nav_txt_2 = "[M] SILENCIAR ALARMAS"
        
        # Calcular ancho del texto para alinear a la derecha
        (tw1, _), _ = cv2.getTextSize(nav_txt_1, fuente, escala, 1)
        (tw2, _), _ = cv2.getTextSize(nav_txt_2, fuente, escala, 1)
        
        dibujar_texto_legible(frame, nav_txt_1, (w_proc - tw1 - 15, 20), fuente, escala, (200, 200, 200), 1)
        dibujar_texto_legible(frame, nav_txt_2, (w_proc - tw2 - 15, 42), fuente, escala, (255, 200, 0), 1)

        cv2.imshow("S.A.T.A. - Visor de Operaciones", frame)
        tecla = cv2.waitKey(1) & 0xFF
        if tecla in [ord('v'), ord('V')]: 
            print("[+] Regresando al Comando Central...")
            break
        elif tecla in [ord('q'), ord('Q')]: 
            print("[!] Cierre de emergencia solicitado.")
            os._exit(0)
        elif tecla in [ord('c'), ord('C')]:
            threading.Thread(target=registrar_novedad, args=(modo_txt, "MANUAL", frame.copy()), daemon=True).start()
        elif tecla in [ord('m'), ord('M')]: 
            silencio_global = not silencio_global
            print(f"[+] Silencio Global: {'ON' if silencio_global else 'OFF'}")

    if vs: vs.release()
    cv2.destroyAllWindows()