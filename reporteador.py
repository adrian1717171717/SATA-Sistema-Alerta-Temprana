# S.A.V.I.A. V7.0 — GENERADOR DE REPORTES SALUTE (reporteador.py)
# Genera un PDF táctico para el archivo de evidencia seleccionado.
# Soporta imágenes JPG/PNG y videoclips MP4 (extrae primer fotograma).
import os, csv, tempfile
import cv2
from datetime import datetime

try:
    from fpdf import FPDF as _BASE
    FPDF_OK = True
except ImportError:
    _BASE = object
    FPDF_OK = False
    print("[!] fpdf2 no instalado. Ejecute: pip install fpdf2")

CARPETA = "Evidencia_Seguridad"
MARGEN  = 14


def _ascii(texto):
    """
    Sanitiza texto para fuentes Latin-1 de fpdf2.
    Sustituye em-dash, en-dash, y otros caracteres Unicode problemáticos.
    """
    if not isinstance(texto, str):
        texto = str(texto)
    reemplazos = {
        "\u2014": " - ", "\u2013": " - ", "\u2012": " - ",
        "\u2018": "'",   "\u2019": "'",
        "\u201C": '"',   "\u201D": '"',
        "\u2022": "*",   "\u2026": "...",
        "\u00B0": "deg", "\u2605": "*",  "\u2192": "->",
    }
    for orig, rep in reemplazos.items():
        texto = texto.replace(orig, rep)
    return texto.encode('latin-1', errors='replace').decode('latin-1')


def _extraer_frame_video(ruta_mp4):
    """
    Extrae el primer fotograma de un MP4 y lo guarda como JPG temporal.
    Retorna la ruta del JPG temporal o None si falla.
    """
    try:
        cap = cv2.VideoCapture(ruta_mp4)
        ok, frame = cap.read()
        cap.release()
        if not ok or frame is None:
            return None
        # Guardar en carpeta temporal del sistema
        tmp = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
        cv2.imwrite(tmp.name, frame)
        return tmp.name
    except Exception as e:
        print(f"[!] No se pudo extraer frame de video: {e}")
        return None


