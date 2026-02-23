import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import json
import requests
from bs4 import BeautifulSoup
import re
import base64

# --- FUNCIÓN DE SANEAMIENTO DEFINITIVO (SOLUCIONA INVALID PADDING E INVALID BYTE) ---
def sanear_llave_google(llave_sucia):
    if not llave_sucia: return ""
    
    # 1. Extraemos solo los caracteres válidos de Base64 (A-Z, a-z, 0-9, +, /, =)
    # Esto elimina guiones iniciales, espacios, saltos de línea mal pegados y bytes basura
    cuerpo = re.sub(r'[^A-Za-z0-9+/=]', '', llave_sucia)
    
    # 2. Corregimos el Padding (Relleno)
    # Base64 requiere que la longitud sea múltiplo de 4
    faltante = len(cuerpo) % 4
    if faltante:
        cuerpo += "=" * (4 - faltante)
    
    # 3. Formateamos a 64 caracteres por línea (Estándar RFC 7468)
    cuerpo_formateado = "\n".join(re.findall(r'.{1,64}', cuerpo))
    
    # 4. Reconstruimos el bloque PEM con sus etiquetas exactas
    llave_final = (
        "-----BEGIN PRIVATE KEY-----\n" +
        cuerpo_formateado +
        "\n-----END PRIVATE KEY-----\n"
    )
    return llave_final

# --- 1. CARGA DE CONFIGURACIÓN ---
try:
    API_KEY = st.secrets["GEMINI_API_KEY"]
    g_secrets = st.secrets["GCP_SERVICE_ACCOUNT"]
    EXCEL_NAME = st.secrets["EXCEL_NAME"]
    SHEET_NAME = st.secrets.get("SHEET_NAME", "Hoja 1")
    
    # Saneamos la clave privada antes de crear el diccionario de credenciales
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
    st.error(f"❌ Error en Secretos: {e}")
    st.stop()

st.set_page_config(page_title="Catalogador Gemini 2.5", layout="wide")

if 'datos_extraidos' not in st.session_state:
    st.session_state.datos_extraidos = None

# --- 2. LÓGICA DE IA (GEMINI 2.5 FLASH) ---

def analizar_con_ia(texto, fotos):
    # Usamos el modelo estrella confirmado en tu cuenta
    modelo = "models/gemini-2.5-flash"
    url_ia = f"https://generativelanguage.googleapis.com/v1beta/{modelo}:generateContent?key={API_KEY}"
    
    prompt = """Extrae los datos del libro y responde UNICAMENTE en JSON plano. 
    Campos: Autor, Titulo, Traductor, Ilustrador, Editorial, Coleccion, Poblacion, Año, 
    Primera_Edicion, Tematica, Categorias, Encuadernacion, ISBN, Idioma, 
    Observaciones, Paginas, Medidas, Peso, Precio.
    Usa '---' para datos no encontrados."""
    
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
    except:
        return None

# --- 3. EXTRACCIÓN WEB (SCRAPING) ---

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

st.title("📚 Catalogador Profesional v3.8")

col1, col2, col3 = st.columns([3, 1, 1])
with col1: url_lote = st.text_input("🔗 URL Todocolección")
with col2: id_lote = st.text_input("🆔 ID / Lote")
with col3: ubi_lote = st.text_input("📍 Ubicación")

if st.button("🚀 Analizar Lote", type="primary", use_container_width=True):
    if url_lote and id_lote:
        with st.spinner("Analizando con Gemini 2.5..."):
            txt, imgs = extraer_datos_web(url_lote)
            if txt:
                res = analizar_con_ia(txt, imgs)
                if res: 
                    st.session_state.datos_extraidos = res
                    st.success("Análisis terminado.")
    else: st.warning("URL e ID son obligatorios.")

# --- 5. VISUALIZACIÓN Y GUARDADO ---

if st.session_state.datos_extraidos:
    d = st.session_state.datos_extraidos
    st.divider()
    c1, c2, c3 = st.columns(3)
    
    with c1:
        f_aut = st.text_input("Autor", d.get('Autor', '---'))
        f_tit = st.text_input("Título", d.get('Titulo', '---'))
        f_tra = st.text_input("Traductor", d.get('Traductor', '---'))
        f_ilu = st.text_input("Ilustrador", d.get('Ilustrador', '---'))
        f_edi = st.text_input("Editorial", d.get('Editorial', '---'))
        f_col = st.text_input("Colección", d.get('Coleccion', '---'))
        f_pob = st.text_input("Población", d.get('Poblacion', '---'))
    with c2:
        f_ano = st.text_input("Año", d.get('Año', '---'))
        f_pri = st.text_input("1ª Edición", d.get('Primera_Edicion', '---'))
        f_tem = st.text_input("Temática", d.get('Tematica', '---'))
        f_cat = st.text_input("Categoría", d.get('Categorias', '---'))
        f_enc = st.text_input("Encuadernación", d.get('Encuadernacion', '---'))
        f_isb = st.text_input("ISBN", d.get('ISBN', '---'))
        f_idi = st.text_input("Idioma", d.get('Idioma', '---'))
    with c3:
        f_pag = st.text_input("Páginas", d.get('Paginas', '---'))
        f_med = st.text_input("Medidas", d.get('Medidas', '---'))
        f_pes = st.text_input("Peso", d.get('Peso', '---'))
        f_pre = st.text_input("Precio", d.get('Precio', '---'))
        f_obs = st.text_area("Observaciones", d.get('Observaciones', '---'))

    if st.button("💾 GUARDAR EN GOOGLE SHEETS", type="primary", use_container_width=True):
        try:
            scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
            creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
            client = gspread.authorize(creds)
            sheet = client.open(EXCEL_NAME).worksheet(SHEET_NAME)
            
            fila = [id_lote, ubi_lote, f_aut, f_tit, f_tra, f_ilu, f_edi, f_col, f_pob, f_ano, f_pri, f_tem, f_cat, f_enc, f_isb, f_idi, f_obs, f_pag, f_med, f_pes, f_pre]
            sheet.append_row(fila)
            
            st.success("✅ Guardado en la nube")
            st.session_state.datos_extraidos = None
            st.rerun()
        except Exception as e:
            st.error(f"❌ Error al conectar con Sheets: {e}")

if st.button("🧹 Limpiar"):
    st.session_state.datos_extraidos = None
    st.rerun()
