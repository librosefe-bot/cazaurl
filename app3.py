import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import json
import requests
from bs4 import BeautifulSoup
import re
import base64

# --- 1. CONFIGURACIÓN SEGURA ---
try:
    API_KEY = st.secrets["GEMINI_API_KEY"]
    # Corregimos la lectura de la llave privada (el problema de los saltos de línea \n)
    google_creds_dict = dict(st.secrets["GCP_SERVICE_ACCOUNT"])
    google_creds_dict["private_key"] = google_creds_dict["private_key"].replace("\\n", "\n")
    
    EXCEL_NAME = st.secrets["EXCEL_NAME"]
    SHEET_NAME = st.secrets.get("SHEET_NAME", "Hoja 1")
except Exception as e:
    st.error(f"Error de configuración: {e}")
    st.stop()

st.set_page_config(page_title="Catalogador Pro Cloud", layout="wide")

if 'datos' not in st.session_state: 
    st.session_state.datos = None

# --- 2. FUNCIONES LÓGICAS ---

def limpiar_dato(dato):
    """Asegura que el dato sea texto plano y no una lista o número"""
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

    # PROMPT REFORZADO PARA CATEGORÍAS SIN NÚMEROS
    prompt = """
    Genera un JSON con estas claves exactas:
    Autor, Titulo, Traductor, Ilustrador, Editorial, Coleccion, Poblacion, Año, 
    Primera_Edicion, Tematica, Categorias, Encuadernacion, ISBN, Idioma, 
    Observaciones, Paginas, Medidas, Peso, Precio.

    REGLAS ESTRICTAS:
    1. CATEGORIAS (CDU): Clasifica según la CDU pero devuelve EXCLUSIVAMENTE el nombre de la categoría en texto. 
       Está TERMINANTEMENTE PROHIBIDO incluir números o códigos (ej: NO pongas '821', pon 'Literatura').
    2. OBSERVACIONES: Solo datos del lote y fotos (estado, manchas, firmas, etc).
    3. Si falta un dato, usa '---'.
    """
    partes.append({"text": prompt})
    payload = {"contents": [{"parts": partes}], "generationConfig": {"response_mime_type": "application/json"}}
    
    try:
        r = requests.post(url, json=payload, timeout=35)
        return r.json()['candidates'][0]['content']['parts'][0]['text']
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
with col_h[0]: url_in = st.text_input("🔗 URL:", key="url")
with col_h[1]: id_user = st.text_input("🆔 ID:", key="id_u")
with col_h[2]: ubi_in = st.text_input("📍 Ubicación:", key="ubi")

if st.button("🔍 Analizar Libro", type="primary"):
    if url_in and id_user:
        with st.spinner("IA analizando texto y fotos..."):
            texto, fotos = extraer_info_todocoleccion(url_in)
            if texto:
                res_json = analizar_con_vision(texto, fotos)
                if res_json:
                    st.session_state.datos = json.loads(res_json)
                    st.success("¡Análisis listo!")

if st.session_state.datos:
    d = st.session_state.datos
    st.divider()
    col1, col2, col3 = st.columns(3)
    with col1:
        f_aut = st.text_input("Autor", value=limpiar_dato(d.get("Autor")))
        f_tit = st.text_input("Título", value=limpiar_dato(d.get("Titulo")))
        f
