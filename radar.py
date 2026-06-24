# S.A.V.I.A. V7.0 — MOTOR DE VISIÓN TÁCTICA (radar.py)
# MÓDULO 1: Optimización CUDA/FFMPEG + Escalado de Alta Fidelidad
# MÓDULO 2: Torreta PID + Kalman (Ultralytics bytetrack) + Arduino Serial
# ============================================================
import cv2, os, time, numpy as np, torch, threading, csv, winsound
import win32gui, win32ui, ctypes, telemetria
from datetime import datetime
from ultralytics import YOLO

# ── Comunicación Serial con Arduino (opcional) ─────────────
try:
    import serial
    SERIAL_DISPONIBLE = True
except ImportError:
    SERIAL_DISPONIBLE = False
    print("[!] pyserial no instalado. Torreta deshabilitada. Ejecute: pip install pyserial")

# ── SAHI: Inferencia por parches ───────────────────────────
try:
    from sahi import AutoDetectionModel
    from sahi.predict import get_sliced_prediction
    SAHI_DISPONIBLE = True
except ImportError:
    SAHI_DISPONIBLE = False

# ── Clases tácticas (BGR) ──────────────────────────────────
CLASES_TACTICAS = {
    0: {"nombre": "Civil",            "color": (255, 100,   0)},
    1: {"nombre": "Militar_Jaguar",   "color": (0,   200,   0)},
    2: {"nombre": "Vehiculo_Civil",   "color": (240, 240, 240)},
    3: {"nombre": "Vehiculo_Tactico", "color": (0,   140, 255)},
}
CLASES_COCO_FALLBACK = [0, 2, 3, 5, 7, 15, 16, 17, 19]

# ── Sirena continua daemon ─────────────────────────────────
alarma_critica_activa = False
_hilo_sirena_iniciado = False

def _bucle_sirena():
    while True:
        if alarma_critica_activa:
            try:
                winsound.Beep(1200, 200); time.sleep(0.15)
                winsound.Beep(900,  200); time.sleep(0.15)
            except Exception:
                time.sleep(0.5)
        else:
            time.sleep(0.3)

def _iniciar_hilo_sirena():
    global _hilo_sirena_iniciado
    if not _hilo_sirena_iniciado:
        threading.Thread(target=_bucle_sirena, daemon=True).start()
        _hilo_sirena_iniciado = True

# ── MÓDULO 1: Escalado de Alta Fidelidad ───────────────────
def _escalar_hifi(frame, target_w, target_h):
    """
    Redimensionado adaptativo de alta fidelidad:
    - INTER_AREA    : para reducir resolución (menos aliasing)
    - INTER_LANCZOS4: para ampliar (preserva bordes y nitidez)
    Mantiene proporción con letterbox negro.
    """
    h0, w0 = frame.shape[:2]
    ratio   = min(target_w / w0, target_h / h0)
    nw, nh  = int(w0 * ratio), int(h0 * ratio)

    interp  = cv2.INTER_AREA if ratio < 1.0 else cv2.INTER_LANCZOS4
    resized = cv2.resize(frame, (nw, nh), interpolation=interp)

    canvas  = np.zeros((target_h, target_w, 3), dtype=np.uint8)
    yo      = (target_h - nh) // 2
    xo      = (target_w - nw) // 2
    canvas[yo:yo+nh, xo:xo+nw] = resized
    return canvas

