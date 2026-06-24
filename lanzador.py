# ============================================================
# S.A.V.I.A. V7.0 — COMMAND CENTER (ESMIL)
# Paleta Dark Navy | Ámbar | Pizarra
# Refactorizado: bugs corregidos, eficiencia mejorada,
# descargador de modelos integrado.
# ============================================================

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import socket, threading, subprocess, os, time, glob, shutil, json, urllib.request
import win32gui, psutil
import radar, telemetria, reporteador
from datetime import datetime
from PIL import Image, ImageTk

# ── Paleta de colores ─────────────────────────────────────
BG_BASE   = "#0B131E"   # Dark Navy — fondo principal
BG_PANEL  = "#1E293B"   # Azul pizarra — paneles
BG_INNER  = "#0F1F33"   # Fondo interior de controles
ACCENT    = "#F59E0B"   # Ámbar — acción principal
ACCENT2   = "#38BDF8"   # Cyan — info / telemetría
TEXT_PRI  = "#E2E8F0"   # Blanco pizarra
TEXT_MUT  = "#94A3B8"   # Gris pizarra (muted)
DANGER    = "#EF4444"   # Rojo — salida / peligro
SUCCESS   = "#22C55E"   # Verde — operativo
BORDER    = "#334155"   # Borde sutil
WARN      = "#FB923C"   # Naranja — advertencia

# ── Catálogo de modelos descargables ──────────────────────
# Fuente oficial: Ultralytics GitHub Releases (Air-Gapped: cache local)
MODELOS_CATALOGO = [
    # YOLOv8 — equilibrio velocidad/precisión (recomendado campo)
    {"nombre": "YOLOv8 Nano  (yolov8n) — Más rápido, ideal CPU",
     "archivo": "yolov8n.pt",
     "url": "https://github.com/ultralytics/assets/releases/download/v8.3.0/yolov8n.pt",
     "tam": "6 MB",  "mAP": "37.3"},
    {"nombre": "YOLOv8 Small (yolov8s) — Balance velocidad/precisión",
     "archivo": "yolov8s.pt",
     "url": "https://github.com/ultralytics/assets/releases/download/v8.3.0/yolov8s.pt",
     "tam": "22 MB", "mAP": "44.9"},
    {"nombre": "YOLOv8 Medium (yolov8m) — Mayor precisión",
     "archivo": "yolov8m.pt",
     "url": "https://github.com/ultralytics/assets/releases/download/v8.3.0/yolov8m.pt",
     "tam": "52 MB", "mAP": "50.2"},
    {"nombre": "YOLOv8 Large (yolov8l) — Alta precisión, requiere GPU",
     "archivo": "yolov8l.pt",
     "url": "https://github.com/ultralytics/assets/releases/download/v8.3.0/yolov8l.pt",
     "tam": "87 MB", "mAP": "52.9"},
    # YOLOv10 — sin NMS, latencia reducida
    {"nombre": "YOLOv10 Nano (yolov10n) — Sin NMS, ultra rápido",
     "archivo": "yolov10n.pt",
     "url": "https://github.com/ultralytics/assets/releases/download/v8.3.0/yolov10n.pt",
     "tam": "5 MB",  "mAP": "38.5"},
    {"nombre": "YOLOv10 Small (yolov10s) — Sin NMS, balance",
     "archivo": "yolov10s.pt",
     "url": "https://github.com/ultralytics/assets/releases/download/v8.3.0/yolov10s.pt",
     "tam": "16 MB", "mAP": "46.3"},
    {"nombre": "YOLOv10 Medium (yolov10m) — Sin NMS, buena precisión",
     "archivo": "yolov10m.pt",
     "url": "https://github.com/ultralytics/assets/releases/download/v8.3.0/yolov10m.pt",
     "tam": "32 MB", "mAP": "51.1"},
    # YOLOv11 — arquitectura más reciente
    {"nombre": "YOLOv11 Nano (yolo11n) — Arquitectura 2024, ultra ligero",
     "archivo": "yolo11n.pt",
     "url": "https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11n.pt",
     "tam": "5 MB",  "mAP": "39.5"},
    {"nombre": "YOLOv11 Small (yolo11s) — Arquitectura 2024",
     "archivo": "yolo11s.pt",
     "url": "https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11s.pt",
     "tam": "19 MB", "mAP": "47.0"},
    {"nombre": "YOLOv11 Medium (yolo11m) — Arquitectura 2024, precisión alta",
     "archivo": "yolo11m.pt",
     "url": "https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11m.pt",
     "tam": "38 MB", "mAP": "51.5"},
]

