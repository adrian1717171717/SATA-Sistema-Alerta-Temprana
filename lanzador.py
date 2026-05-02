# ==========================================
# S.A.V.I.A. V7.0 - COMMAND CENTER (ESMIL)
# ==========================================

import tkinter as tk
from tkinter import ttk, messagebox, simpledialog, filedialog
import socket
import subprocess
import os
import time
import win32gui
import psutil
import radar
import telemetria
import io
import glob
from datetime import datetime, timedelta
from PIL import Image, ImageTk

def limpiar_evidencia_antigua():
    """ Elimina archivos de evidencia de más de 5 días """
    carpeta = "Evidencia_Seguridad"
    if not os.path.exists(carpeta): return
    ahora = time.time()
    limite = ahora - (5 * 24 * 3600)
    for f in os.listdir(carpeta):
        if f.startswith("ALERTA_") and f.endswith((".jpg", ".png", ".sata_enc")):
            path = os.path.join(carpeta, f)
            if os.path.getmtime(path) < limite:
                try: os.remove(path)
                except: pass

def abrir_boveda():
    """ Ventana del Visor de Inteligencia """
    top = tk.Toplevel(ventana)
    top.title("V.I.B. - VISOR DE INTELIGENCIA (BÓVEDA)")
    top.state('zoomed')
    top.configure(bg="#0a0f0a")
    
    # Layout: Panel Izquierdo (Lista) | Panel Derecho (Imagen)
    paned = tk.PanedWindow(top, orient="horizontal", bg="#152015", sashwidth=4)
    paned.pack(fill="both", expand=True)
    
    frame_lista = tk.Frame(paned, bg="#152015", width=300)
    frame_visor = tk.Frame(paned, bg="#0a0f0a")
    paned.add(frame_lista)
    paned.add(frame_visor)
    
    tk.Label(frame_lista, text="EVIDENCIAS TÁCTICAS", bg="#152015", fg="#00ffcc", font=("Segoe UI", 12, "bold")).pack(pady=15)
    
    # Mejorar lista visual
    lista_archivos = tk.Listbox(frame_lista, bg="#0a0f0a", fg="#aebfbe", selectbackground="#00ffcc", selectforeground="#0a0f0a", font=("Consolas", 10), borderwidth=0, highlightthickness=1, highlightcolor="#00ffcc", highlightbackground="#223322")
    lista_archivos.pack(fill="both", expand=True, padx=10, pady=5)
    
    label_img = tk.Label(frame_visor, bg="#0a0f0a")
    label_img.pack(fill="both", expand=True, padx=20, pady=20)
    
    btn_mover = ModernButton(frame_visor, text="📁 MOVER A BÓVEDA CLASIFICADA", bg="#00ffcc", fg="#0a0f0a", hover_bg="#00ccaa", state="disabled")
    btn_mover.pack(pady=10)

    def cargar_lista():
        lista_archivos.delete(0, "end")
        if not os.path.exists("Evidencia_Seguridad"): return
        archivos = sorted([f for f in os.listdir("Evidencia_Seguridad") if f.lower().endswith((".jpg", ".png"))], reverse=True)
        for f in archivos: lista_archivos.insert("end", f)

    def visualizar(event):
        sel = lista_archivos.curselection()
        if not sel: return
        nombre = lista_archivos.get(sel[0])
        ruta = os.path.join("Evidencia_Seguridad", nombre)
        
        try:
            img = Image.open(ruta)
            
            # Redimensionar para el visor
            w_visor = frame_visor.winfo_width() - 100
            h_visor = frame_visor.winfo_height() - 150
            if w_visor < 100: w_visor = 800
            if h_visor < 100: h_visor = 600
            
            img.thumbnail((w_visor, h_visor), Image.Resampling.LANCZOS)
            photo = ImageTk.PhotoImage(img)
            
            label_img.configure(image=photo)
            label_img.image = photo
            btn_mover.configure(state="normal", command=lambda: clasificar_evidencia(nombre))
        except Exception as e:
            messagebox.showerror("ERROR DE ACCESO", f"No se pudo cargar el archivo.\n{e}")

    def clasificar_evidencia(nombre):
        dest = "Evidencia_Clasificada"
        if not os.path.exists(dest): os.makedirs(dest)
        try:
            os.rename(os.path.join("Evidencia_Seguridad", nombre), os.path.join(dest, nombre))
            messagebox.showinfo("OPSEC", "Evidencia movida a Bóveda Clasificada.")
            cargar_lista()
            label_img.configure(image="")
            btn_mover.configure(state="disabled")
        except: pass

    lista_archivos.bind("<<ListboxSelect>>", visualizar)
    cargar_lista()

