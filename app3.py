import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import json
import requests
from bs4 import BeautifulSoup
import re
import base64  # <--- Asegúrate de que esta línea esté presente

# --- 1. CONFIGURACIÓN SEGURA ---
try:
    API_KEY = st.secrets["GEMINI_API_KEY"]
    google_creds_dict = dict(st.secrets["GCP_SERVICE_ACCOUNT"])
    # Arreglo de la llave privada para la nube
    google_creds_dict["private_key"] = google_creds_dict["private_key"].replace("\\n", "\n")
    
    EXCEL_NAME = st.secrets["EXCEL_NAME"]
    SHEET_NAME = st.secrets.get("SHEET_NAME", "Hoja 1")
except Exception as e:
    st.error(f"Error de configuración en Secrets: {e}")
    st.stop()

st.set_page_config(page_title="Catalogador Pro Cloud", layout="wide")

# Inicializar sesión
if 'datos' not in st.session_state: 
    st.session_state.datos = None

# --- 2. FUNCIONES LÓGICAS ---

def limpiar_dato(dato):
    if isinstance(dato, list): return ", ".join(map(str, dato))
    return str(dato) if dato and dato != "---" else "---"

def get_model():
    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={API_KEY}"
    try:
        r = requests.get(url)
        modelos = r.json().get('models', [])
        for m in modelos:
            if 'generateContent' in m.get('supportedGenerationMethods', []):
                return m['name']
        return None
    except: return None

def analizar_con_vision(texto_web, lista_imagenes):
    m_name = get_model()
    if not m_name: return None
    url = f"https://generativelanguage.googleapis.com/v1beta/{m_name}:generateContent?key={API_KEY}"
    
    partes = [{"text": f"Analiza para catalogación profesional.\n\nDESCRIPCIÓN: {texto_web[:4500]}"}]
    
    # Procesar imágenes (máximo 4)
    for img_url in lista_imagenes[:4]:
        try:
            img_res = requests.get(img_url, timeout=10)
            if img_res.status_code == 200:
                partes.append({
                    "inline_data": {
                        "mime_type": "image/jpeg",
                        "data": base64.b64encode(img_res.content).decode('utf-8')
                    }
                })
        except: continue

    prompt = """
    Genera un JSON con estas claves exactas:
    Autor, Titulo, Traductor, Ilustrador, Editorial, Coleccion, Poblacion, Año, 
    Primera_Edicion, Tematica, Categorias, Encuadernacion, ISBN, Idioma, 
    Observaciones, Paginas, Medidas, Peso, Precio.

    REGLAS:
    1. CATEGORIAS (CDU): Nombre técnico en texto. PROHIBIDO usar números.
    2. OBSERVACIONES: Solo estado físico, manchas o firmas según descripción y fotos.
    3. Si no hay dato, usa '---'.
    """
    partes.append({"text": prompt})
    payload = {"contents": [{"parts": partes}], "generationConfig": {"response_mime_type": "application/json"}}
    
    try:
        r = requests.post(url, json=payload, timeout=35)
        res_json = r.json()['candidates'][0]['content']['parts'][0]['text']
        return res_json
    except: return None

def extraer_info_todocoleccion(url):
    try:
        h = {"User-Agent": "Mozilla/5.0"}
        r = requests.get(url, headers=h, timeout=12)
        s = BeautifulSoup(r.text, 'html.parser')
        imagenes = []
        for img in s.find_all('img', {'src': re.compile(r'tcimg|cloudfront')}):
            src = img.get('src')
            if src and ('galeria' in src or 'lote' in src) and src not in imagenes:
                imagenes.append(src)
        desc_div = s.find('div', {'id': 'descriptionContents'})
        texto = desc_div.get_text(separator=' ', strip=True) if desc_div else s.get_text()
        return texto, imagenes
    except: return None, []

# --- 3. INTERFAZ ---

st.title("📚 Catalogador Pro Cloud")

