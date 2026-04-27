# ==========================================
# S.A.T.A. V6.0 - COMMAND CENTER (ESMIL)
# ==========================================

import tkinter as tk
from tkinter import ttk, messagebox
import socket
import subprocess
import os
import time
import win32gui
import psutil
import radar
import telemetria

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
    sensibilidad_ia = var_sensibilidad.get() / 100.0 # Convertir a 0.4 - 0.9

    # Mapeo de modelos
    mapa_modelos = {
        "SMALL (Máxima Velocidad)": "yolov8n.pt",
        "MEDIUM (Equilibrio Operativo)": "yolov8s.pt",
        "LARGE (Máxima Precisión)": "yolov8m.pt"
    }
    archivo_modelo = mapa_modelos.get(modelo_alias, "yolov8n.pt")

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
        actualizar_ventanas()

# --- CLASES DE INTERFAZ MODERNA ---
class ModernButton(tk.Button):
    def __init__(self, master, **kwargs):
        self.original_bg = kwargs.get('bg', '#eeb902')
        self.hover_bg = kwargs.pop('hover_bg', '#ffcc33')
        kwargs.setdefault('relief', 'flat')
        kwargs.setdefault('font', ("Helvetica", 11, "bold"))
        kwargs.setdefault('cursor', 'hand2')
        kwargs.setdefault('pady', 8)
        super().__init__(master, **kwargs)
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)

    def _on_enter(self, e): self.configure(bg=self.hover_bg)
    def _on_leave(self, e): self.configure(bg=self.original_bg)

# --- CONFIGURACIÓN DE VENTANA ---
ventana = tk.Tk()
ventana.title("S.A.T.A. v6.0 | Comando de Operaciones (ESMIL)")
ventana.configure(bg="#0d130d") # Fondo ultra oscuro militar

# Forzar Pantalla Completa Adaptativa
try:
    ventana.state('zoomed')
except:
    ventana.attributes('-fullscreen', True)

ventana.bind("<Escape>", lambda e: ventana.state("normal"))

# Estilos TTK
style = ttk.Style()
style.theme_use('clam')
style.configure('TCombobox', fieldbackground='#1b2818', background='#1b2818', foreground='white', borderwidth=0)
style.map('TCombobox', fieldbackground=[('readonly', '#1b2818')], foreground=[('readonly', 'white')])

# Contenedor Principal
main_container = tk.Frame(ventana, bg="#0d130d")
main_container.place(relx=0.5, rely=0.5, anchor="center")

# Cabecera Institucional
header_frame = tk.Frame(main_container, bg="#0d130d")
header_frame.pack(pady=(0, 30))

tk.Label(header_frame, text="E J É R C I T O   E C U A T O R I A N O", bg="#0d130d", fg="#eeb902", font=("Helvetica", 14, "bold")).pack()
tk.Label(header_frame, text="S.A.T.A. COMMAND CENTER", bg="#0d130d", fg="#ffffff", font=("Helvetica", 32, "bold")).pack()
tk.Label(header_frame, text="Sistema de Inteligencia y Vigilancia Aérea", bg="#0d130d", fg="#5c7a5c", font=("Helvetica", 12, "italic")).pack()

# Cuerpo de la Interfaz (Grid 2 columnas)
content_frame = tk.Frame(main_container, bg="#0d130d")
content_frame.pack(padx=20)

# IZQUIERDA: Configuración de Misión
left_pane = tk.Frame(content_frame, bg="#0d130d")
left_pane.grid(row=0, column=0, padx=20, sticky="n")

# SECCIÓN 1: MISIÓN
marco_mision = tk.LabelFrame(left_pane, text=" [1] TIPO DE OPERACIÓN ", bg="#0d130d", fg="#eeb902", font=("Helvetica", 10, "bold"), padx=15, pady=10)
marco_mision.pack(fill="x", pady=10)

var_mision = tk.IntVar(value=1)
opts = [("MODO DRON: Patrullaje UAS", 1), ("MODO CENTINELA: Cámara Fija", 2), ("MODO GARITA: Analizador App", 3)]
for text, val in opts:
    tk.Radiobutton(marco_mision, text=text, variable=var_mision, value=val, bg="#0d130d", fg="#ffffff", selectcolor="#eeb902", activebackground="#0d130d", activeforeground="#eeb902", font=("Helvetica", 10), command=actualizar_controles_por_modo).pack(anchor="w", pady=5)

# SECCIÓN 2: FUENTE
marco_fuente = tk.LabelFrame(left_pane, text=" [2] ENTRADA DE VÍDEO ", bg="#0d130d", fg="#eeb902", font=("Helvetica", 10, "bold"), padx=15, pady=10)
marco_fuente.pack(fill="x", pady=10)

label_url = tk.Label(marco_fuente, text="Fuente de vídeo:", bg="#0d130d", fg="#aebfbe", font=("Helvetica", 9))
label_url.pack(anchor="w")