def confirmar_salida():
    if messagebox.askyesno("CONFIRMAR", "¿Está seguro que desea salir del sistema?"):
        ventana.quit()

def obtener_ip_local():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

ventanas = []

def actualizar_ventanas():
    ventanas.clear()
    def enum_win(hwnd, result):
        texto = win32gui.GetWindowText(hwnd)
        if win32gui.IsWindowVisible(hwnd) and texto != "":
            result.append(texto)
    win32gui.EnumWindows(enum_win, ventanas)
    combo_ventanas['values'] = ventanas
    if ventanas: combo_ventanas.current(0)

def obtener_modelos_disponibles():
    # Buscar archivos .pt en el directorio actual
    modelos = glob.glob("*.pt")
    if not modelos:
        return ["No se encontraron modelos .pt"]
    return modelos

def actualizar_combo_modelos():
    modelos = obtener_modelos_disponibles()
    combo_modelo['values'] = modelos
    if modelos and modelos[0] != "No se encontraron modelos .pt":
        # Intentar seleccionar yolov10n si existe, sino el primero
        for i, m in enumerate(modelos):
            if "yolov10n.pt" in m.lower():
                combo_modelo.current(i)
                return
        combo_modelo.current(0)
    else:
        combo_modelo.set("No se encontraron modelos .pt")

def mediamtx_en_ejecucion():
    for proc in psutil.process_iter(['name']):
        try:
            if 'mediamtx.exe' in proc.info.get('name', '').lower():
                return True
        except: continue
    return False

def crear_config_mediamtx():
    config_path = "mediamtx.yml"
    contenido = "paths:\n  all_others:\n  live/dron:\n"
    with open(config_path, "w", encoding="utf-8") as f:
        f.write(contenido)
    return config_path

def lanzar_mediamtx():
    if not os.path.exists("mediamtx.exe"):
        return False
    if mediamtx_en_ejecucion():
        return True
    config_path = crear_config_mediamtx()
    subprocess.Popen(["mediamtx.exe", config_path], creationflags=subprocess.CREATE_NEW_CONSOLE)
    return True

def validar_enlace_transmision(enlace):
    if not enlace: return False
    enlace = enlace.strip().lower()
    return enlace.startswith(("rtmp://", "rtsp://", "udp://", "http://", "https://"))

def actualizar_controles_por_modo():
    modo = var_mision.get()
    if modo == 1: # DRON
        combo_fuente['values'] = ["RTMP/RTSP/UDP Manual"]
        combo_fuente.current(0)
        combo_fuente.configure(state='disabled')
        entry_url.configure(state='normal')
        label_url.configure(text="Enlace de stream (Dron):", fg='#aebfbe')
        frame_garita.pack_forget()
    elif modo == 2: # CENTINELA
        combo_fuente['values'] = ["Cámara Principal (Webcam 0)", "RTMP/RTSP/UDP Manual"]
        combo_fuente.configure(state='readonly')
        if combo_fuente.get() not in combo_fuente['values']:
            combo_fuente.current(0)
        label_url.configure(text="Enlace de stream (Centinela):", fg='#aebfbe')
        frame_garita.pack_forget()
        actualizar_controles_por_fuente()
    else: # GARITA
        combo_fuente.configure(state='disabled')
        entry_url.configure(state='disabled')
        label_url.configure(text="Seleccione aplicación objetivo:", fg='#aebfbe')
        frame_garita.pack(fill='x', padx=15, pady=5)

def actualizar_controles_por_fuente():
    fuente = combo_fuente.get()
    if fuente == "Cámara Principal (Webcam 0)":
        entry_url.configure(state='disabled')
    else:
        entry_url.configure(state='normal')

def importar_modelo():
    filepath = filedialog.askopenfilename(
        title="Importar Modelo YOLO (.pt)",
        filetypes=[("YOLO Models", "*.pt")]
    )
    if filepath:
        # Copiar al directorio actual
        import shutil
        filename = os.path.basename(filepath)
        dest = os.path.join(os.getcwd(), filename)
        if not os.path.exists(dest):
            shutil.copy2(filepath, dest)
            messagebox.showinfo("Éxito", f"Modelo '{filename}' importado correctamente.")
        else:
            messagebox.showinfo("Información", f"El modelo '{filename}' ya existe en el directorio.")
        actualizar_combo_modelos()