# ─────────────────────────────────────────────────────────
# UTILIDADES
# ─────────────────────────────────────────────────────────
def obtener_ip_local() -> str:
    """Obtiene la IP local del equipo para construir la URL RTMP."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"

def limpiar_evidencia_antigua():
    """Elimina capturas de más de 5 días para liberar espacio en campo."""
    carpeta = "Evidencia_Seguridad"
    if not os.path.exists(carpeta):
        return
    limite = time.time() - 5 * 24 * 3600
    for nombre in os.listdir(carpeta):
        if nombre.startswith("ALERTA_") and nombre.endswith((".jpg", ".png")):
            ruta = os.path.join(carpeta, nombre)
            try:
                if os.path.getmtime(ruta) < limite:
                    os.remove(ruta)
            except OSError:
                pass

def mediamtx_en_ejecucion() -> bool:
    """Verifica si el servidor RTMP/RTSP MediaMTX ya está corriendo."""
    for proc in psutil.process_iter(["name"]):
        try:
            if "mediamtx" in (proc.info.get("name") or "").lower():
                return True
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return False

def lanzar_mediamtx():
    """Inicia MediaMTX en segundo plano si existe el ejecutable."""
    if not os.path.exists("mediamtx.exe"):
        return False
    if mediamtx_en_ejecucion():
        return True
    with open("mediamtx.yml", "w") as f:
        f.write("paths:\n  all_others:\n  live/dron:\n")
    subprocess.Popen(
        ["mediamtx.exe", "mediamtx.yml"],
        creationflags=subprocess.CREATE_NEW_CONSOLE
    )
    return True

def confirmar_salida():
    """Diálogo de confirmación antes de cerrar el sistema."""
    if messagebox.askyesno(
        "CONFIRMAR SALIDA",
        "¿Confirmar cierre del Sistema Centinela?\n\nSe detendran todos los procesos activos.",
        icon="warning"
    ):
        ventana.quit()

# ─────────────────────────────────────────────────────────
# ACCIÓN: REPORTE SALUTE (hilo daemon — no bloquea GUI)
# ─────────────────────────────────────────────────────────
def ejecutar_reporte_salute():
    """Genera el reporte SALUTE de la última novedad en hilo separado."""
    def _gen():
        try:
            ruta = reporteador.generar_reporte()
            msg  = f"Reporte generado exitosamente.\n\n{ruta}"
            ventana.after(0, lambda: messagebox.showinfo("REPORTE SALUTE", msg))
            try:
                os.startfile(ruta)
            except OSError:
                pass
        except Exception as ex:
            err = str(ex)
            ventana.after(0, lambda: messagebox.showerror("ERROR REPORTE", err))
    threading.Thread(target=_gen, daemon=True).start()

# ─────────────────────────────────────────────────────────
# DESCARGADOR DE MODELOS IA
# ─────────────────────────────────────────────────────────
def abrir_descargador_modelos():
    """
    Abre una ventana con el catálogo de modelos YOLO oficiales de Ultralytics.
    Permite descargar directamente al directorio de trabajo.
    """
    top = tk.Toplevel(ventana)
    top.title("S.A.V.I.A. — Centro de Modelos IA")
    top.configure(bg=BG_BASE)
    top.resizable(False, False)
    top.grab_set()  # Modal

    # Cabecera
    tk.Label(top, text="CENTRO DE MODELOS DE INTELIGENCIA ARTIFICIAL",
             bg=BG_BASE, fg=ACCENT, font=("Segoe UI", 13, "bold")).pack(pady=(18, 2))
    tk.Label(top, text="Modelos oficiales de Ultralytics (COCO, 80 clases)",
             bg=BG_BASE, fg=TEXT_MUT, font=("Segoe UI", 9)).pack()
    tk.Label(top, text="Para deteccion tactica, entrena tu propio modelo con las 4 clases militares.",
             bg=BG_BASE, fg=WARN, font=("Segoe UI", 8, "italic")).pack(pady=(0, 10))

    # Frame de lista
    frame_lista = tk.Frame(top, bg=BG_PANEL, bd=1, relief="flat",
                           highlightbackground=BORDER, highlightthickness=1)
    frame_lista.pack(fill="both", padx=20, pady=4)

    # Encabezados de columna
    hdr = tk.Frame(frame_lista, bg=BG_INNER)
    hdr.pack(fill="x")
    for txt, w in [("Modelo", 38), ("Tamaño", 7), ("mAP50-95", 9), ("Estado", 10)]:
        tk.Label(hdr, text=txt, bg=BG_INNER, fg=ACCENT2,
                 font=("Segoe UI", 9, "bold"), width=w, anchor="w").pack(side="left", padx=4)

    # Filas de modelos
    filas = []
    for modelo in MODELOS_CATALOGO:
        ya_existe = os.path.exists(modelo["archivo"])
        fg_row = SUCCESS if ya_existe else TEXT_PRI

        row = tk.Frame(frame_lista, bg=BG_PANEL, cursor="hand2")
        row.pack(fill="x", pady=1)
        row.bind("<Enter>", lambda e, r=row: r.configure(bg=BG_INNER))
        row.bind("<Leave>", lambda e, r=row: r.configure(bg=BG_PANEL))

        lbl_nombre = tk.Label(row, text=modelo["nombre"][:50], bg=BG_PANEL,
                              fg=fg_row, font=("Segoe UI", 9), anchor="w", width=38)
        lbl_nombre.pack(side="left", padx=4)
        tk.Label(row, text=modelo["tam"], bg=BG_PANEL, fg=TEXT_MUT,
                 font=("Segoe UI", 9), width=7).pack(side="left")
        tk.Label(row, text=modelo["mAP"], bg=BG_PANEL, fg=TEXT_MUT,
                 font=("Segoe UI", 9), width=9).pack(side="left")

        estado_txt = "✓ LISTO" if ya_existe else "Descargar"
        estado_col = SUCCESS if ya_existe else ACCENT
        lbl_estado = tk.Label(row, text=estado_txt, bg=BG_PANEL,
                              fg=estado_col, font=("Segoe UI", 9, "bold"), width=10)
        lbl_estado.pack(side="left", padx=6)

        filas.append({
            "modelo":    modelo,
            "row":       row,
            "lbl_nom":   lbl_nombre,
            "lbl_est":   lbl_estado,
        })

        # Click en fila → seleccionar
        for w in [row, lbl_nombre, lbl_estado]:
            w.bind("<Button-1>", lambda e, idx=len(filas)-1: _seleccionar(idx))

    # Barra de progreso
    frame_prog = tk.Frame(top, bg=BG_BASE)
    frame_prog.pack(fill="x", padx=20, pady=(8, 2))
    lbl_prog = tk.Label(frame_prog, text="Selecciona un modelo para descargarlo.",
                        bg=BG_BASE, fg=TEXT_MUT, font=("Segoe UI", 9))
    lbl_prog.pack(anchor="w")
    barra = ttk.Progressbar(frame_prog, orient="horizontal", length=560,
                            mode="determinate", maximum=100)
    barra.pack(fill="x", pady=4)

    # Botones
    frame_btns = tk.Frame(top, bg=BG_BASE)
    frame_btns.pack(pady=12)

    _seleccion = {"idx": None}

    btn_dl = ModernButton(frame_btns, text="⬇  DESCARGAR MODELO",
                          bg=ACCENT, fg=BG_BASE, hover_bg="#D97706",
                          font=("Segoe UI", 11, "bold"), width=24, pady=6,
                          state="disabled", command=lambda: _descargar())
    btn_dl.pack(side="left", padx=8)

    ModernButton(frame_btns, text="✕ Cerrar",
                 bg=BG_PANEL, fg=TEXT_MUT, hover_bg=BORDER,
                 font=("Segoe UI", 10), width=12,
                 command=top.destroy).pack(side="left", padx=4)

    def _seleccionar(idx: int):
        _seleccion["idx"] = idx
        for i, fila in enumerate(filas):
            color = BG_INNER if i == idx else BG_PANEL
            fila["row"].configure(bg=color)
            for child in fila["row"].winfo_children():
                child.configure(bg=color)
        modelo = filas[idx]["modelo"]
        ya = os.path.exists(modelo["archivo"])
        lbl_prog.configure(
            text=f"Seleccionado: {modelo['archivo']}  |  Tamaño: {modelo['tam']}  |  mAP: {modelo['mAP']}"
        )
        btn_dl.configure(
            state="disabled" if ya else "normal",
            text="✓ Ya descargado" if ya else "⬇  DESCARGAR MODELO"
        )

    def _descargar():
        idx = _seleccion["idx"]
        if idx is None:
            return
        modelo = filas[idx]["modelo"]
        archivo = modelo["archivo"]
        url     = modelo["url"]

        if os.path.exists(archivo):
            messagebox.showinfo("Modelo", f"{archivo} ya existe en el directorio.")
            return

        btn_dl.configure(state="disabled", text="Descargando...")
        barra["value"] = 0
        lbl_prog.configure(text=f"Descargando {archivo}...", fg=ACCENT2)

        def _tarea():
            try:
                tmp = archivo + ".tmp"

                def _progreso(bloque, tam_bloque, tam_total):
                    if tam_total > 0:
                        pct = min(100, bloque * tam_bloque * 100 / tam_total)
                        mb_dl = bloque * tam_bloque / 1_048_576
                        mb_tot = tam_total / 1_048_576
                        top.after(0, lambda p=pct, d=mb_dl, t=mb_tot: _actualizar_barra(p, d, t))

                urllib.request.urlretrieve(url, tmp, _progreso)
                os.rename(tmp, archivo)

                top.after(0, lambda: _finalizar_ok(idx, archivo))
            except Exception as e:
                if os.path.exists(archivo + ".tmp"):
                    try:
                        os.remove(archivo + ".tmp")
                    except OSError:
                        pass
                err = str(e)
                top.after(0, lambda: _finalizar_error(err))

        threading.Thread(target=_tarea, daemon=True).start()

    def _actualizar_barra(pct, mb_dl, mb_tot):
        barra["value"] = pct
        lbl_prog.configure(
            text=f"Descargando... {mb_dl:.1f} / {mb_tot:.1f} MB  ({int(pct)}%)"
        )

    def _finalizar_ok(idx: int, archivo: str):
        barra["value"] = 100
        lbl_prog.configure(text=f"✓ {archivo} descargado correctamente.", fg=SUCCESS)
        filas[idx]["lbl_est"].configure(text="✓ LISTO", fg=SUCCESS)
        btn_dl.configure(text="✓ Ya descargado", state="disabled")
        # Actualizar combo de modelos en la ventana principal
        actualizar_combo_modelos()
        messagebox.showinfo("Descarga completa",
                            f"Modelo '{archivo}' listo para usar.\n"
                            "Seleccionalo en el panel [3] NUCLEO DE INTELIGENCIA.")

    def _finalizar_error(err: str):
        barra["value"] = 0
        lbl_prog.configure(text=f"Error: {err}", fg=DANGER)
        btn_dl.configure(text="⬇  DESCARGAR MODELO", state="normal")
        messagebox.showerror("Error de descarga",
                             f"No se pudo descargar el modelo.\n\n{err}\n\n"
                             "Verifique la conexion a internet.")

# ─────────────────────────────────────────────────────────
# BÓVEDA DE INTELIGENCIA
# ─────────────────────────────────────────────────────────
def abrir_boveda():
    """Visor multimedia de evidencias tácticas (JPG, PNG, MP4)."""
    import cv2 as _cv2

    top = tk.Toplevel(ventana)
    top.title("V.I.B. — Visor de Inteligencia Tactica")
    top.state("zoomed")
    top.configure(bg=BG_BASE)

    paned = tk.PanedWindow(top, orient="horizontal", bg=BG_PANEL, sashwidth=4)
    paned.pack(fill="both", expand=True)
    fl = tk.Frame(paned, bg=BG_PANEL, width=300)
    fv = tk.Frame(paned, bg=BG_BASE)
    paned.add(fl)
    paned.add(fv)

    # ── Panel izquierdo ───────────────────────────────────
    tk.Label(fl, text="EVIDENCIAS TACTICAS", bg=BG_PANEL, fg=ACCENT,
             font=("Segoe UI", 11, "bold")).pack(pady=(12, 2))
    tk.Label(fl, text="JPG / PNG / MP4", bg=BG_PANEL, fg=TEXT_MUT,
             font=("Segoe UI", 8)).pack()

    lista = tk.Listbox(fl, bg=BG_INNER, fg=TEXT_MUT,
                       selectbackground=ACCENT, selectforeground=BG_BASE,
                       font=("Consolas", 10), borderwidth=0,
                       highlightthickness=1, highlightcolor=ACCENT,
                       highlightbackground=BORDER, activestyle="none")
    lista.pack(fill="both", expand=True, padx=8, pady=(4, 8))

    # ── Panel derecho: visor + botones ───────────────────
    lbl_img = tk.Label(fv, bg=BG_BASE,
                       text="Selecciona una evidencia de la lista",
                       fg=TEXT_MUT, font=("Segoe UI", 12))
    lbl_img.pack(fill="both", expand=True, padx=20, pady=(20, 8))

    frame_btns = tk.Frame(fv, bg=BG_BASE)
    frame_btns.pack(fill="x", padx=20, pady=(0, 14))

    btn_reproducir = ModernButton(
        frame_btns, text="▶  REPRODUCIR VIDEO",
        bg=BG_PANEL, fg=SUCCESS, hover_bg=BORDER,
        font=("Segoe UI", 10, "bold"), state="disabled"
    )
    btn_reproducir.pack(side="left", padx=(0, 6), pady=4, fill="x", expand=True)

    btn_salute = ModernButton(
        frame_btns, text="📄 REPORTE SALUTE",
        bg="#1C1208", fg=ACCENT, hover_bg="#2D1E0A",
        font=("Segoe UI", 10, "bold"), state="disabled"
    )
    btn_salute.pack(side="left", padx=(0, 6), pady=4, fill="x", expand=True)

    btn_mover = ModernButton(
        frame_btns, text="📁 CLASIFICAR",
        bg=BG_PANEL, fg=ACCENT2, hover_bg=BORDER,
        font=("Segoe UI", 10, "bold"), state="disabled"
    )
    btn_mover.pack(side="left", pady=4, fill="x", expand=True)

    _estado = {"nombre": None}

    def _cargar():
        lista.delete(0, "end")
        _limpiar_visor()
        if not os.path.exists("Evidencia_Seguridad"):
            return
        exts = (".jpg", ".png", ".mp4")
        archivos = sorted(
            [f for f in os.listdir("Evidencia_Seguridad")
             if f.lower().endswith(exts)],
            reverse=True
        )
        for f in archivos:
            prefijo = "▶ " if f.lower().endswith(".mp4") else "🖼 "
            lista.insert("end", f"{prefijo}{f}")

    def _nombre_real(entrada: str) -> str:
        return entrada.replace("▶ ", "").replace("🖼 ", "").strip()

    def _limpiar_visor():
        lbl_img.configure(image="",
                          text="Selecciona una evidencia de la lista",
                          fg=TEXT_MUT, font=("Segoe UI", 12))
        lbl_img.image = None
        for b in [btn_reproducir, btn_salute, btn_mover]:
            b.configure(state="disabled", command=lambda: None)
        _estado["nombre"] = None

    def _ver(event=None):
        sel = lista.curselection()
        if not sel:
            return
        nombre   = _nombre_real(lista.get(sel[0]))
        ruta     = os.path.join("Evidencia_Seguridad", nombre)
        es_video = nombre.lower().endswith(".mp4")
        _estado["nombre"] = nombre

        if not os.path.exists(ruta):
            lbl_img.configure(image="", text="[Archivo no encontrado]",
                              fg=DANGER, font=("Segoe UI", 12))
            return

        if es_video:
            try:
                cap = _cv2.VideoCapture(ruta)
                ok, frame = cap.read()
                cap.release()
                if ok and frame is not None:
                    from PIL import Image as _PI, ImageDraw, ImageFont
                    rgb  = _cv2.cvtColor(frame, _cv2.COLOR_BGR2RGB)
                    img  = _PI.fromarray(rgb)
                    wv   = max(fv.winfo_width() - 60, 600)
                    hv   = max(fv.winfo_height() - 160, 400)
                    img.thumbnail((wv, hv), _PI.Resampling.LANCZOS)
                    draw = ImageDraw.Draw(img)
                    try:
                        font = ImageFont.truetype("segoeui.ttf", 18)
                    except Exception:
                        font = ImageFont.load_default()
                    txt = "▶  VIDEO TACTICO — Clic en REPRODUCIR"
                    draw.text((11, 11), txt, fill=(0, 0, 0),      font=font)
                    draw.text((10, 10), txt, fill=(245, 158, 11), font=font)
                    ph = ImageTk.PhotoImage(img)
                    lbl_img.configure(image=ph, text="")
                    lbl_img.image = ph
                else:
                    lbl_img.configure(image="",
                                      text="▶ VIDEO (sin previsualización disponible)",
                                      fg=ACCENT, font=("Segoe UI", 13, "bold"))
                    lbl_img.image = None
            except Exception as e:
                lbl_img.configure(image="",
                                  text=f"▶ VIDEO\n[Error: {e}]",
                                  fg=TEXT_MUT)
                lbl_img.image = None
            btn_reproducir.configure(
                state="normal",
                command=lambda r=ruta: os.startfile(r)
            )
        else:
            try:
                img = Image.open(ruta)
                wv  = max(fv.winfo_width() - 60, 600)
                hv  = max(fv.winfo_height() - 160, 400)
                img.thumbnail((wv, hv), Image.Resampling.LANCZOS)
                ph  = ImageTk.PhotoImage(img)
                lbl_img.configure(image=ph, text="")
                lbl_img.image = ph
            except Exception as e:
                lbl_img.configure(image="",
                                  text=f"[Error al cargar imagen: {e}]",
                                  fg=DANGER)
                lbl_img.image = None
            btn_reproducir.configure(state="disabled", command=lambda: None)

        btn_salute.configure(state="normal",
                             command=lambda n=nombre: _generar_salute(n))
        btn_mover.configure(state="normal",
                            command=lambda n=nombre: _clasificar(n))

    def _generar_salute(nombre: str):
        def _tarea():
            ok, resultado = reporteador.generar_pdf(nombre)
            if ok:
                msg = f"Reporte generado exitosamente.\n\n{resultado}"
                top.after(0, lambda: messagebox.showinfo("REPORTE SALUTE", msg))
                try:
                    os.startfile(resultado)
                except OSError:
                    pass
            else:
                err = resultado
                top.after(0, lambda: messagebox.showerror("ERROR REPORTE", err))
        threading.Thread(target=_tarea, daemon=True).start()

    def _clasificar(nombre: str):
        dest = "Evidencia_Clasificada"
        os.makedirs(dest, exist_ok=True)
        src  = os.path.join("Evidencia_Seguridad", nombre)
        dst  = os.path.join(dest, nombre)
        try:
            os.rename(src, dst)
            messagebox.showinfo("OPSEC", f"'{nombre}' movido a Boveda Clasificada.")
        except OSError as e:
            messagebox.showerror("Error", f"No se pudo mover: {e}")
            return
        _limpiar_visor()
        _cargar()

    lista.bind("<<ListboxSelect>>", _ver)
    _cargar()

# ─────────────────────────────────────────────────────────
# MODELOS: listado dinámico de .pt locales
# ─────────────────────────────────────────────────────────
def obtener_modelos() -> list:
    modelos = glob.glob("*.pt")
    return sorted(modelos) if modelos else ["-- No hay modelos .pt --"]

def actualizar_combo_modelos():
    modelos = obtener_modelos()
    combo_modelo["values"] = modelos
    if modelos[0].endswith(".pt"):
        # Priorizar yolov10n > yolov8n > cualquier otro
        preferidos = ["yolov10n.pt", "yolo11n.pt", "yolov8n.pt"]
        for pref in preferidos:
            if pref in modelos:
                combo_modelo.set(pref)
                return
        combo_modelo.current(0)
    else:
        combo_modelo.set(modelos[0])

def importar_modelo():
    fp = filedialog.askopenfilename(
        title="Importar Modelo YOLO (.pt)",
        filetypes=[("YOLO Models", "*.pt")]
    )
    if fp:
        fn   = os.path.basename(fp)
        dest = os.path.join(os.getcwd(), fn)
        if not os.path.exists(dest):
            shutil.copy2(fp, dest)
            messagebox.showinfo("Importado", f"Modelo '{fn}' importado correctamente.")
        else:
            messagebox.showinfo("Info", f"'{fn}' ya existe en el directorio.")
        actualizar_combo_modelos()

# ─────────────────────────────────────────────────────────
# VENTANAS GARITA: filtradas (visibles, >100x100 px)
# ─────────────────────────────────────────────────────────
ventanas_lista: list = []

def actualizar_ventanas():
    ventanas_lista.clear()
    def _enum(hwnd, _):
        if not win32gui.IsWindowVisible(hwnd):
            return
        texto = win32gui.GetWindowText(hwnd)
        if not texto:
            return
        try:
            l, t, r, b = win32gui.GetClientRect(hwnd)
            if (r - l) > 100 and (b - t) > 100:
                ventanas_lista.append(texto)
        except Exception:
            pass
    win32gui.EnumWindows(_enum, None)
    combo_ventanas["values"] = ventanas_lista
    if ventanas_lista:
        combo_ventanas.current(0)

# ─────────────────────────────────────────────────────────
# CONTROLES DINÁMICOS POR MODO
# ─────────────────────────────────────────────────────────
def actualizar_controles_por_modo(*_):
    modo = var_mision.get()
    if modo == 1:   # DRON
        marco_tele.pack(fill="x", pady=8)
        # marco_torreta: DESACTIVADO — activar cuando se disponga del Arduino
        combo_fuente["values"] = ["Stream RTMP/RTSP/UDP"]
        combo_fuente.current(0)
        combo_fuente.configure(state="disabled")
        label_url.configure(text="Enlace del dron (RTMP/RTSP):")
        entry_url.configure(state="normal")
        frame_garita.pack_forget()
    elif modo == 2:  # CENTINELA
        marco_tele.pack_forget()
        combo_fuente["values"] = [
            "Camara USB 0",
            "Camara USB 1",
            "Stream Externo (RTMP/RTSP)",
        ]
        combo_fuente.configure(state="readonly")
        if combo_fuente.get() not in combo_fuente["values"]:
            combo_fuente.current(0)
        label_url.configure(text="Enlace de stream (si aplica):")
        frame_garita.pack_forget()
        actualizar_controles_por_fuente()
    else:            # GARITA
        marco_tele.pack_forget()
        combo_fuente.configure(state="disabled")
        entry_url.configure(state="disabled")
        label_url.configure(text="Seleccione aplicacion objetivo:")
        frame_garita.pack(fill="x", padx=12, pady=4)

def actualizar_controles_por_fuente(*_):
    fuente = combo_fuente.get()
    if any(k in fuente for k in ("Stream", "RTMP", "RTSP")):
        entry_url.configure(state="normal")
    else:
        entry_url.configure(state="disabled")

# ─────────────────────────────────────────────────────────
# INICIO DE MISIÓN
# ─────────────────────────────────────────────────────────
def iniciar_mision():
    mision_id       = var_mision.get()
    fuente_sel      = combo_fuente.get()
    modelo_alias    = combo_modelo.get()
    modo_silencioso = var_silencio.get()
    ventana_obj     = combo_ventanas.get()
    enlace          = entry_url.get().strip()
    usar_tele       = var_telemetria.get()
    sdk_url         = entry_sdk_url.get().strip()
    sensibilidad    = var_sensibilidad.get() / 100.0
    usar_torreta    = False   # TORRETA DESACTIVADA — reactivar con Arduino
    puerto_arduino  = "COM3"

    if not modelo_alias or not modelo_alias.endswith(".pt"):
        messagebox.showerror("Sin Modelo",
                             "Selecciona un modelo .pt valido.\n"
                             "Usa el boton '⬇ MODELOS IA' para descargar uno.")
        return

    fuente_final = 0
    es_estatico  = False
    modo_garita  = False

    if mision_id == 3:   # GARITA
        if not ventana_obj:
            messagebox.showerror("Error", "Selecciona una ventana objetivo.")
            return
        modo_garita  = True
        fuente_final = ventana_obj

    elif mision_id == 1:  # DRON
        if not enlace:
            messagebox.showerror("Error", "Ingresa el enlace RTMP/RTSP del dron.")
            return
        fuente_final = enlace
        if enlace.lower().startswith("rtmp://"):
            lanzar_mediamtx()

    else:                 # CENTINELA
        if "USB 0" in fuente_sel:
            fuente_final = 0
        elif "USB 1" in fuente_sel:
            fuente_final = 1
        else:
            if not enlace:
                messagebox.showerror("Error", "Ingresa el enlace de stream externo.")
                return
            fuente_final = enlace
            if enlace.lower().startswith("rtmp://"):
                lanzar_mediamtx()
        es_estatico = True

    ventana.withdraw()
    try:
        radar.iniciar_radar(
            fuente_video=fuente_final,
            modelo_ia=modelo_alias,
            modo_estatico=es_estatico,
            modo_garita=modo_garita,
            modo_silencioso_global=modo_silencioso,
            usar_telemetria=usar_tele,
            sdk_url=sdk_url,
            sensibilidad=sensibilidad,
            puerto_arduino=puerto_arduino,
            usar_torreta=usar_torreta,
        )
    finally:
        ventana.deiconify()
        try:
            ventana.state("zoomed")
        except Exception:
            ventana.attributes("-fullscreen", True)
        actualizar_ventanas()

# ─────────────────────────────────────────────────────────
# COMPONENTE: Botón Moderno con hover
# ─────────────────────────────────────────────────────────
class ModernButton(tk.Button):
    def __init__(self, master, hover_bg=None, **kwargs):
        self._bg_base  = kwargs.get("bg", BG_PANEL)
        self._bg_hover = hover_bg or BG_INNER
        kwargs.setdefault("relief", "flat")
        kwargs.setdefault("font",   ("Segoe UI", 11, "bold"))
        kwargs.setdefault("cursor", "hand2")
        kwargs.setdefault("pady",   8)
        kwargs.setdefault("borderwidth", 0)
        super().__init__(master, **kwargs)
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)

    def _on_enter(self, _):
        if str(self["state"]) != "disabled":
            self.configure(bg=self._bg_hover)

    def _on_leave(self, _):
        if str(self["state"]) != "disabled":
            self.configure(bg=self._bg_base)

# ─────────────────────────────────────────────────────────
# CONSTRUCCIÓN DE LA VENTANA PRINCIPAL
# ─────────────────────────────────────────────────────────
ventana = tk.Tk()
ventana.title("S.A.V.I.A. v7.0  |  Sistema Centinela — ESMIL")
ventana.configure(bg=BG_BASE)
try:
    ventana.state("zoomed")
except Exception:
    ventana.attributes("-fullscreen", True)
ventana.bind("<Escape>", lambda e: ventana.state("normal"))
ventana.protocol("WM_DELETE_WINDOW", confirmar_salida)

# Estilos TTK
style = ttk.Style()
style.theme_use("clam")
style.configure("TCombobox",
                fieldbackground=BG_INNER, background=BG_PANEL,
                foreground=TEXT_PRI, bordercolor=BORDER, arrowcolor=ACCENT,
                selectbackground=BG_INNER, selectforeground=TEXT_PRI)
style.map("TCombobox",
          fieldbackground=[("readonly", BG_INNER)],
          foreground=[("readonly", TEXT_PRI)])
style.configure("TProgressbar",
                troughcolor=BG_INNER, background=ACCENT,
                bordercolor=BORDER, lightcolor=ACCENT, darkcolor=ACCENT)

# ── Contenedor principal centrado ─────────────────────────
main = tk.Frame(ventana, bg=BG_BASE)
main.place(relx=0.5, rely=0.5, anchor="center")

# ── Cabecera ──────────────────────────────────────────────
hdr = tk.Frame(main, bg=BG_BASE)
hdr.pack(pady=(0, 16))
tk.Label(hdr, text="SISTEMA CENTINELA — ESMIL",
         bg=BG_BASE, fg=ACCENT, font=("Segoe UI", 10, "bold")).pack()
tk.Label(hdr, text="S.A.V.I.A. COMMAND CENTER",
         bg=BG_BASE, fg=TEXT_PRI, font=("Segoe UI", 32, "bold")).pack()
tk.Label(hdr, text="Sistema de Asistencia Visual e Inteligencia Artificial  v7.0",
         bg=BG_BASE, fg=TEXT_MUT, font=("Segoe UI", 10, "italic")).pack(pady=(0, 4))

# ── Cuerpo: 2 columnas ────────────────────────────────────
body  = tk.Frame(main, bg=BG_BASE)
body.pack(padx=16)
left  = tk.Frame(body, bg=BG_BASE)
left.grid(row=0, column=0, padx=16, sticky="n")
right = tk.Frame(body, bg=BG_BASE)
right.grid(row=0, column=1, padx=16, sticky="n")

def _lf(parent, titulo: str) -> tk.LabelFrame:
    return tk.LabelFrame(
        parent, text=f"  {titulo}  ",
        bg=BG_PANEL, fg=ACCENT,
        font=("Segoe UI", 10, "bold"),
        padx=14, pady=10, bd=1,
        highlightbackground=BORDER, highlightthickness=1
    )

def _lbl(parent, texto: str):
    tk.Label(parent, text=texto, bg=BG_PANEL, fg=TEXT_MUT,
             font=("Segoe UI", 9)).pack(anchor="w")

# ── [1] TIPO DE OPERACIÓN ─────────────────────────────────
marco_mision = _lf(left, "[1] TIPO DE OPERACION")
marco_mision.pack(fill="x", pady=8)
var_mision = tk.IntVar(value=2)   # Default: CENTINELA
for txt, val in [
    ("MODO DRON:      Patrullaje UAS / Drone FPV", 1),
    ("MODO CENTINELA: Camara Fija / Stream", 2),
    ("MODO GARITA:    Analisis de Ventana App", 3),
]:
    tk.Radiobutton(
        marco_mision, text=txt, variable=var_mision, value=val,
        bg=BG_PANEL, fg=TEXT_PRI, selectcolor=BG_INNER,
        activebackground=BG_PANEL, activeforeground=ACCENT,
        font=("Segoe UI", 10),
        command=actualizar_controles_por_modo
    ).pack(anchor="w", pady=3)

# ── [2] ENTRADA DE VÍDEO ──────────────────────────────────
marco_fuente = _lf(left, "[2] ENTRADA DE VIDEO")
marco_fuente.pack(fill="x", pady=8)
label_url = tk.Label(marco_fuente, text="Fuente de video:",
                     bg=BG_PANEL, fg=TEXT_MUT, font=("Segoe UI", 9))
label_url.pack(anchor="w")
combo_fuente = ttk.Combobox(marco_fuente, width=44, state="readonly",
                             font=("Segoe UI", 10))
combo_fuente.pack(pady=4)
entry_url = tk.Entry(marco_fuente, width=44, bg=BG_INNER, fg=ACCENT2,
                     insertbackground="white", relief="flat",
                     font=("Consolas", 10), justify="center")
entry_url.insert(0, f"rtmp://{obtener_ip_local()}:1935/live/dron")
entry_url.pack(pady=6, ipady=4)

frame_garita = tk.Frame(marco_fuente, bg=BG_PANEL)
combo_ventanas = ttk.Combobox(frame_garita, state="readonly", width=30,
                               font=("Segoe UI", 10))
combo_ventanas.pack(side="left")
ModernButton(frame_garita, text="↻", width=3, pady=2,
             bg=BG_INNER, fg=TEXT_PRI, hover_bg=BORDER,
             command=actualizar_ventanas).pack(side="left", padx=4)

# ── [3] NÚCLEO DE INTELIGENCIA ────────────────────────────
marco_ia = _lf(right, "[3] NUCLEO DE INTELIGENCIA IA")
marco_ia.pack(fill="x", pady=8)
_lbl(marco_ia, "Modelo de deteccion (.pt):")
fm = tk.Frame(marco_ia, bg=BG_PANEL)
fm.pack(fill="x", pady=4)
combo_modelo = ttk.Combobox(fm, state="readonly", width=28, font=("Segoe UI", 10))
combo_modelo.pack(side="left", fill="x", expand=True)
ModernButton(fm, text="📁 Importar", bg=BG_INNER, fg=TEXT_PRI, hover_bg=BORDER,
             pady=2, font=("Segoe UI", 9), command=importar_modelo).pack(side="left", padx=(6, 0))

_lbl(marco_ia, "Sensibilidad de deteccion (%):")
var_sensibilidad = tk.DoubleVar(value=60)
tk.Scale(marco_ia, from_=30, to=95, variable=var_sensibilidad, orient="horizontal",
         bg=BG_PANEL, fg=ACCENT, troughcolor=BG_INNER,
         highlightthickness=0, relief="flat",
         font=("Segoe UI", 9, "bold"), activebackground=ACCENT).pack(fill="x", pady=4)
var_silencio = tk.BooleanVar(value=False)
tk.Checkbutton(marco_ia, text="Modo Silencioso (sin alarmas auditivas)",
               variable=var_silencio, bg=BG_PANEL, fg=TEXT_PRI,
               selectcolor=BG_INNER, activebackground=BG_PANEL,
               font=("Segoe UI", 10)).pack(anchor="w", pady=4)

# ── [4] TELEMETRÍA Y GPS (solo en MODO DRON) ─────────────
marco_tele = _lf(right, "[4] TELEMETRIA Y GPS  [DRON]")
var_telemetria = tk.BooleanVar(value=False)
tk.Checkbutton(marco_tele, text="Habilitar datos GPS / MAVSDK",
               variable=var_telemetria, bg=BG_PANEL, fg=TEXT_PRI,
               selectcolor=BG_INNER, activebackground=BG_PANEL,
               font=("Segoe UI", 10)).pack(anchor="w")
_lbl(marco_tele, "URL MAVSDK:")
entry_sdk_url = tk.Entry(marco_tele, width=44, bg=BG_INNER, fg=TEXT_PRI,
                         relief="flat", font=("Consolas", 10))
entry_sdk_url.insert(0, "udp://:14540")
entry_sdk_url.pack(pady=(0, 4), ipady=3)

# ── [5] TORRETA PID — oculto (requiere Arduino) ──────────
marco_torreta = _lf(right, "[5] TORRETA CENTINELA PID+Arduino  [INACTIVO]")
var_torreta = tk.BooleanVar(value=False)
tk.Checkbutton(marco_torreta, text="Habilitar Auto-Tracking Gimbal (PID)",
               variable=var_torreta, bg=BG_PANEL, fg=SUCCESS,
               selectcolor=BG_INNER, activebackground=BG_PANEL,
               font=("Segoe UI", 10, "bold")).pack(anchor="w")
tk.Label(marco_torreta, text="Requiere Arduino con firmware torreta_arduino.ino",
         bg=BG_PANEL, fg=TEXT_MUT, font=("Segoe UI", 8)).pack(anchor="w")
_lbl(marco_torreta, "Puerto COM del Arduino:")
frame_com = tk.Frame(marco_torreta, bg=BG_PANEL)
frame_com.pack(fill="x", pady=4)
entry_com = tk.Entry(frame_com, width=10, bg=BG_INNER, fg=ACCENT2,
                     relief="flat", font=("Consolas", 10), justify="center")
entry_com.insert(0, "COM3")
entry_com.pack(side="left", ipady=3, padx=(0, 8))
tk.Label(frame_com, text="(ej. COM3, COM5, COM8)",
         bg=BG_PANEL, fg=TEXT_MUT, font=("Segoe UI", 8)).pack(side="left")
# marco_torreta NO hace pack() — activar en versión futura

# ── PANEL DE ACCIONES ─────────────────────────────────────
actions  = tk.Frame(main, bg=BG_BASE)
actions.pack(pady=16, fill="x")
grid_acc = tk.Frame(actions, bg=BG_BASE)
grid_acc.pack(expand=True)

# Fila 0 — Herramientas auxiliares
ModernButton(grid_acc, text="⬇  MODELOS IA",
             bg=BG_PANEL, fg=ACCENT2, hover_bg=BORDER,
             font=("Segoe UI", 10, "bold"), width=18,
             command=abrir_descargador_modelos).grid(row=0, column=0, padx=6, pady=6)

ModernButton(grid_acc, text="📁 BOVEDA",
             bg=BG_PANEL, fg=ACCENT2, hover_bg=BORDER,
             font=("Segoe UI", 10, "bold"), width=18,
             command=abrir_boveda).grid(row=0, column=1, padx=6, pady=6)

ModernButton(grid_acc, text="📄 REPORTE SALUTE",
             bg="#1C1208", fg=ACCENT, hover_bg="#2D1E0A",
             font=("Segoe UI", 10, "bold"), width=20,
             command=ejecutar_reporte_salute).grid(row=0, column=2, padx=6, pady=6)

# Fila 1 — Acción principal
ModernButton(grid_acc, text="🚀  DESPLEGAR SISTEMA",
             bg=ACCENT, fg=BG_BASE, hover_bg="#D97706",
             font=("Segoe UI", 15, "bold"), width=58, pady=13,
             command=iniciar_mision).grid(row=1, column=0, columnspan=3, padx=6, pady=6)

# Fila 2 — Salir
ModernButton(grid_acc, text="✕  SALIR DEL SISTEMA",
             bg="#1F0A0A", fg=DANGER, hover_bg="#2D1010",
             font=("Segoe UI", 10, "bold"), width=58,
             command=confirmar_salida).grid(row=2, column=0, columnspan=3, padx=6, pady=6)

# ── Pie de página ─────────────────────────────────────────
tk.Label(main,
         text=f"S.A.V.I.A. v7.0  |  ESMIL  |  {datetime.now().strftime('%Y')}  "
              "— Sistema clasificado. Uso exclusivo autorizado.",
         bg=BG_BASE, fg=BORDER, font=("Segoe UI", 7)).pack(pady=(4, 0))

# ── Inicialización ────────────────────────────────────────
actualizar_ventanas()
actualizar_combo_modelos()
combo_fuente.bind("<<ComboboxSelected>>", actualizar_controles_por_fuente)
actualizar_controles_por_modo()
lanzar_mediamtx()
limpiar_evidencia_antigua()

ventana.mainloop()