combo_fuente = ttk.Combobox(marco_fuente, width=45, state="readonly")
combo_fuente.pack(pady=5)

entry_url = tk.Entry(marco_fuente, width=35, bg="#1b2818", fg="#eeb902", insertbackground="white", relief="flat", font=("Helvetica", 12, "bold"), justify="center")
entry_url.insert(0, f"rtmp://{obtener_ip_local()}:1935/live/dron")
entry_url.pack(pady=10)

frame_garita = tk.Frame(marco_fuente, bg="#0d130d")
combo_ventanas = ttk.Combobox(frame_garita, state="readonly", width=30)
combo_ventanas.pack(side="left")
btn_refrescar = ModernButton(frame_garita, text="↻", width=3, pady=2, command=actualizar_ventanas)
btn_refrescar.pack(side="left", padx=5)

# DERECHA: Parámetros IA y Telemetría
right_pane = tk.Frame(content_frame, bg="#0d130d")
right_pane.grid(row=0, column=1, padx=20, sticky="n")

# SECCIÓN 3: INTELIGENCIA ARTIFICIAL
marco_ia = tk.LabelFrame(right_pane, text=" [3] NÚCLEO DE INTELIGENCIA ", bg="#0d130d", fg="#eeb902", font=("Helvetica", 10, "bold"), padx=15, pady=10)
marco_ia.pack(fill="x", pady=10)

tk.Label(marco_ia, text="Tamaño del Modelo IA:", bg="#0d130d", fg="#aebfbe", font=("Helvetica", 9)).pack(anchor="w")
combo_modelo = ttk.Combobox(marco_ia, values=["SMALL (Máxima Velocidad)", "MEDIUM (Equilibrio Operativo)", "LARGE (Máxima Precisión)"], state="readonly", width=45)
combo_modelo.current(0)
combo_modelo.pack(pady=5)

tk.Label(marco_ia, text="Sensibilidad de Detección (%):", bg="#0d130d", fg="#aebfbe", font=("Helvetica", 9)).pack(anchor="w", pady=(10, 0))
var_sensibilidad = tk.DoubleVar(value=60)
scale_sens = tk.Scale(marco_ia, from_=40, to=90, variable=var_sensibilidad, orient="horizontal", bg="#0d130d", fg="#eeb902", troughcolor="#1b2818", highlightthickness=0, relief="flat", font=("Helvetica", 9, "bold"), activebackground="#eeb902")
scale_sens.pack(fill="x", pady=5)

var_silencio = tk.BooleanVar(value=False)
tk.Checkbutton(marco_ia, text="Modo Silencioso (Sin Alarmas)", variable=var_silencio, bg="#0d130d", fg="#ffffff", selectcolor="#4b6043", activebackground="#0d130d", font=("Helvetica", 10)).pack(anchor="w", pady=5)

# SECCIÓN 4: TELEMETRÍA (Opcional)
marco_tele = tk.LabelFrame(right_pane, text=" [4] TELEMETRÍA Y GPS ", bg="#0d130d", fg="#eeb902", font=("Helvetica", 10, "bold"), padx=15, pady=10)
marco_tele.pack(fill="x", pady=10)

var_telemetria = tk.BooleanVar(value=False)
tk.Checkbutton(marco_tele, text="Habilitar Datos GPS/MAVSDK", variable=var_telemetria, bg="#0d130d", fg="#ffffff", selectcolor="#4b6043", activebackground="#0d130d", font=("Helvetica", 10)).pack(anchor="w")

entry_sdk_url = tk.Entry(marco_tele, width=45, bg="#1b2818", fg="white", relief="flat")
entry_sdk_url.insert(0, "udp://:14540")
entry_sdk_url.pack(pady=5)

entry_geocerca = tk.Entry(marco_tele, width=45, bg="#1b2818", fg="white", relief="flat")
entry_geocerca.insert(0, "-1.23456,-78.12345; -1.23500,-78.12400")
entry_geocerca.pack(pady=5)

# PANEL DE ACCIONES (BOTTOM)
actions_frame = tk.Frame(main_container, bg="#0d130d")
actions_frame.pack(pady=30, fill="x")

btn_iniciar = ModernButton(actions_frame, text="🚀 DESPLEGAR SISTEMA", bg="#eeb902", fg="#0d130d", font=("Helvetica", 16, "bold"), command=iniciar_mision)
btn_iniciar.pack(side="top", fill="x", padx=100, pady=5)

btn_salir = ModernButton(actions_frame, text="✕ SALIR DEL PROGRAMA", bg="#3a0d0d", fg="white", hover_bg="#5a1d1d", font=("Helvetica", 10, "bold"), command=ventana.quit)
btn_salir.pack(side="top", pady=15)

# Inicialización
actualizar_ventanas()
combo_fuente.bind("<<ComboboxSelected>>", lambda e: actualizar_controles_por_fuente())
actualizar_controles_por_modo()
lanzar_mediamtx()

ventana.mainloop()