def iniciar_mision():
    mision_id = var_mision.get()
    fuente_seleccionada = combo_fuente.get()
    modelo_alias = combo_modelo.get()
    modo_silencioso = var_silencio.get()
    ventana_objetivo = combo_ventanas.get()
    enlace_transmision = entry_url.get().strip()
    usar_telemetria = var_telemetria.get()
    sdk_url = entry_sdk_url.get().strip()
    zona_gps = entry_geocerca.get().strip()
    sensibilidad_ia = var_sensibilidad.get() / 100.0

    if not modelo_alias or modelo_alias == "No se encontraron modelos .pt":
        messagebox.showerror("Error", "Debe seleccionar un modelo de inteligencia artificial válido (.pt).")
        return

    archivo_modelo = modelo_alias

    fuente_final = 0
    es_estatico = False
    modo_garita = False

    if mision_id == 3:
        if not ventana_objetivo:
            messagebox.showerror("Error", "Seleccione una ventana objetivo.")
            return
        modo_garita = True
        fuente_final = ventana_objetivo
    elif mision_id == 1:
        if not enlace_transmision:
            messagebox.showerror("Error", "Indique enlace RTMP/RTSP/UDP.")
            return
        fuente_final = enlace_transmision
        if enlace_transmision.lower().startswith("rtmp://"):
            lanzar_mediamtx()
    else:
        if fuente_seleccionada == "Cámara Principal (Webcam 0)":
            fuente_final = 0
        else:
            if not enlace_transmision:
                messagebox.showerror("Error", "Indique enlace de stream.")
                return
            fuente_final = enlace_transmision
            if enlace_transmision.lower().startswith("rtmp://"):
                lanzar_mediamtx()
        es_estatico = True

    ventana.withdraw()
    try:
        radar.iniciar_radar(
            fuente_video=fuente_final, 
            modelo_ia=archivo_modelo, 
            modo_estatico=es_estatico, 
            modo_garita=modo_garita,
            modo_silencioso_global=modo_silencioso,
            usar_telemetria=usar_telemetria,
            sdk_url=sdk_url,
            zona_gps=zona_gps,
            sensibilidad=sensibilidad_ia
        )
    finally:
        ventana.deiconify()
        try:
            ventana.state('zoomed')
        except:
            ventana.attributes('-fullscreen', True)
        actualizar_ventanas()

# --- CLASES DE INTERFAZ MODERNA ---
class ModernButton(tk.Button):
    def __init__(self, master, **kwargs):
        self.original_bg = kwargs.get('bg', '#00ffcc')
        self.hover_bg = kwargs.pop('hover_bg', '#00ccaa')
        kwargs.setdefault('relief', 'flat')
        kwargs.setdefault('font', ("Segoe UI", 11, "bold"))
        kwargs.setdefault('cursor', 'hand2')
        kwargs.setdefault('pady', 8)
        kwargs.setdefault('borderwidth', 0)
        super().__init__(master, **kwargs)
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)

    def _on_enter(self, e): 
        if self['state'] != 'disabled':
            self.configure(bg=self.hover_bg)
    def _on_leave(self, e): 
        if self['state'] != 'disabled':
            self.configure(bg=self.original_bg)

# --- CONFIGURACIÓN DE VENTANA ---
ventana = tk.Tk()
ventana.title("S.A.V.I.A. v7.0 | Comando de Operaciones (ESMIL)")
ventana.configure(bg="#050805") # Fondo ultra oscuro

# Forzar Pantalla Completa Adaptativa
try:
    ventana.state('zoomed')
except:
    ventana.attributes('-fullscreen', True)

ventana.bind("<Escape>", lambda e: ventana.state("normal"))
ventana.protocol("WM_DELETE_WINDOW", confirmar_salida)

# Estilos TTK
style = ttk.Style()
style.theme_use('clam')
style.configure('TCombobox', fieldbackground='#0a0f0a', background='#152015', foreground='#00ffcc', borderwidth=1, bordercolor="#223322", arrowcolor="#00ffcc")
style.map('TCombobox', fieldbackground=[('readonly', '#0a0f0a')], foreground=[('readonly', '#00ffcc')])

# Contenedor Principal
main_container = tk.Frame(ventana, bg="#050805")
main_container.place(relx=0.5, rely=0.5, anchor="center")

# Cabecera Institucional
header_frame = tk.Frame(main_container, bg="#050805")
header_frame.pack(pady=(0, 20))

tk.Label(header_frame, text="S I S T E M A   C E N T I N E L A", bg="#050805", fg="#00ffcc", font=("Segoe UI", 12, "bold")).pack()
tk.Label(header_frame, text="S.A.V.I.A. COMMAND CENTER", bg="#050805", fg="#ffffff", font=("Segoe UI", 36, "bold")).pack()
tk.Label(header_frame, text="Sistema de Asistencia Visual e Inteligencia Artificial", bg="#050805", fg="#4b6043", font=("Segoe UI", 12, "italic")).pack(pady=(0, 10))