# ── MÓDULO 2: Torreta PID ─────────────────────────────────
class TorretaPID:
    """
    Controlador PID proporcional para Pan/Tilt de servos.
    Envía comandos "X,Y\\n" al Arduino vía Serial.
    El filtro de Kalman es provisto por Ultralytics (bytetrack).
    """
    KP = 0.05          # Constante proporcional (ajustar según montura)
    SERVO_MIN = 0      # Grados mínimos del servo
    SERVO_MAX = 180    # Grados máximos del servo
    SERVO_CENTER = 90  # Posición neutral (apuntando al frente)

    def __init__(self, puerto_com="COM3", baudios=9600):
        self.activa    = False
        self.ser       = None
        self.pan_ang   = self.SERVO_CENTER
        self.tilt_ang  = self.SERVO_CENTER
        self._lock     = threading.Lock()

        if not SERIAL_DISPONIBLE:
            print("[!] Torreta PID: pyserial no disponible.")
            return

        try:
            self.ser   = serial.Serial(puerto_com, baudios, timeout=0.1)
            self.activa = True
            print(f"[+] Torreta PID conectada en {puerto_com} a {baudios} baud.")
            # Enviar posición neutral al arrancar
            self._enviar(self.SERVO_CENTER, self.SERVO_CENTER)
        except Exception as e:
            print(f"[!] Torreta PID: no se pudo abrir {puerto_com} — {e}")

    @staticmethod
    def _clamp(val, lo, hi):
        return max(lo, min(hi, val))

    def calcular_y_enviar(self, cx_objetivo, cy_objetivo, cx_pantalla, cy_pantalla):
        """
        Calcula error de posición y aplica control proporcional.
        Se llama desde el hilo de video — NO bloquea.
        """
        if not self.activa or self.ser is None:
            return

        error_x = cx_objetivo - cx_pantalla   # positivo = objetivo a la derecha
        error_y = cy_objetivo - cy_pantalla   # positivo = objetivo abajo

        # Ajuste proporcional de ángulos
        nuevo_pan  = self.pan_ang  + self.KP * error_x
        nuevo_tilt = self.tilt_ang - self.KP * error_y  # invertir Y (servo mira arriba)

        self.pan_ang  = self._clamp(int(nuevo_pan),  self.SERVO_MIN, self.SERVO_MAX)
        self.tilt_ang = self._clamp(int(nuevo_tilt), self.SERVO_MIN, self.SERVO_MAX)

        # Enviar en hilo daemon para no bloquear el bucle de video
        threading.Thread(
            target=self._enviar,
            args=(self.pan_ang, self.tilt_ang),
            daemon=True
        ).start()

    def _enviar(self, pan, tilt):
        try:
            with self._lock:
                if self.ser and self.ser.is_open:
                    cmd = f"{pan},{tilt}\n".encode('ascii')
                    self.ser.write(cmd)
        except Exception as e:
            print(f"[!] Error serial torreta: {e}")

    def cerrar(self):
        if self.ser:
            try:
                self._enviar(self.SERVO_CENTER, self.SERVO_CENTER)
                time.sleep(0.1)
                self.ser.close()
            except Exception:
                pass

# ── Grabación de clip asíncrona ───────────────────────────
def _grabar_clip(ruta, frames, fps=15.0):
    if not frames: return
    h, w = frames[0].shape[:2]
    writer = cv2.VideoWriter(ruta, cv2.VideoWriter_fourcc(*'mp4v'), fps, (w, h))
    for f in frames: writer.write(f)
    writer.release()
    print(f"[+] Clip guardado: {ruta}")

