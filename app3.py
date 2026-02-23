import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import json
import requests
from bs4 import BeautifulSoup
import re
import base64

# --- 1. CONFIGURACIÓN SEGURA (Usa st.secrets en la nube) ---
# En GitHub NO aparecerán tus claves. Las configuraremos en el panel de Streamlit Cloud.
try:
    API_KEY = st.secrets["GEMINI_API_KEY"]
    # Cargamos las credenciales de Google desde un diccionario secreto
    google_creds_dict = dict(st.secrets["GCP_SERVICE_ACCOUNT"])
    EXCEL_NAME = st.secrets["EXCEL_NAME"]
    SHEET_NAME = st.secrets.get("SHEET_NAME", "Hoja 1")
except Exception as e:
    st.error("Error: No se encontraron los Secretos de configuración. Si estás en local, asegúrate de tener el archivo .streamlit/secrets.toml")
    st.stop()

st.set_page_config(page_title="Catalogador Pro Cloud", layout="wide")

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
    1. CATEGORIAS: Clasificación CDU técnica (solo texto).
    2. OBSERVACIONES: Solo datos del lote y fotos (estado, daños, firmas).
    3. TEMATICA: Keywords separadas por comas.
    4. Precio: Solo número. Si no hay, 0.00.
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

st.title("📚 Catalogador Pro (Cloud Version)")

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
    # (Los campos de entrada son iguales a tu versión anterior)
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
            creds = ServiceAccountCredentials.from_json_keyfile_dict(google_creds_dict)
            hoja = gspread.authorize(creds).open(EXCEL_NAME).worksheet(SHEET_NAME)
            fila = [id_user, ubi_in, f_aut, f_tit, f_tra, f_ilu, f_edi, f_col, f_pob, f_ano, f_pri, f_tem, f_cat, f_enc, f_isb, f_idi, f_obs, f_pag, f_med, f_pes, f_pre]
            hoja.append_row(fila)
            st.balloons()
            st.session_state.datos = None
            st.rerun()
        except Exception as e: st.error(f"Error: {e}")