# Cuerpo de la Interfaz (Grid 2 columnas)
content_frame = tk.Frame(main_container, bg="#050805")
content_frame.pack(padx=20)

# Colores del panel
PANEL_BG = "#0a0f0a"
BORDER_COLOR = "#152015"
ACCENT_COLOR = "#00ffcc"
TEXT_COLOR = "#ffffff"
TEXT_MUTED = "#8ba38b"

# IZQUIERDA: Configuración de Misión
left_pane = tk.Frame(content_frame, bg="#050805")
left_pane.grid(row=0, column=0, padx=20, sticky="n")

# SECCIÓN 1: MISIÓN
marco_mision = tk.LabelFrame(left_pane, text=" [1] TIPO DE OPERACIÓN ", bg=PANEL_BG, fg=ACCENT_COLOR, font=("Segoe UI", 10, "bold"), padx=20, pady=15, bd=1, highlightbackground=BORDER_COLOR, highlightthickness=1)
marco_mision.pack(fill="x", pady=10)

var_mision = tk.IntVar(value=1)
opts = [("MODO DRON: Patrullaje UAS", 1), ("MODO CENTINELA: Cámara Fija", 2), ("MODO GARITA: Analizador App", 3)]
for text, val in opts:
    tk.Radiobutton(marco_mision, text=text, variable=var_mision, value=val, bg=PANEL_BG, fg=TEXT_COLOR, selectcolor="#152015", activebackground=PANEL_BG, activeforeground=ACCENT_COLOR, font=("Segoe UI", 10), command=actualizar_controles_por_modo).pack(anchor="w", pady=5)

# SECCIÓN 2: FUENTE
marco_fuente = tk.LabelFrame(left_pane, text=" [2] ENTRADA DE VÍDEO ", bg=PANEL_BG, fg=ACCENT_COLOR, font=("Segoe UI", 10, "bold"), padx=20, pady=15, bd=1, highlightbackground=BORDER_COLOR, highlightthickness=1)
marco_fuente.pack(fill="x", pady=10)

label_url = tk.Label(marco_fuente, text="Fuente de vídeo:", bg=PANEL_BG, fg=TEXT_MUTED, font=("Segoe UI", 9))
label_url.pack(anchor="w")

combo_fuente = ttk.Combobox(marco_fuente, width=45, state="readonly", font=("Segoe UI", 10))
combo_fuente.pack(pady=5)

entry_url = tk.Entry(marco_fuente, width=35, bg="#152015", fg=ACCENT_COLOR, insertbackground="white", relief="flat", font=("Consolas", 11), justify="center")
entry_url.insert(0, f"rtmp://{obtener_ip_local()}:1935/live/dron")
entry_url.pack(pady=10, ipady=4)

frame_garita = tk.Frame(marco_fuente, bg=PANEL_BG)
combo_ventanas = ttk.Combobox(frame_garita, state="readonly", width=30, font=("Segoe UI", 10))
combo_ventanas.pack(side="left")
btn_refrescar = ModernButton(frame_garita, text="↻", width=3, pady=2, bg="#152015", fg=TEXT_COLOR, hover_bg="#223322", command=actualizar_ventanas)
btn_refrescar.pack(side="left", padx=5)

# DERECHA: Parámetros IA y Telemetría
right_pane = tk.Frame(content_frame, bg="#050805")
right_pane.grid(row=0, column=1, padx=20, sticky="n")

# SECCIÓN 3: INTELIGENCIA ARTIFICIAL
marco_ia = tk.LabelFrame(right_pane, text=" [3] NÚCLEO DE INTELIGENCIA ", bg=PANEL_BG, fg=ACCENT_COLOR, font=("Segoe UI", 10, "bold"), padx=20, pady=15, bd=1, highlightbackground=BORDER_COLOR, highlightthickness=1)
marco_ia.pack(fill="x", pady=10)

tk.Label(marco_ia, text="Seleccione Modelo Base (Archivos .pt locales):", bg=PANEL_BG, fg=TEXT_MUTED, font=("Segoe UI", 9)).pack(anchor="w")

# Sub-frame para combo de modelos y botón de importar
frame_modelos = tk.Frame(marco_ia, bg=PANEL_BG)
frame_modelos.pack(fill="x", pady=5)

combo_modelo = ttk.Combobox(frame_modelos, state="readonly", width=35, font=("Segoe UI", 10))
combo_modelo.pack(side="left", fill="x", expand=True)

