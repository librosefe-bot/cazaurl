import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import json
import requests
from bs4 import BeautifulSoup
import re
import base64

# --- 1. FUNCIÓN DE LIMPIEZA DE CLAVE (BLINDADA) ---
def sanear_llave_google(llave_sucia):
    if not llave_sucia: return ""
    cuerpo = llave_sucia.replace("-----BEGIN PRIVATE KEY-----", "").replace("-----END PRIVATE KEY-----", "")
    cuerpo = cuerpo.replace("\\n", "").replace("\n", "").replace(" ", "").strip()
    cuerpo = re.sub(r'[^A-Za-z0-9+/]', '', cuerpo)
    faltante = len(cuerpo) % 4
    if faltante: cuerpo += "=" * (4 - faltante)
    lineas = [cuerpo[i:i+64] for i in range(0, len(cuerpo), 64)]
    cuerpo_final = "\n".join(lineas)
    return f"-----BEGIN PRIVATE KEY-----\n{cuerpo_final}\n-----END PRIVATE KEY-----\n"

# --- 2. CARGA DE SECRETOS ---
try:
    API_KEY = st.secrets["GEMINI_API_KEY"].strip()
    EXCEL_NAME = st.secrets["EXCEL_NAME"]
    SHEET_NAME = st.secrets.get("SHEET_NAME", "Hoja 1")
    g_secrets = st.secrets["GCP_SERVICE_ACCOUNT"]
    pk_limpia = sanear_llave_google(g_secrets["private_key"])
    
    creds_dict = {
        "type": "service_account",
        "project_id": g_secrets["project_id"],
        "private_key_id": g_secrets["private_key_id"],
        "private_key": pk_limpia,
        "client_email": g_secrets["client_email"],
        "client_id": g_secrets["client_id"],
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
        "client_x509_cert_url": g_secrets["client_x509_cert_url"]
    }
except Exception as e:
    st.error(f"⚠️ Error en Secrets: {e}")
    st.stop()

st.set_page_config(page_title="Catalogador Gemini 2.0", layout="wide")

if 'datos_extraidos' not in st.session_state:
    st.session_state.datos_extraidos = None

# --- 3. LÓGICA DE IA (VERSION 2.0 FLASH) ---

def analizar_con_ia(texto, fotos):
    # Cambiado a gemini-2.0-flash para evitar el error 404
    url_ia = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={API_KEY}"
    
    prompt = """Extrae los datos del libro y devuelve ÚNICAMENTE un JSON. 
    Campos: Autor, Titulo, Traductor, Ilustrador, Editorial, Coleccion, Poblacion, Año, 
    Primera_Edicion, Tematica, Categorias, Encuadernacion, ISBN, Idioma, 
    Observaciones, Paginas, Medidas, Peso, Precio. Usa '---' si falta."""
    
    partes = [{"text": f"{prompt}\n\nTexto del lote: {texto[:3500]}"}]
    
    if fotos:
        try:
            # Procesamos la imagen principal para mejorar la precisión
            img_data = base64.b64encode(requests.get(fotos[0]).content).decode('utf-8')
            partes.append({"inline_data": {"mime_type": "image/jpeg", "data": img_data}})
        except: pass

    payload = {
        "contents": [{"parts": partes}],
        "generationConfig": {"temperature": 0.1, "response_mime_type": "application/json"}
    }

    try:
        res = requests.post(url_ia, json=payload, timeout=30)
        if res.status_code == 200:
            return json.loads(res.json()['candidates'][0]['content']['parts'][0]['text'])
        else:
            st.error(f"Error Gemini API ({res.status_code}): {res.text}")
            return None
    except Exception as e:
        st.error(f"Error en análisis: {e}")
        return None

# --- 4. EXTRACCIÓN WEB ---

def extraer_web(url):
    try:
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        soup = BeautifulSoup(r.text, 'html.parser')
        imgs = [img.get('src') for img in soup.find_all('img') if 'tcimg' in str(img.get('src'))]
        desc = soup.find('div', {'id': 'descriptionContents'})
        texto = desc.get_text(separator=' ', strip=True) if desc else soup.get_text()[:4000]
        return texto, imgs
    except Exception as e:
        st.error(f"Error Web: {e}")
        return None, []

# --- 5. INTERFAZ ---

st.title("📚 Catalogador v4.3 (Gemini 2.0)")

with st.container(border=True):
    c1, c2, c3 = st.columns([3, 1, 1])
    url_in = c1.text_input("🔗 URL")
    id_in = c2.text_input("🆔 ID")
    ubi_in = c3.text_input("📍 Ubicación")

if st.button("🚀 Analizar", type="primary", use_container_width=True):
    if url_in and id_in:
        with st.spinner("IA analizando..."):
            txt, imgs = extraer_web(url_in)
            if txt:
                res = analizar_con_ia(txt, imgs)
                if res:
                    st.session_state.datos_extraidos = res
                    st.rerun()
    else:
        st.warning("Falta URL o ID")

if st.session_state.datos_extraidos:
    st.divider()
    d = st.session_state.datos_extraidos
    cols = st.columns(3)
    
    # Formulario dinámico
    f_aut = cols[0].text_input("Autor", d.get('Autor', '---'))
    f_tit = cols[0].text_input("Título", d.get('Titulo', '---'))
    f_tra = cols[0].text_input("Traductor", d.get('Traductor', '---'))
    f_ilu = cols[0].text_input("Ilustrador", d.get('Ilustrador', '---'))
    f_edi = cols[0].text_input("Editorial", d.get('Editorial', '---'))
    f_col = cols[0].text_input("Colección", d.get('Coleccion', '---'))
    f_pob = cols[0].text_input("Población", d.get('Poblacion', '---'))
    
    f_ano = cols[1].text_input("Año", d.get('Año', '---'))
    f_pri = cols[1].text_input("1ª Edición", d.get('Primera_Edicion', '---'))
    f_tem = cols[1].text_input("Temática", d.get('Tematica', '---'))
    f_cat = cols[1].text_input("Categoría", d.get('Categorias', '---'))
    f_enc = cols[1].text_input("Encuadernación", d.get('Encuadernacion', '---'))
    f_isb = cols[1].text_input("ISBN", d.get('ISBN', '---'))
    f_idi = cols[1].text_input("Idioma", d.get('Idioma', '---'))
    
    f_pag = cols[2].text_input("Páginas", d.get('Paginas', '---'))
    f_med = cols[2].text_input("Medidas", d.get('Medidas', '---'))
    f_pes = cols[2].text_input("Peso", d.get('Peso', '---'))
    f_pre = cols[2].text_input("Precio", d.get('Precio', '---'))
    f_obs = cols[2].text_area("Observaciones", d.get('Observaciones', '---'))

    if st.button("💾 GUARDAR EN EXCEL", type="primary", use_container_width=True):
        try:
            scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
            creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
            client = gspread.authorize(creds)
            sh = client.open(EXCEL_NAME).worksheet(SHEET_NAME)
            
            fila = [id_in, ubi_in, f_aut, f_tit, f_tra, f_ilu, f_edi, f_col, f_pob, f_ano, f_pri, f_tem, f_cat, f_enc, f_isb, f_idi, f_obs, f_pag, f_med, f_pes, f_pre]
            sh.append_row(fila)
            st.success("¡Guardado!")
            st.session_state.datos_extraidos = None
            st.balloons()
        except Exception as e:
            st.error(f"Error al guardar: {e}")

if st.button("🧹 Limpiar"):
    st.session_state.datos_extraidos = None
    st.rerun()
