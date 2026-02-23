import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import json
import requests
from bs4 import BeautifulSoup
import re
import base64

# --- FUNCIÓN DE LIMPIEZA CON AUTOCORRECCIÓN DE PADDING ---
def sanear_llave_google(llave_sucia):
    if not llave_sucia: return ""
    
    # 1. Extraer solo el contenido entre las etiquetas o limpiar el ruido
    cuerpo = llave_sucia.replace("-----BEGIN PRIVATE KEY-----", "")
    cuerpo = cuerpo.replace("-----END PRIVATE KEY-----", "")
    cuerpo = cuerpo.replace("\\n", "").replace("\n", "").replace(" ", "").strip()
    
    # 2. Eliminar cualquier cosa que no sea Base64
    cuerpo = re.sub(r'[^A-Za-z0-9+/=]', '', cuerpo)
    
    # 3. CORRECCIÓN DE PADDING: Base64 debe ser múltiplo de 4
    # Si faltan caracteres, se añaden '=' al final
    faltante = len(cuerpo) % 4
    if faltante:
        cuerpo += "=" * (4 - faltante)
    
    # 4. Reconstruir con el formato exacto que espera la librería
    cuerpo_formateado = "\n".join(re.findall(r'.{1,64}', cuerpo))
    
    return f"-----BEGIN PRIVATE KEY-----\n{cuerpo_formateado}\n-----END PRIVATE KEY-----\n"

# --- 1. CONFIGURACIÓN DE SECRETOS ---
try:
    API_KEY = st.secrets["GEMINI_API_KEY"]
    g_secrets = st.secrets["GCP_SERVICE_ACCOUNT"]
    EXCEL_NAME = st.secrets["EXCEL_NAME"]
    SHEET_NAME = st.secrets.get("SHEET_NAME", "Hoja 1")
    
    # Aplicamos el saneamiento con corrección de padding
    private_key_fix = sanear_llave_google(g_secrets["private_key"])
    
    creds_dict = {
        "type": g_secrets["type"],
        "project_id": g_secrets["project_id"],
        "private_key_id": g_secrets["private_key_id"],
        "private_key": private_key_fix,
        "client_email": g_secrets["client_email"],
        "client_id": g_secrets["client_id"],
        "auth_uri": g_secrets["auth_uri"],
        "token_uri": g_secrets["token_uri"],
        "auth_provider_x509_cert_url": g_secrets["auth_provider_x509_cert_url"],
        "client_x509_cert_url": g_secrets["client_x509_cert_url"]
    }
except Exception as e:
    st.error(f"❌ Error en Secretos: {e}")
    st.stop()

st.set_page_config(page_title="Catalogador 2.5 Fix", layout="wide")

if 'datos_extraidos' not in st.session_state:
    st.session_state.datos_extraidos = None

# --- 2. LÓGICA DE IA (GEMINI 2.5 FLASH) ---

def analizar_con_ia(texto, fotos):
    # Usamos tu modelo 2.5 detectado anteriormente
    modelo = "models/gemini-2.5-flash"
    url_ia = f"https://generativelanguage.googleapis.com/v1beta/{modelo}:generateContent?key={API_KEY}"
    
    prompt = """Extrae los datos del libro en JSON: Autor, Titulo, Traductor, Ilustrador, Editorial, Coleccion, Poblacion, Año, Primera_Edicion, Tematica, Categorias, Encuadernacion, ISBN, Idioma, Observaciones, Paginas, Medidas, Peso, Precio. Usa '---' si no hay datos."""
    
    partes = [{"text": f"{prompt}\n\nTexto: {texto[:3000]}"}]
    if fotos:
        try:
            img_data = base64.b64encode(requests.get(fotos[0], timeout=5).content).decode('utf-8')
            partes.append({"inline_data": {"mime_type": "image/jpeg", "data": img_data}})
        except: pass

    payload = {
        "contents": [{"parts": partes}],
        "generationConfig": {"temperature": 0.1, "response_mime_type": "application/json"}
    }

    try:
        res = requests.post(url_ia, json=payload, timeout=30)
        res_j = res.json()
        if 'candidates' in res_j:
            return json.loads(res_j['candidates'][0]['content']['parts'][0]['text'])
        return None
    except Exception as e:
        st.error(f"IA Error: {e}")
        return None

# --- 3. SCRAPING ---

def extraer_datos_web(url):
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        r = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(r.text, 'html.parser')
        imgs = [img.get('src') for img in soup.find_all('img') if 'tcimg' in str(img.get('src'))]
        desc = soup.find('div', {'id': 'descriptionContents'})
        texto = desc.get_text(separator=' ', strip=True) if desc else soup.get_text()[:4000]
        return texto, imgs
    except: return None, []

# --- 4. INTERFAZ ---

st.title("📚 Catalogador v3.7 (Final Fix)")

col1, col2, col3 = st.columns([3, 1, 1])
with col1: url_lote = st.text_input("🔗 URL")
with col2: id_lote = st.text_input("🆔 ID")
with col3: ubi_lote = st.text_input("📍 Ubicación")

if st.button("🚀 Analizar"):
    txt, imgs = extraer_datos_web(url_lote)
    if txt:
        res = analizar_con_ia(txt, imgs)
        if res: st
