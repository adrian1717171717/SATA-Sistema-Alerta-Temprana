# ==========================================
# S.A.V.I.A. V7.0 - COMMAND CENTER (ESMIL)
# ==========================================

import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
import socket
import subprocess
import os
import time
import win32gui
import psutil
import radar
import telemetria
import hashlib
import io
from datetime import datetime, timedelta
from cryptography.fernet import Fernet
from PIL import Image, ImageTk

# SEGURIDAD TÁCTICA S.A.V.I.A. v7.0
SATA_KEY = b'cYaPITSeO2gj2QiSrLiVTVagbATv7BstuzSaAXPYD3o='
cipher_suite = Fernet(SATA_KEY)
PUK_MASTER = "1717171717171717" # Clave Maestra de 16 dígitos
AUTH_FILE = ".sata_auth"

def hash_pin(pin):
    return hashlib.sha256(pin.encode()).hexdigest()

def limpiar_evidencia_antigua():
    """ Elimina archivos .sata_enc de más de 5 días """
    carpeta = "Evidencia_Seguridad"
    if not os.path.exists(carpeta): return
    ahora = time.time()
    limite = ahora - (5 * 24 * 3600)
    for f in os.listdir(carpeta):
        if f.endswith(".sata_enc"):
            path = os.path.join(carpeta, f)
            if os.path.getmtime(path) < limite:
                try: os.remove(path)
                except: pass