btn_importar_modelo = ModernButton(frame_modelos, text="Importar", bg="#152015", fg=TEXT_COLOR, hover_bg="#223322", pady=2, font=("Segoe UI", 9), command=importar_modelo)
btn_importar_modelo.pack(side="left", padx=(10, 0))

tk.Label(marco_ia, text="Sensibilidad de Detección (%):", bg=PANEL_BG, fg=TEXT_MUTED, font=("Segoe UI", 9)).pack(anchor="w", pady=(15, 0))
var_sensibilidad = tk.DoubleVar(value=60)
scale_sens = tk.Scale(marco_ia, from_=40, to=90, variable=var_sensibilidad, orient="horizontal", bg=PANEL_BG, fg=ACCENT_COLOR, troughcolor="#152015", highlightthickness=0, relief="flat", font=("Segoe UI", 9, "bold"), activebackground=ACCENT_COLOR)
scale_sens.pack(fill="x", pady=5)

var_silencio = tk.BooleanVar(value=False)
tk.Checkbutton(marco_ia, text="Modo Silencioso (Sin Alarmas Auditivas)", variable=var_silencio, bg=PANEL_BG, fg=TEXT_COLOR, selectcolor="#152015", activebackground=PANEL_BG, font=("Segoe UI", 10)).pack(anchor="w", pady=5)

# SECCIÓN 4: TELEMETRÍA (Opcional)
marco_tele = tk.LabelFrame(right_pane, text=" [4] TELEMETRÍA Y GPS ", bg=PANEL_BG, fg=ACCENT_COLOR, font=("Segoe UI", 10, "bold"), padx=20, pady=15, bd=1, highlightbackground=BORDER_COLOR, highlightthickness=1)
marco_tele.pack(fill="x", pady=10)

var_telemetria = tk.BooleanVar(value=False)
tk.Checkbutton(marco_tele, text="Habilitar Datos GPS/MAVSDK", variable=var_telemetria, bg=PANEL_BG, fg=TEXT_COLOR, selectcolor="#152015", activebackground=PANEL_BG, font=("Segoe UI", 10)).pack(anchor="w")

tk.Label(marco_tele, text="URL MAVSDK:", bg=PANEL_BG, fg=TEXT_MUTED, font=("Segoe UI", 8)).pack(anchor="w", pady=(5,0))
entry_sdk_url = tk.Entry(marco_tele, width=45, bg="#152015", fg=TEXT_COLOR, relief="flat", font=("Consolas", 10))
entry_sdk_url.insert(0, "udp://:14540")
entry_sdk_url.pack(pady=(0,5), ipady=3)

tk.Label(marco_tele, text="Coordenadas de Geocerca:", bg=PANEL_BG, fg=TEXT_MUTED, font=("Segoe UI", 8)).pack(anchor="w", pady=(5,0))
entry_geocerca = tk.Entry(marco_tele, width=45, bg="#152015", fg=TEXT_COLOR, relief="flat", font=("Consolas", 10))
entry_geocerca.insert(0, "-1.23456,-78.12345; -1.23500,-78.12400")
entry_geocerca.pack(pady=(0,5), ipady=3)

# PANEL DE ACCIONES (BOTTOM)
actions_frame = tk.Frame(main_container, bg="#050805")
actions_frame.pack(pady=20, fill="x")

# Grid para botones de acción para mejor alineación
actions_grid = tk.Frame(actions_frame, bg="#050805")
actions_grid.pack(expand=True)

btn_boveda = ModernButton(actions_grid, text="📁 VISOR DE INTELIGENCIA", bg="#152015", fg="#00ffcc", hover_bg="#223322", font=("Segoe UI", 11, "bold"), width=30, command=abrir_boveda)
btn_boveda.grid(row=0, column=0, padx=10, pady=10)

btn_iniciar = ModernButton(actions_grid, text="🚀 DESPLEGAR SISTEMA", bg="#00ffcc", fg="#050805", hover_bg="#00ccaa", font=("Segoe UI", 14, "bold"), width=30, pady=12, command=iniciar_mision)
btn_iniciar.grid(row=1, column=0, padx=10, pady=5)

btn_salir = ModernButton(actions_grid, text="✕ SALIR", bg="#2a1111", fg="#ff4444", hover_bg="#3a1818", font=("Segoe UI", 10, "bold"), width=30, command=confirmar_salida)
btn_salir.grid(row=2, column=0, padx=10, pady=10)

# Inicialización
actualizar_ventanas()
actualizar_combo_modelos()
combo_fuente.bind("<<ComboboxSelected>>", lambda e: actualizar_controles_por_fuente())
actualizar_controles_por_modo()
lanzar_mediamtx()
limpiar_evidencia_antigua()

ventana.mainloop()