def _buscar_fila_csv(nombre_archivo):
    """
    Busca en el CSV la fila cuya columna 'Archivo_Imagen' coincida con
    nombre_archivo. Si es un .mp4, también intenta con el CLIP_ equivalente.
    Retorna un dict con los datos de la fila o un dict vacío si no encuentra.
    """
    ruta_csv = os.path.join(CARPETA, "registro_novedades.csv")
    if not os.path.exists(ruta_csv):
        return {}

    nombre_base = os.path.splitext(nombre_archivo)[0]  # sin extensión

    try:
        with open(ruta_csv, newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            filas = list(reader)
    except Exception as e:
        print(f"[!] Error leyendo CSV: {e}")
        return {}

    # Búsqueda 1: coincidencia exacta por Archivo_Imagen
    for fila in filas:
        img_col = (fila.get("Archivo_Imagen") or fila.get("Archivo de Foto") or "").strip()
        if img_col == nombre_archivo:
            return fila

    # Búsqueda 2: coincidencia por timestamp (nombre base sin extensión)
    # Ej: "CLIP_20260511_095012" coincide con "ALERTA_20260511_095012"
    ts_buscado = nombre_base.replace("CLIP_", "").replace("ALERTA_", "")
    for fila in filas:
        img_col = (fila.get("Archivo_Imagen") or fila.get("Archivo de Foto") or "").strip()
        ts_fila = os.path.splitext(img_col)[0].replace("ALERTA_", "").replace("CLIP_", "")
        if ts_buscado and ts_buscado == ts_fila:
            return fila

    # Sin coincidencia: retornar vacío (se usarán valores N/A)
    return {}


class _PDF(_BASE):
    def header(self):
        self.set_fill_color(11, 19, 30)
        self.rect(0, 0, 210, 24, 'F')
        self.set_font("Helvetica", "B", 8)
        self.set_text_color(148, 163, 184)
        self.set_xy(MARGEN, 4)
        self.cell(0, 5, "COMANDO DE INTELIGENCIA - S.A.V.I.A. V7.0 - ESMIL", ln=True)
        self.set_font("Helvetica", "B", 13)
        self.set_text_color(245, 158, 11)
        self.set_x(MARGEN)
        self.cell(0, 8, "REPORTE TACTICO AUTOMATIZADO - FORMATO SALUTE",
                  ln=True, align="C")
        self.set_font("Helvetica", "B", 9)
        self.set_text_color(220, 38, 38)
        self.set_fill_color(40, 10, 10)
        self.set_xy(210 - MARGEN - 44, 6)
        self.cell(44, 10, " * RESERVADO * ", border=1, align="C", fill=True)
        self.set_draw_color(245, 158, 11)
        self.set_line_width(0.4)
        self.line(MARGEN, 25, 210 - MARGEN, 25)
        self.ln(7)

    def footer(self):
        self.set_y(-10)
        self.set_font("Helvetica", "I", 6)
        self.set_text_color(100, 116, 139)
        ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        self.cell(0, 6,
                  f"Generado: {ts} - Pag. {self.page_no()} - DOCUMENTO CLASIFICADO",
                  align="C")


def generar_pdf(nombre_archivo_seleccionado):
    """
    Genera un PDF SALUTE para el archivo de evidencia indicado.

    Args:
        nombre_archivo_seleccionado: nombre del archivo (ej. 'ALERTA_20260511_095012.jpg'
                                     o 'CLIP_20260511_095012.mp4')

    Returns:
        (True, ruta_pdf)     si se generó correctamente.
        (False, msg_error)   si hubo un problema.
    """
    if not FPDF_OK:
        return False, "fpdf2 no instalado. Ejecute: pip install fpdf2"

    es_video = nombre_archivo_seleccionado.lower().endswith(".mp4")
    ruta_archivo = os.path.join(CARPETA, nombre_archivo_seleccionado)

    if not os.path.exists(ruta_archivo):
        return False, f"Archivo no encontrado: {ruta_archivo}"

    # Buscar metadatos en el CSV
    fila = _buscar_fila_csv(nombre_archivo_seleccionado)

    def _get(*keys):
        for k in keys:
            val = fila.get(k, "").strip() if fila else ""
            if val:
                return _ascii(val)
        return "N/A"

    fecha     = _get("Fecha")
    hora      = _get("Hora")
    size_val  = _get("Size", "Nivel de Confianza (%)")
    activity  = _get("Activity", "Modo de Operacion", "Modo de Operación")
    location  = _get("Location")
    unit      = _get("Unit", "Clase Tactica", "Clase Táctica")
    equipment = _get("Equipment")

    # Si no hay datos en CSV, construir valores mínimos desde el nombre
    if fecha == "N/A":
        try:
            # Intentar extraer fecha del timestamp en el nombre del archivo
            nombre_base = os.path.splitext(nombre_archivo_seleccionado)[0]
            ts_part = nombre_base.replace("ALERTA_","").replace("CLIP_","")
            if len(ts_part) >= 15:
                fecha = f"{ts_part[:4]}-{ts_part[4:6]}-{ts_part[6:8]}"
                hora  = f"{ts_part[9:11]}:{ts_part[11:13]}:{ts_part[13:15]}"
        except Exception:
            pass

    # Obtener imagen para el PDF
    ruta_imagen_pdf = None
    tmp_frame = None

    if es_video:
        # 1. Buscar si existe una imagen ALERTA con el mismo timestamp
        ts = os.path.splitext(nombre_archivo_seleccionado)[0].replace("CLIP_","")
        candidato_jpg = os.path.join(CARPETA, f"ALERTA_{ts}.jpg")
        if os.path.exists(candidato_jpg):
            ruta_imagen_pdf = candidato_jpg
        else:
            # 2. Extraer primer fotograma del MP4
            tmp_frame = _extraer_frame_video(ruta_archivo)
            ruta_imagen_pdf = tmp_frame
    else:
        ruta_imagen_pdf = ruta_archivo

    # Construir PDF
    try:
        pdf = _PDF(orientation='P', unit='mm', format='A4')
        pdf.set_auto_page_break(auto=True, margin=18)
        pdf.add_page()

        HF        = "Helvetica"
        COL_BG    = (30, 41, 59)
        COL_AMBER = (245, 158, 11)
        COL_MUTED = (148, 163, 184)
        COL_WHITE = (226, 232, 240)

        def _fila(letra, etiqueta, valor):
            ancho = 210 - 2 * MARGEN
            pdf.set_x(MARGEN)
            pdf.set_fill_color(*COL_BG)
            pdf.set_font(HF, "B", 8)
            pdf.set_text_color(*COL_AMBER)
            pdf.cell(46, 6.5, f"  [{letra}] {etiqueta}:", border="LTB", fill=True)
            pdf.set_font(HF, "", 8)
            pdf.set_text_color(*COL_WHITE)
            v = valor if len(valor) <= 90 else valor[:87] + "..."
            pdf.cell(ancho - 46, 6.5, f"  {v}", border="RTB", fill=True, ln=True)

        # Encabezado de evento
        tipo_ev = "VIDEO CLIP" if es_video else "IMAGEN"
        pdf.set_fill_color(20, 30, 48)
        pdf.set_font(HF, "B", 10)
        pdf.set_text_color(*COL_AMBER)
        pdf.set_x(MARGEN)
        pdf.cell(210 - 2 * MARGEN, 8,
                 f"  EVENTO [{tipo_ev}] - {fecha}  {hora}",
                 fill=True, ln=True)
        pdf.ln(3)

        # Nombre de archivo fuente
        pdf.set_font(HF, "I", 8)
        pdf.set_text_color(*COL_MUTED)
        pdf.set_x(MARGEN)
        pdf.cell(0, 5, f"Fuente: {_ascii(nombre_archivo_seleccionado)}", ln=True)
        pdf.ln(2)

        # Tabla SALUTE
        pdf.set_font(HF, "B", 10)
        pdf.set_text_color(*COL_AMBER)
        pdf.set_x(MARGEN)
        pdf.cell(0, 7, "ANALISIS DE INTELIGENCIA - FORMATO SALUTE", ln=True)
        pdf.set_draw_color(*COL_AMBER)
        pdf.set_line_width(0.3)
        pdf.line(MARGEN, pdf.get_y(), 210 - MARGEN, pdf.get_y())
        pdf.ln(2)

        _fila("S", "TAMANO (Size)",           f"{size_val} objetivo(s) detectados")
        _fila("A", "ACTIVIDAD (Activity)",    activity)
        _fila("L", "LOCALIZACION (Location)", location)
        _fila("U", "UNIDAD/CLASE (Unit)",     unit)
        _fila("T", "TIEMPO (Time)",           f"{fecha} - {hora} (hora local)")
        _fila("E", "EQUIPO (Equipment)",      equipment)
        pdf.ln(5)

        # Evidencia visual
        pdf.set_font(HF, "B", 9)
        pdf.set_text_color(*COL_AMBER)
        pdf.set_x(MARGEN)
        etiq_ev = "FOTOGRAMA DE EVIDENCIA (extraido del video)" if es_video else "CAPTURA DE EVIDENCIA"
        pdf.cell(0, 7, etiq_ev, ln=True)
        pdf.line(MARGEN, pdf.get_y(), 210 - MARGEN, pdf.get_y())
        pdf.ln(2)

        if ruta_imagen_pdf and os.path.exists(ruta_imagen_pdf):
            try:
                img_w = 150
                img_x = (210 - img_w) / 2
                pdf.image(ruta_imagen_pdf, x=img_x, y=pdf.get_y(), w=img_w)
                pdf.ln(img_w * 0.5625 + 4)
                pdf.set_font(HF, "I", 7)
                pdf.set_text_color(*COL_MUTED)
                pdf.set_x(MARGEN)
                pdf.cell(0, 5, f"Archivo fuente: {_ascii(nombre_archivo_seleccionado)}",
                         ln=True, align="C")
            except Exception as e:
                pdf.set_font(HF, "I", 8)
                pdf.set_text_color(180, 60, 60)
                pdf.cell(0, 6, _ascii(f"[!] No se pudo insertar imagen: {e}"), ln=True)
        else:
            pdf.set_font(HF, "I", 8)
            pdf.set_text_color(*COL_MUTED)
            pdf.set_x(MARGEN)
            pdf.cell(0, 6, "[Sin imagen disponible para este registro]", ln=True)

        # Guardar PDF
        os.makedirs(CARPETA, exist_ok=True)
        ts_out = datetime.now().strftime("%Y%m%d_%H%M%S")
        nombre_base_sin_ext = os.path.splitext(nombre_archivo_seleccionado)[0]
        out = os.path.join(CARPETA, f"REPORTE_SALUTE_{nombre_base_sin_ext}_{ts_out}.pdf")
        pdf.output(out)
        print(f"[+] Reporte SALUTE generado: {out}")
        return True, out

    except Exception as e:
        return False, f"Error generando PDF: {e}"
    finally:
        # Limpiar fotograma temporal si fue extraído de un video
        if tmp_frame and os.path.exists(tmp_frame):
            try:
                os.remove(tmp_frame)
            except Exception:
                pass


# Mantener compatibilidad con el botón del panel principal (usa última fila)
def generar_reporte():
    """
    Compatibilidad: genera reporte de la ultima evidencia registrada que tenga
    un archivo de imagen/video valido. Ignora filas del formato antiguo corrupto.
    Usado por el boton del panel principal de lanzador.py.
    """
    ruta_csv = os.path.join(CARPETA, "registro_novedades.csv")
    if not os.path.exists(ruta_csv):
        raise RuntimeError("No hay registros en registro_novedades.csv")
    try:
        with open(ruta_csv, newline='', encoding='utf-8') as f:
            filas = list(csv.DictReader(f))
    except Exception as e:
        raise RuntimeError(f"Error leyendo CSV: {e}")
    if not filas:
        raise RuntimeError("El CSV de novedades esta vacio.")

    # Buscar la última fila con un archivo de imagen/video real (extensión válida)
    EXTS_VALIDAS = (".jpg", ".jpeg", ".png", ".mp4")
    nombre = None
    for fila in reversed(filas):
        candidato = (fila.get("Archivo_Imagen") or fila.get("Archivo de Foto") or "").strip()
        if candidato.lower().endswith(EXTS_VALIDAS):
            nombre = candidato
            break

    if not nombre:
        raise RuntimeError(
            "No se encontro ninguna fila valida en el CSV.\n"
            "Asegurese de haber generado al menos una alerta con la nueva version del sistema."
        )

    ok, resultado = generar_pdf(nombre)
    if ok:
        return resultado
    raise RuntimeError(resultado)


def main():
    import tkinter as tk
    from tkinter import messagebox
    root = tk.Tk(); root.withdraw()
    try:
        ruta = generar_reporte()
        messagebox.showinfo(
            "Reporte de Inteligencia",
            f"Reporte generado con exito en la boveda.\n\n{ruta}"
        )
        try: os.startfile(ruta)
        except Exception: pass
    except Exception as e:
        messagebox.showerror("Error al generar reporte", str(e))
    finally:
        root.destroy()


if __name__ == "__main__":
    main()
