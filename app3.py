import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import json
import requests
from bs4 import BeautifulSoup
import re
import base64

# --- FUNCIÓN DE LIMPIEZA ---
def sanear_llave_google(llave_sucia):
    if not llave_sucia: return ""
    cuerpo = re.sub(r'[^A-Za-z0-9+/=]', '', llave_sucia)
    faltante = len(cuerpo) % 4
    if faltante: cuerpo += "=" * (4 - faltante)
    cuerpo_formateado = "\n".join(re.findall(r'.{1,64}', cuerpo))
    return f"-----BEGIN PRIVATE KEY-----\n{cuerpo_formateado}\n-----END PRIVATE KEY-----\n"

# --- CONFIGURACIÓN DE SECRETOS ---
try:
    API_KEY = st.secrets["GEMINI_API_KEY"]
    g_secrets = st.secrets["GCP_SERVICE_ACCOUNT"]
    EXCEL_NAME = st.secrets["EXCEL_NAME"]
    SHEET_NAME = st.secrets.get("SHEET_NAME", "Hoja 1")
    pk_fix = sanear_llave_google(g_secrets["private_key"])
    creds_dict = {
        "type": "service_account",
        "project_id": g_secrets["project_id"],
        "private_key_id": g_secrets["private_key_id"],
        "private_key": pk_fix,
        "client_email": g_secrets["client_email"],
        "client_id": g_secrets["client_id"],
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
        "client_x509_cert_url": g_secrets["client_x509_cert_url"]
    }
except Exception as e:
    st.error(f"Error en Secrets: {e}")
    st.stop()

st.set_page_config(page_title="Catalogador Gemini 2.5", layout="wide")

# --- ESTADO DE LA SESIÓN ---
if 'datos_extraidos' not in st.session_state:
    st.session_state.datos_extraidos = None

# --- FUNCIONES ---
def analizar_con_ia(texto, fotos):
    modelo = "models/gemini-2.5-flash"
    url_ia = f"https://generativelanguage.googleapis.com/v1beta/{modelo}:generateContent?key={API_KEY}"
    prompt = "Extrae los datos del libro en JSON plano. Campos: Autor, Titulo, Traductor, Ilustrador, Editorial, Coleccion, Poblacion, Año, Primera_Edicion, Tematica, Categorias, Encuadernacion, ISBN, Idioma, Observaciones, Paginas, Medidas, Peso, Precio. Usa '---' si falta."
    
    partes = [{"text": f"{prompt}\n\nTexto: {texto[:3000]}"}]
    if fotos:
        try:
            img_data = base64.b64encode(requests.get(fotos[0]).content).decode('utf-8')
            partes.append({"inline_data": {"mime_type": "image/jpeg", "data": img_data}})
        except: pass

    payload = {"contents": [{"parts": partes}], "generationConfig": {"temperature": 0.1, "response_mime_type": "application/json"}}
    
    res = requests.post(url_ia, json=payload, timeout=30)
    if res.status_code == 200:
        return json.loads(res.json()['candidates'][0]['content']['parts'][0]['text'])
    else:
        st.error(f"Error API Gemini: {res.text}")
        return None

def extraer_web(url):
    try:
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        soup = BeautifulSoup(r.text, 'html.parser')
        imgs = [img.get('src') for img in soup.find_all('img') if 'tcimg' in str(img.get('src'))]
        desc = soup.find('div', {'id': 'descriptionContents'})
        texto = desc.get_text(strip=True) if desc else soup.get_text()[:3000]
        return texto, imgs
    except Exception as e:
        st.error(f"Error Web: {e}")
        return None, []

# --- INTERFAZ ---
st.title("📚 Catalogador v4.1")

col1, col2, col3 = st.columns([3, 1, 1])
url_input = col1.text_input("🔗 URL")
id_input = col2.text_input("🆔 ID")
ubi_input = col3.text_input("📍 Ubicación")

# BOTÓN CON LÓGICA DE PERSISTENCIA
if st.button("🚀 ANALIZAR AHORA", type="primary", use_container_width=True):
    if not url_input or not id_input:
        st.warning("Falta URL o ID")
    else:
        with st.spinner("1. Extrayendo texto de la web..."):
            txt, imgs = extraer_web(url_input)
        
        if txt:
            with st.spinner("2. La IA está procesando los datos..."):
                resultado = analizar_con_ia(txt, imgs)
                if resultado:
                    st.session_state.datos_extraidos = resultado
                    st.rerun() # Forzamos el refresco para mostrar el formulario
                else:
                    st.error("La IA no devolvió datos. Revisa tu API KEY.")

# --- FORMULARIO (Solo aparece si hay datos) ---
if st.session_state.datos_extraidos:
    st.divider()
    d = st.session_state.datos_extraidos
    c1, c2, c3 = st.columns(3)
    
    # Rellenar campos
    f_aut = c1.text_input("Autor", d.get('Autor', '---'))
    f_tit = c1.text_input("Título", d.get('Titulo', '---'))
    f_tra = c1.text_input("Traductor", d.get('Traductor', '---'))
    f_ilu = c1.text_input("Ilustrador", d.get('Ilustrador', '---'))
    f_edi = c1.text_input("Editorial", d.get('Editorial', '---'))
    f_col = c1.text_input("Colección", d.get('Coleccion', '---'))
    f_pob = c1.text_input("Población", d.get('Poblacion', '---'))
    
    f_ano = c2.text_input("Año", d.get('Año', '---'))
    f_pri = c2.text_input("1ª Edición", d.get('Primera_Edicion', '---'))
    f_tem = c2.text_input("Temática", d.get('Tematica', '---'))
    f_cat = c2.text_input("Categoría", d.get('Categorias', '---'))
    f_enc = c2.text_input("Encuadernación", d.get('Encuadernacion', '---'))
    f_isb = c2.text_input("ISBN", d.get('ISBN', '---'))
    f_idi = c2.text_input("Idioma", d.get('Idioma', '---'))
    
    f_pag = c3.text_input("Páginas", d.get('Paginas', '---'))
    f_med = c3.text_input("Medidas", d.get('Medidas', '---'))
    f_pes = c3.text_input("Peso", d.get('Peso', '---'))
    f_pre = c3.text_input("Precio", d.get('Precio', '---'))
    f_obs = c3.text_area("Observaciones", d.get('Observaciones', '---'))

    if st.button("💾 GUARDAR EN EXCEL", type="primary", use_container_width=True):
        try:
            scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
            creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
            client = gspread.authorize(creds)
            sheet = client.open(EXCEL_NAME).worksheet(SHEET_NAME)
            
            fila = [id_input, ubi_input, f_aut, f_tit, f_tra, f_ilu, f_edi, f_col, f_pob, f_ano, f_pri, f_tem, f_cat, f_enc, f_isb, f_idi, f_obs, f_pag, f_med, f_pes, f_pre]
            sheet.append_row(fila)
            st.success("¡Guardado!")
            st.session_state.datos_extraidos = None
            st.rerun()
        except Exception as e:
            st.error(f"Error al guardar: {e}")

if st.button("🧹 Limpiar"):
    st.session_state.datos_extraidos = None
    st.rerun()