def solicitar_pin(callback, titulo="CONTROL DE ACCESO"):
    """ Ventana de autenticación para acciones críticas """
    top = tk.Toplevel(ventana)
    top.title(titulo)
    top.geometry("400x250")
    top.configure(bg="#1b2818")
    top.resizable(False, False)
    top.grab_set()
    
    # Centrar
    top.update_idletasks()
    w, h = 400, 250
    x = (top.winfo_screenwidth() // 2) - (w // 2)
    y = (top.winfo_screenheight() // 2) - (h // 2)
    top.geometry(f"{w}x{h}+{x}+{y}")

    tk.Label(top, text="INGRESE PIN DE COMANDANTE", bg="#1b2818", fg="#eeb902", font=("Helvetica", 10, "bold")).pack(pady=20)
    
    entry_pin = tk.Entry(top, show="*", justify="center", font=("Helvetica", 18, "bold"), bg="#0d130d", fg="white", width=15)
    entry_pin.pack(pady=10)
    entry_pin.focus()

    def verificar():
        p = entry_pin.get()
        if not os.path.exists(AUTH_FILE):
            messagebox.showerror("ERROR", "Sistema no inicializado.")
            top.destroy()
            return
            
        with open(AUTH_FILE, "r") as f:
            pin_guardado = f.read().strip()
            
        if hash_pin(p) == pin_guardado or p == PUK_MASTER:
            top.destroy()
            if p == PUK_MASTER:
                messagebox.showinfo("PUK ACEPTADO", "Clave Maestra ingresada correctamente. Por favor, reconfigure su PIN.")
                configurar_pin_inicial(fuerza=True)
            callback()
        else:
            messagebox.showerror("ACCESO DENEGADO", "PIN Incorrecto.")
            
    def usar_puk():
        puk_in = simpledialog.askstring("RECUPERACIÓN PUK", "Ingrese los 16 dígitos del código PUK:", show="*", parent=top)
        if puk_in == PUK_MASTER:
            top.destroy()
            messagebox.showinfo("PUK ACEPTADO", "Clave Maestra ingresada correctamente. Por favor, reconfigure su PIN.")
            configurar_pin_inicial(fuerza=True)
            callback()
        elif puk_in:
            messagebox.showerror("ERROR", "Código PUK incorrecto.")

    ModernButton(top, text="AUTENTICAR", command=verificar, width=20).pack(pady=10)
    tk.Button(top, text="Olvidé mi PIN (Usar PUK)", bg="#1b2818", fg="#aebfbe", font=("Helvetica", 9, "underline"), relief="flat", cursor="hand2", activebackground="#1b2818", activeforeground="white", command=usar_puk).pack(pady=5)


def configurar_pin_inicial(fuerza=False):
    """ Obliga a crear un PIN en el primer inicio o tras usar el PUK """
    if os.path.exists(AUTH_FILE) and not fuerza: return
    
    top = tk.Toplevel(ventana)
    top.title("CONFIGURACIÓN INICIAL OPSEC")
    top.geometry("400x300")
    top.configure(bg="#1b2818")
    top.grab_set()
    
    tk.Label(top, text="SISTEMA DE SEGURIDAD S.A.V.I.A.", bg="#1b2818", fg="#eeb902", font=("Helvetica", 12, "bold")).pack(pady=15)
    tk.Label(top, text="Cree su PIN de Comandante (4+ dígitos):", bg="#1b2818", fg="white").pack()
    
    e1 = tk.Entry(top, show="*", justify="center", font=("Helvetica", 14), bg="#0d130d", fg="white")
    e1.pack(pady=5)
    
    tk.Label(top, text="Confirme su PIN:", bg="#1b2818", fg="white").pack()
    e2 = tk.Entry(top, show="*", justify="center", font=("Helvetica", 14), bg="#0d130d", fg="white")
    e2.pack(pady=5)

    def guardar():
        p1, p2 = e1.get(), e2.get()
        if len(p1) < 4:
            messagebox.showwarning("DÉBIL", "El PIN debe tener al menos 4 dígitos.")
            return
        if p1 == p2:
            with open(AUTH_FILE, "w") as f:
                f.write(hash_pin(p1))
            messagebox.showinfo("ÉXITO", "PIN de Comandante establecido correctamente.")
            top.destroy()
        else:
            messagebox.showerror("ERROR", "Los PINs no coinciden.")

    ModernButton(top, text="ESTABLECER PIN", command=guardar).pack(pady=20)

def abrir_boveda():
    """ Ventana del Visor de Inteligencia """
    top = tk.Toplevel(ventana)
    top.title("V.I.B. - VISOR DE INTELIGENCIA (BÓVEDA)")
    top.state('zoomed')
    top.configure(bg="#0d130d")
    
    # Layout: Panel Izquierdo (Lista) | Panel Derecho (Imagen)
    paned = tk.PanedWindow(top, orient="horizontal", bg="#1b2818", sashwidth=4)
    paned.pack(fill="both", expand=True)
    
    frame_lista = tk.Frame(paned, bg="#1b2818", width=300)
    frame_visor = tk.Frame(paned, bg="#0d130d")
    paned.add(frame_lista)
    paned.add(frame_visor)
    
    tk.Label(frame_lista, text="EVIDENCIAS TÁCTICAS", bg="#1b2818", fg="#eeb902", font=("Helvetica", 10, "bold")).pack(pady=10)
    
    lista_archivos = tk.Listbox(frame_lista, bg="#0d130d", fg="white", font=("Consolas", 10), borderwidth=0)
    lista_archivos.pack(fill="both", expand=True, padx=5, pady=5)
    
    label_img = tk.Label(frame_visor, bg="#0d130d")
    label_img.pack(fill="both", expand=True, padx=20, pady=20)
    
    btn_mover = ModernButton(frame_visor, text="📁 MOVER A BÓVEDA CLASIFICADA", bg="#eeb902", state="disabled")
    btn_mover.pack(pady=10)

    def cargar_lista():
        lista_archivos.delete(0, "end")
        if not os.path.exists("Evidencia_Seguridad"): return
        # Permitir tanto archivos cifrados como antiguos (jpg, png)
        archivos = [f for f in os.listdir("Evidencia_Seguridad") if f.lower().endswith((".sata_enc", ".jpg", ".png"))]
        for f in archivos: lista_archivos.insert("end", f)

    def visualizar(event):
        sel = lista_archivos.curselection()
        if not sel: return
        nombre = lista_archivos.get(sel[0])
        ruta = os.path.join("Evidencia_Seguridad", nombre)
        
        try:
            if nombre.lower().endswith(".sata_enc"):
                with open(ruta, "rb") as f:
                    datos_encriptados = f.read()
                datos_desencriptados = cipher_suite.decrypt(datos_encriptados)
                img = Image.open(io.BytesIO(datos_desencriptados))
            else:
                # Carga normal para archivos antiguos
                img = Image.open(ruta)
            
            # Redimensionar para el visor
            w_visor = frame_visor.winfo_width() - 100
            h_visor = frame_visor.winfo_height() - 150
            if w_visor < 100: w_visor = 800
            if h_visor < 100: h_visor = 600
            
            img.thumbnail((w_visor, h_visor))
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
    solicitar_pin(ventana.quit, "AUTORIZAR CIERRE DE SISTEMA")

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
        try:
            ventana.state('zoomed')
        except:
            ventana.attributes('-fullscreen', True)
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
ventana.title("S.A.V.I.A. v7.0 | Comando de Operaciones (ESMIL)")
ventana.configure(bg="#0d130d") # Fondo ultra oscuro militar

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
style.configure('TCombobox', fieldbackground='#1b2818', background='#1b2818', foreground='white', borderwidth=0)
style.map('TCombobox', fieldbackground=[('readonly', '#1b2818')], foreground=[('readonly', 'white')])

# Contenedor Principal
main_container = tk.Frame(ventana, bg="#0d130d")
main_container.place(relx=0.5, rely=0.5, anchor="center")

# Cabecera Institucional
header_frame = tk.Frame(main_container, bg="#0d130d")
header_frame.pack(pady=(0, 30))

tk.Label(header_frame, text="E J É R C I T O   E C U A T O R I A N O", bg="#0d130d", fg="#eeb902", font=("Helvetica", 14, "bold")).pack()
tk.Label(header_frame, text="S.A.V.I.A. COMMAND CENTER", bg="#0d130d", fg="#ffffff", font=("Helvetica", 32, "bold")).pack()
tk.Label(header_frame, text="Sistema de Asistencia Visual e Inteligencia Artificial", bg="#0d130d", fg="#5c7a5c", font=("Helvetica", 12, "italic")).pack()

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

btn_boveda = ModernButton(actions_frame, text="🔒 VISOR DE INTELIGENCIA (BÓVEDA)", bg="#4b6043", fg="white", hover_bg="#5c7a5c", font=("Helvetica", 12, "bold"), command=lambda: solicitar_pin(abrir_boveda, "ACCESO A BÓVEDA TÁCTICA"))
btn_boveda.pack(side="top", fill="x", padx=100, pady=10)

def proceso_cambiar_pin():
    configurar_pin_inicial(fuerza=True)

btn_cambiar_pin = ModernButton(actions_frame, text="⚙️ CAMBIAR PIN DE COMANDANTE", bg="#1b2818", fg="white", hover_bg="#2c3e2c", font=("Helvetica", 10, "bold"), command=lambda: solicitar_pin(proceso_cambiar_pin, "AUTORIZAR CAMBIO DE PIN"))
btn_cambiar_pin.pack(side="top", fill="x", padx=100, pady=5)

btn_iniciar = ModernButton(actions_frame, text="🚀 DESPLEGAR SISTEMA", bg="#eeb902", fg="#0d130d", font=("Helvetica", 16, "bold"), command=iniciar_mision)
btn_iniciar.pack(side="top", fill="x", padx=100, pady=5)

btn_salir = ModernButton(actions_frame, text="✕ SALIR DEL PROGRAMA", bg="#3a0d0d", fg="white", hover_bg="#5a1d1d", font=("Helvetica", 10, "bold"), command=confirmar_salida)
btn_salir.pack(side="top", pady=15)

# Inicialización
actualizar_ventanas()
combo_fuente.bind("<<ComboboxSelected>>", lambda e: actualizar_controles_por_fuente())
actualizar_controles_por_modo()
lanzar_mediamtx()
configurar_pin_inicial()
limpiar_evidencia_antigua()

ventana.mainloop()