col_h = st.columns([3, 1, 1])
with col_h[0]: url_in = st.text_input("🔗 URL de Todocolección:", key="url")
with col_h[1]: id_user = st.text_input("🆔 ID Libro:", key="id_u")
with col_h[2]: ubi_in = st.text_input("📍 Ubicación:", key="ubi")

if st.button("🔍 Analizar Libro", type="primary"):
    if url_in and id_user:
        with st.spinner("IA analizando texto y fotos..."):
            texto, fotos = extraer_info_todocoleccion(url_in)
            if texto:
                res_raw = analizar_con_vision(texto, fotos)
                if res_raw:
                    st.session_state.datos = json.loads(res_raw)
                    st.success("¡Análisis completado!")
    else: st.warning("Falta URL o ID.")

if st.session_state.datos:
    d = st.session_state.datos
    st.divider()
    
    col1, col2, col3 = st.columns(3)
    with col1:
        f_aut = st.text_input("Autor", value=limpiar_dato(d.get("Autor")))
        f_tit = st.text_input("Título", value=limpiar_dato(d.get("Titulo")))
        f_tra = st.text_input("Traductor", value=limpiar_dato(d.get("Traductor")))
        f_ilu = st.text_input("Ilustrador", value=limpiar_dato(d.get("Ilustrador")))
        f_edi = st.text_input("Editorial", value=limpiar_dato(d.get("Editorial")))
        f_col = st.text_input("Colección", value=limpiar_dato(d.get("Coleccion")))
        f_pob = st.text_input("Población", value=limpiar_dato(d.get("Poblacion")))
    with col2:
        f_ano = st.text_input("Año", value=limpiar_dato(d.get("Año")))
        f_pri = st.text_input("Primera Edición", value=limpiar_dato(d.get("Primera_Edicion")))
        f_tem = st.text_input("Temática", value=limpiar_dato(d.get("Tematica")))
        f_cat = st.text_input("Categorías (CDU)", value=limpiar_dato(d.get("Categorias")))
        f_enc = st.text_input("Encuadernación", value=limpiar_dato(d.get("Encuadernacion")))
        f_isb = st.text_input("ISBN", value=limpiar_dato(d.get("ISBN")))
        f_idi = st.text_input("Idioma", value=limpiar_dato(d.get("Idioma")))
    with col3:
        f_pag = st.text_input("Páginas", value=limpiar_dato(d.get("Paginas")))
        f_med = st.text_input("Medidas", value=limpiar_dato(d.get("Medidas")))
        f_pes = st.text_input("Peso", value=limpiar_dato(d.get("Peso")))
        f_pre = st.text_input("Precio", value=limpiar_dato(d.get("Precio")))
        f_obs = st.text_area("Observaciones", value=limpiar_dato(d.get("Observaciones")), height=155)

    if st.button("💾 Guardar en Sheets", use_container_width=True, type="primary"):
        try:
            with st.spinner("Guardando..."):
                creds = ServiceAccountCredentials.from_json_keyfile_dict(google_creds_dict)
                gc = gspread.authorize(creds)
                hoja = gc.open(EXCEL_NAME).worksheet(SHEET_NAME)
                
                # Lista de las 21 columnas en orden exacto
                fila = [
                    str(id_user), str(ubi_in), str(f_aut), str(f_tit), str(f_tra), 
                    str(f_ilu), str(f_edi), str(f_col), str(f_pob), str(f_ano), 
                    str(f_pri), str(f_tem), str(f_cat), str(f_enc), str(f_isb), 
                    str(f_idi), str(f_obs), str(f_pag), str(f_med), str(f_pes), str(f_pre)
                ]
                
                hoja.append_row(fila)
                st.balloons()
                st.success("✅ ¡Guardado!")
                st.session_state.datos = None
                st.rerun()
        except Exception as e:
            st.error(f"Error al guardar: {e}")

if st.button("♻️ Nueva Extracción"):
    st.session_state.datos = None
    st.rerun()