# ── Registro CSV SALUTE + JPG ─────────────────────────────
def registrar_novedad(modo, frame, detecciones_info, coords_gps=None):
    carpeta = "Evidencia_Seguridad"
    os.makedirs(carpeta, exist_ok=True)
    fh = datetime.now()
    ts = fh.strftime('%Y%m%d_%H%M%S')
    nombre_foto = f"ALERTA_{ts}.jpg"
    cv2.imwrite(os.path.join(carpeta, nombre_foto), frame)

    unit_val = ", ".join(sorted(set(d["nombre"] for d in detecciones_info))) or "N/A"
    loc_val  = (f"LAT {coords_gps[0]:.6f}, LON {coords_gps[1]:.6f}"
                if coords_gps and coords_gps[0] is not None else "N/A - Fijo")
    csv_path = os.path.join(carpeta, "registro_novedades.csv")
    existe   = os.path.exists(csv_path)
    with open(csv_path, 'a', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        if not existe:
            w.writerow(["Archivo_Imagen", "Fecha", "Hora", "Size",
                        "Activity", "Location", "Unit", "Equipment"])
        w.writerow([nombre_foto, fh.strftime("%Y-%m-%d"), fh.strftime("%H:%M:%S"),
                    len(detecciones_info), f"Alerta en modo {modo}",
                    loc_val, unit_val,
                    f"S.A.V.I.A. V7.0 | SAHI+YOLO+PID | {modo}"])
    print(f"[!] Novedad: {nombre_foto} | {unit_val}")

# ── Captura de ventana (Modo Garita) ─────────────────────
def capturar_ventana_especifica(titulo):
    hwnd = win32gui.FindWindow(None, titulo)
    if not hwnd: return None
    l, t, r, b = win32gui.GetClientRect(hwnd)
    w, h = r - l, b - t
    if w <= 0 or h <= 0: return None
    hwndDC = win32gui.GetWindowDC(hwnd)
    mfcDC  = win32ui.CreateDCFromHandle(hwndDC)
    saveDC = mfcDC.CreateCompatibleDC()
    bmp    = win32ui.CreateBitmap()
    bmp.CreateCompatibleBitmap(mfcDC, w, h)
    saveDC.SelectObject(bmp)
    ctypes.windll.user32.PrintWindow(hwnd, saveDC.GetSafeHdc(), 2)
    info   = bmp.GetInfo()
    data   = bmp.GetBitmapBits(True)
    img    = np.frombuffer(data, dtype='uint8').reshape((info['bmHeight'], info['bmWidth'], 4))
    img    = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
    win32gui.DeleteObject(bmp.GetHandle())
    saveDC.DeleteDC(); mfcDC.DeleteDC()
    win32gui.ReleaseDC(hwnd, hwndDC)
    return _escalar_hifi(img, 1280, 720)

# ── VideoStream multihilo con aceleración FFMPEG ──────────
class VideoStream:
    def __init__(self, src, backend=cv2.CAP_ANY):
        # MÓDULO 1: Forzar latencia cero en streams RTSP/RTMP vía FFMPEG
        if backend == cv2.CAP_FFMPEG and isinstance(src, str):
            os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = (
                "rtsp_transport;udp|"
                "fflags;nobuffer|"
                "flags;low_delay"
            )
        self.cap = cv2.VideoCapture(src, backend)
        if backend == cv2.CAP_FFMPEG:
            self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        self.ret, self.frame = self.cap.read()
        self.stopped = False
        self.lock    = threading.Lock()

    def start(self):
        threading.Thread(target=self.update, daemon=True).start()
        return self

    def update(self):
        while not self.stopped:
            if not self.ret:
                self.stopped = True; return
            ret, frame = self.cap.read()
            with self.lock:
                self.ret, self.frame = ret, frame

    def read(self):
        with self.lock:
            return self.ret, self.frame

    def release(self):
        self.stopped = True
        self.cap.release()

# ── HUD: texto con fondo semitransparente ─────────────────
def _texto_bg(img, txt, pos, fuente, escala, color, grosor=1, pad=5):
    (tw, th), bl = cv2.getTextSize(txt, fuente, escala, grosor)
    x, y = pos
    ov = img.copy()
    cv2.rectangle(ov, (x-pad, y-th-pad), (x+tw+pad, y+bl+pad), (0, 0, 0), -1)
    cv2.addWeighted(ov, 0.6, img, 0.4, 0, img)
    cv2.putText(img, txt, pos, fuente, escala, (0, 0, 0), grosor+1)
    cv2.putText(img, txt, pos, fuente, escala, color, grosor)

def _es_modelo_tactico(ruta):
    try:
        m = YOLO(ruta)
        return m.names.get(1, "").lower() == "militar_jaguar"
    except Exception:
        return False

def _inferir_sahi(model, frame, sensibilidad):
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    res = get_sliced_prediction(
        rgb, model, slice_height=512, slice_width=512,
        overlap_height_ratio=0.2, overlap_width_ratio=0.2,
        perform_standard_pred=True, postprocess_type="NMM", verbose=0
    )
    out = []
    for p in res.object_prediction_list:
        if p.score.value < sensibilidad: continue
        b = p.bbox
        out.append({
            "cls":    p.category.id,
            "nombre": CLASES_TACTICAS.get(p.category.id, {}).get("nombre", p.category.name),
            "conf":   p.score.value,
            "x1": int(b.minx), "y1": int(b.miny),
            "x2": int(b.maxx), "y2": int(b.maxy),
            "id":  None,  # tracking ID (solo disponible con model.track)
        })
    return out

# ── FUNCIÓN PRINCIPAL ─────────────────────────────────────
def iniciar_radar(
    fuente_video=0, modelo_ia='yolov8n.pt',
    modo_estatico=True, modo_garita=False,
    modo_silencioso_global=False,
    usar_telemetria=False, sdk_url=None,
    zona_gps=None, sensibilidad=0.6,
    puerto_arduino="COM3", usar_torreta=False
):
    global alarma_critica_activa
    os.makedirs("Evidencia_Seguridad", exist_ok=True)
    _iniciar_hilo_sirena()

    # MÓDULO 1: CUDA
    dispositivo = 'cuda' if torch.cuda.is_available() else 'cpu'
    dev_int     = 0 if dispositivo == 'cuda' else 'cpu'
    if dispositivo == 'cuda':
        torch.backends.cudnn.benchmark    = True
        torch.backends.cudnn.deterministic = False
        print("[+] CUDA + CuDNN Benchmark: ACTIVADO")

    usar_tactico = _es_modelo_tactico(modelo_ia)
    print(f"[+] Modo clases: {'TACTICO' if usar_tactico else 'COCO-FALLBACK'}")

    # ── Motor de inferencia ────────────────────────────────
    sahi_model = None
    model_yolo = None   # Para SAHI-fallback o tracking

    if SAHI_DISPONIBLE:
        sahi_model = AutoDetectionModel.from_pretrained(
            model_type="yolov8", model_path=modelo_ia,
            confidence_threshold=sensibilidad, device=dispositivo
        )
        print("[+] Motor: SAHI 512x512 / overlap 20%")
    else:
        # Sin SAHI: usar YOLO con track + bytetrack (Kalman interno)
        model_yolo = YOLO(modelo_ia)
        if dispositivo == 'cuda':
            model_yolo.to('cuda')
            # Calentamiento FP16
            model_yolo.predict(
                np.zeros((640, 640, 3), dtype=np.uint8),
                device=dev_int, verbose=False, half=True
            )
        print("[+] Motor: YOLO+ByteTrack (Kalman interno de Ultralytics)")

    # ── MÓDULO 2: Torreta PID ──────────────────────────────
    torreta = None
    if usar_torreta and modo_estatico and not modo_garita:
        torreta = TorretaPID(puerto_com=puerto_arduino, baudios=9600)

    # ── Telemetría GPS ─────────────────────────────────────
    tele = None
    if usar_telemetria:
        tele = telemetria.DroneTelemetry(sdk_url or "udp://:14540")
        tele.start()

    # ── Conexión de video ──────────────────────────────────
    vs = None
    if not modo_garita:
        for i in range(1, 31):
            backend = cv2.CAP_FFMPEG if isinstance(fuente_video, str) else cv2.CAP_ANY
            vs = VideoStream(fuente_video, backend)
            if vs.ret: break
            vs.release()
            print(f"[+] Esperando fuente... ({i}/30)")
            time.sleep(1)
        if not vs or not vs.ret:
            print("[!] Error de conexión con la fuente de video.")
            return
        vs.start()

    # ── Ventana OpenCV ─────────────────────────────────────
    TITULO = "S.A.V.I.A. - Visor de Inteligencia Artificial"
    cv2.namedWindow(TITULO, cv2.WINDOW_NORMAL | cv2.WINDOW_KEEPRATIO)
    hwnd = win32gui.FindWindow(None, TITULO)
    if hwnd: win32gui.ShowWindow(hwnd, 3)

    modo_txt   = "DRON" if not modo_estatico else ("GARITA" if modo_garita else "CENTINELA")
    silencioso = modo_silencioso_global
    ult_guard  = 0; t_ant = 0; frame_cnt = 0
    frame_skip = 2 if dispositivo == 'cpu' else 1
    ult_det    = []
    FPS_CLIP   = 15; MAX_BUF = FPS_CLIP * 5
    buf_clip   = []; grabando = False; clip_rest = 0
    HUD        = cv2.FONT_HERSHEY_SIMPLEX

    # Centro de pantalla para PID
    CENTRO_X, CENTRO_Y = 640, 360

    while True:
        # ── Captura ────────────────────────────────────────
        if modo_garita:
            frame = capturar_ventana_especifica(fuente_video)
        else:
            ok, frame = vs.read()
            if not ok:
                black = np.zeros((720, 1280, 3), dtype=np.uint8)
                cv2.putText(black, "[!] PERDIDA DE SENAL - RECONECTANDO...",
                            (80, 360), HUD, 0.9, (0, 0, 255), 2)
                cv2.imshow(TITULO, black); cv2.waitKey(2000)
                vs.release()
                backend = cv2.CAP_FFMPEG if isinstance(fuente_video, str) else cv2.CAP_ANY
                vs = VideoStream(fuente_video, backend)
                if vs.ret: vs.start()
                continue

        if frame is None:
            if modo_garita: break
            continue

        # ── MÓDULO 1: Escalado de Alta Fidelidad ──────────
        frame = _escalar_hifi(frame, 1280, 720)

        # ── Buffer de clip ─────────────────────────────────
        if grabando:
            buf_clip.append(frame.copy())
            clip_rest -= 1
            if clip_rest <= 0: grabando = False

        # ── Inferencia con frame-skip ──────────────────────
        frame_cnt += 1
        if frame_cnt % (frame_skip + 1) == 0:
            if sahi_model:
                ult_det = _inferir_sahi(sahi_model, frame, sensibilidad)

            elif model_yolo:
                clases = list(CLASES_TACTICAS.keys()) if usar_tactico else CLASES_COCO_FALLBACK
                # MÓDULO 2: model.track con bytetrack (Kalman interno)
                try:
                    rs = model_yolo.track(
                        frame, classes=clases, conf=sensibilidad,
                        persist=True, tracker="bytetrack.yaml",
                        verbose=False,
                        device=dev_int,
                        half=(dispositivo == 'cuda')   # FP16 MÓDULO 1
                    )
                except Exception:
                    # bytetrack.yaml no encontrado — fallback a predict
                    rs = model_yolo.predict(
                        frame, classes=clases, conf=sensibilidad,
                        verbose=False, device=dev_int,
                        half=(dispositivo == 'cuda')
                    )

                ult_det = []
                for r in rs:
                    if not r.boxes: continue
                    for b in r.boxes:
                        ci = int(b.cls[0])
                        x1, y1, x2, y2 = map(int, b.xyxy[0])
                        track_id = int(b.id[0]) if b.id is not None else None
                        ult_det.append({
                            "cls":    ci,
                            "nombre": CLASES_TACTICAS.get(ci, {}).get("nombre", f"cls_{ci}"),
                            "conf":   float(b.conf[0]),
                            "x1": x1, "y1": y1, "x2": x2, "y2": y2,
                            "id":     track_id,
                        })

        # ── Dibujar detecciones + PID ──────────────────────
        amenazas = []; hay_amenaza = False
        objetivo_pid = None  # Primera amenaza válida para la torreta

        for d in ult_det:
            ci = d["cls"]
            if usar_tactico:
                col = CLASES_TACTICAS.get(ci, {"color": (128, 128, 128)})["color"]
                es  = (ci == 1)  # Solo Militar_Jaguar activa torreta
            else:
                es  = (ci == 0)
                col = (0, 200, 50) if ci == 0 else ((255, 150, 0) if ci in [2,3,5,7] else (0, 220, 220))

            if es:
                hay_amenaza = True
                amenazas.append(d)
                if objetivo_pid is None:
                    objetivo_pid = d  # Priorizar primer objetivo detectado

            # Bounding box
            cv2.rectangle(frame, (d["x1"], d["y1"]), (d["x2"], d["y2"]), col, 2)
            label = f"{d['nombre']} {int(d['conf']*100)}%"
            if d.get("id") is not None:
                label += f" #{d['id']}"
            _texto_bg(frame, label, (d["x1"], max(d["y1"]-12, 15)), HUD, 0.55, col)

        # ── MÓDULO 2: Enviar comando PID a torreta ─────────
        if torreta and objetivo_pid:
            cx_obj = (objetivo_pid["x1"] + objetivo_pid["x2"]) // 2
            cy_obj = (objetivo_pid["y1"] + objetivo_pid["y2"]) // 2
            torreta.calcular_y_enviar(cx_obj, cy_obj, CENTRO_X, CENTRO_Y)

            # Dibujar retícula de seguimiento
            cv2.line(frame, (CENTRO_X, CENTRO_Y), (cx_obj, cy_obj), (0, 255, 255), 1)
            cv2.circle(frame, (cx_obj, cy_obj), 8, (0, 255, 255), 2)
            cv2.drawMarker(frame, (CENTRO_X, CENTRO_Y),
                           (0, 255, 255), cv2.MARKER_CROSS, 20, 1)

        # ── Sirena ─────────────────────────────────────────
        alarma_critica_activa = hay_amenaza and not silencioso

        # ── Registro (cooldown 15s) ────────────────────────
        if hay_amenaza and (time.time() - ult_guard > 15):
            coords = None
            if tele:
                try:
                    pos = tele.get_position()
                    coords = (pos.latitude_deg, pos.longitude_deg) if pos else None
                except Exception:
                    pass
            snap = frame.copy()
            threading.Thread(
                target=registrar_novedad,
                args=(modo_txt, snap, amenazas, coords),
                daemon=True
            ).start()
            buf_clip.clear(); grabando = True; clip_rest = MAX_BUF
            ts_clip = datetime.now().strftime('%Y%m%d_%H%M%S')
            def _lanzar_clip(ref_buf, ts, fps):
                while grabando: time.sleep(0.05)
                _grabar_clip(
                    os.path.join("Evidencia_Seguridad", f"CLIP_{ts}.mp4"),
                    list(ref_buf), fps
                )
            threading.Thread(
                target=_lanzar_clip,
                args=(buf_clip, ts_clip, FPS_CLIP),
                daemon=True
            ).start()
            ult_guard = time.time()

        # ── HUD ────────────────────────────────────────────
        t_now = time.time()
        fps = 1.0 / (t_now - t_ant) if t_ant else 0
        t_ant = t_now
        motor = "SAHI+YOLO" if sahi_model else "YOLO+ByteTrack"
        torreta_txt = f" | TORRETA: PAN={torreta.pan_ang} TILT={torreta.tilt_ang}" if torreta and torreta.activa else ""

        _texto_bg(frame,
                  f"S.A.V.I.A. V7.0 | {modo_txt} | {modelo_ia} | {motor} | {int(fps)} FPS{torreta_txt}",
                  (15, 28), HUD, 0.55, (180, 255, 100))

        if hay_amenaza:
            cls_txt = ", ".join(sorted(set(d["nombre"] for d in amenazas)))
            _texto_bg(frame, f"ALERTA CRITICA: {cls_txt}", (15, 62), HUD, 0.62, (40, 40, 255))
        else:
            _texto_bg(frame, "SISTEMA OPERATIVO - SIN AMENAZAS", (15, 62), HUD, 0.62, (0, 220, 150))

        nav = "[C] CAPTURA  [T] TORRETA ON/OFF  [M] SILENCIAR  [V] MENU  [Q] SALIR"
        (tw, _), _ = cv2.getTextSize(nav, HUD, 0.48, 1)
        _texto_bg(frame, nav, (1265 - tw, 710), HUD, 0.48, (180, 180, 180))

        cv2.imshow(TITULO, frame)
        k = cv2.waitKey(1) & 0xFF

        if k in [ord('v'), ord('V')]:
            print("[+] Regresando al Comando Central...")
            break
        elif k in [ord('q'), ord('Q')]:
            os._exit(0)
        elif k in [ord('c'), ord('C')]:
            threading.Thread(
                target=registrar_novedad,
                args=(modo_txt, frame.copy(),
                      ult_det or [{"nombre": "MANUAL", "conf": 1.0}], None),
                daemon=True
            ).start()
        elif k in [ord('m'), ord('M')]:
            silencioso = not silencioso
            alarma_critica_activa = False
            print(f"[+] Silencio: {'ON' if silencioso else 'OFF'}")
        elif k in [ord('t'), ord('T')]:
            if torreta:
                torreta.activa = not torreta.activa
                print(f"[+] Torreta PID: {'ACTIVA' if torreta.activa else 'PAUSADA'}")

    # ── Limpieza ───────────────────────────────────────────
    alarma_critica_activa = False
    if torreta: torreta.cerrar()
    if vs:      vs.release()
    cv2.destroyAllWindows()