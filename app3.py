import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import json
import requests
from bs4 import BeautifulSoup
import re
import base64

# --- FUNCIÓN CRÍTICA: LIMPIADOR DE LLAVE PEM ---
def limpiar_llave_pem(llave):
    """Limpia la private_key de errores comunes de copy-paste."""
    if not llave:
        return ""
    # Quitar espacios en blanco y comillas accidentales
    llave = llave.strip().strip('"').strip("'")
    # Convertir el texto '\n' en saltos de línea reales
    llave = llave.replace("\\n", "\n")
    # Asegurar que empiece y termine correctamente sin basura alrededor
    inicio = "-----BEGIN PRIVATE KEY-----"
    fin = "-----END PRIVATE KEY-----"
    if inicio in llave and fin in llave:
        llave_limpia = inicio + llave.split(inicio)[1].split(fin)[0] + fin
        return llave_limpia
    return llave

# --- 1. CONFIGURACIÓN DE SECRETOS Y CREDENCIALES ---
try:
    # 1.1. Datos de Gemini
    API_KEY = st.secrets["GEMINI_API_KEY"]
    
    # 1.2. Datos de Google Sheets (Extracción segura)
    g_secrets = st.secrets["GCP_SERVICE_ACCOUNT"]
    EXCEL_NAME = st.secrets["EXCEL_NAME"]
    SHEET_NAME = st.secrets.get("SHEET_NAME", "Hoja 1")
    
    # 1.3. Reconstrucción del diccionario de credenciales con limpieza de llave
    creds_dict = {
        "type": g_secrets["type"],
        "project_id": g_secrets["project_id"],
        "private_key_id": g_secrets["private_key_id"],
        "private_key": limpiar_llave_pem(g_secrets["private_key"]),
        "client_email": g_secrets["client_email"],
        "client_id": g_secrets["client_id"],
        "auth_uri": g_secrets["auth_uri"],
        "token_uri": g_secrets["token_uri"],
        "auth_provider_x509_cert_url": g_secrets["auth_provider_x509_cert_url"],
        "client_x509_cert_url": g_secrets["client_x509_cert_url"]
    }
except Exception as e:
    st.error(f"❌ Error configurando Secretos: {e}")
    st.stop()

# Configuración básica de la App
st.set_page_config(page_title="Catalogador IA v3", layout="wide", page_icon="📚")

if 'datos_extraidos' not in st.session_state:
    st.session_state.datos_extraidos = None

# --- 2. LÓGICA DE EXTRACCIÓN Y IA ---

def extraer_datos_web(url):
    """Scraping de Todocolección."""
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        r = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(r.text, 'html.parser')
        
        # Imágenes
        imgs = [img.get('src') for img in soup.find_all('img') if 'tcimg' in str(img.get('src'))]
        # Texto descriptivo
        desc = soup.find('div', {'id': 'descriptionContents'})
        texto = desc.get_text(separator=' ', strip=True) if desc else soup.get_text()[:4000]
        
        return texto, imgs[:5]
    except Exception as e:
        st.error(f"Error en el scraping: {e}")
        return None, []

def analizar_con_ia(texto, fotos):
    """Consulta a Gemini 1.5 Flash."""
    url_ia = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={API_KEY}"
    
    prompt = """
    Extrae la información de este libro y devuélvela estrictamente en formato JSON.
    Campos: Autor, Titulo, Traductor, Ilustrador, Editorial, Coleccion, Poblacion, Año, 
    Primera_Edicion, Tematica, Categorias, Encuadernacion, ISBN, Idioma, 
    Observaciones, Paginas, Medidas, Peso, Precio.
    Si no encuentras un dato, usa '---'.
    """
    
    partes = [{"text": f"{prompt}\nContenido: {texto}"}]
    for f in fotos:
        try:
            img_data = base64.b64encode(requests.get(f).content).decode('utf-8')
            partes.append({"inline_data": {"mime_type": "image/jpeg", "data": img_data}})
        except: continue

    payload = {"contents": [{"parts": partes}], "generationConfig": {"response_mime_type": "application/json"}}
    
    try:
        res = requests.post(url_ia, json=payload)
        return json.loads(res.json()['candidates'][0]['content']['parts'][0]['text'])
    except Exception as e:
        st.error(f"Error IA: {e}")
        return None

# --- 3. INTERFAZ DE USUARIO ---

st.title("📖 Catalogador Automático Pro")
st.info("Introduce la URL y el ID para empezar.")

with st.expander("⚙️ Configuración de Entrada", expanded=True):
    col1, col2, col3 = st.columns([3, 1, 1])
    with col1: url_lote = st.text_input("🔗 URL de Todocolección")
    with col2: id_interno = st.text_input("🆔 ID Libro")
    with col3: ubicacion = st.text_input("📍 Ubicación")

if st.button("🔍 Analizar Libro", type="primary", use_container_width=True):
    if url_lote and id_interno:
        with st.spinner("Leyendo web y consultando a la IA..."):
            txt, imgs = extraer_datos_web(url_lote)
            resultado = analizar_con_ia(txt, imgs)
            if resultado:
                st.session_state.datos_extraidos = resultado
                st.success("¡Análisis completado!")
    else:
        st.warning("Faltan campos obligatorios (URL o ID).")

# --- 4. FORMULARIO DE REVISIÓN Y GUARDADO ---

if st.session_state.datos_extraidos:
    d = st.session_state.datos_extraidos
    st.divider()
    
    # 3 Columnas para edición rápida
    c_a, c_b, c_c = st.columns(3)
    with c_a:
        f_aut = st.text_input("Autor", d.get('Autor', '---'))
        f_tit = st.text_input("Título", d.get('Titulo', '---'))
        f_tra = st.text_input("Traductor", d.get('Traductor', '---'))
        f_ilu = st.text_input("Ilustrador", d.get('Ilustrador', '---'))
        f_edi = st.text_input("Editorial", d.get('Editorial', '---'))
        f_col = st.text_input("Colección", d.get('Coleccion', '---'))
        f_pob = st.text_input("Población", d.get('Poblacion', '---'))
    with c_b:
        f_ano = st.text_input("Año", d.get('Año', '---'))
        f_pri = st.text_input("1ª Edición", d.get('Primera_Edicion', '---'))
        f_tem = st.text_input("Temática", d.get('Tematica', '---'))
        f_cat = st.text_input("Categoría (CDU)", d.get('Categorias', '---'))
        f_enc = st.text_input("Encuadernación", d.get('Encuadernacion', '---'))
        f_isb = st.text_input("ISBN", d.get('ISBN', '---'))
        f_idi = st.text_input("Idioma", d.get('Idioma', '---'))
    with c_c:
        f_pag = st.text_input("Páginas", d.get('Paginas', '---'))
        f_med = st.text_input("Medidas", d.get('Medidas', '---'))
        f_pes = st.text_input("Peso", d.get('Peso', '---'))
        f_pre = st.text_input("Precio", d.get('Precio', '---'))
        f_obs = st.text_area("Observaciones", d.get('Observaciones', '---'), height=155)

    if st.button("💾 CONFIRMAR Y GUARDAR EN GOOGLE SHEETS", type="primary", use_container_width=True):
        try:
            with st.spinner("Conectando con Google Sheets..."):
                # Uso de Credentials de google-auth (Solución al error PEM/Base64)
                scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
                creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
                client = gspread.authorize(creds)
                
                # Acceso a la hoja
                sheet = client.open(EXCEL_NAME).worksheet(SHEET_NAME)
                
                # Preparar las 21 columnas
                fila = [
                    id_interno, ubicacion, f_aut, f_tit, f_tra, 
                    f_ilu, f_edi, f_col, f_pob, f_ano, 
                    f_pri, f_tem, f_cat, f_enc, f_isb, 
                    f_idi, f_obs, f_pag, f_med, f_pes, f_pre
                ]
                
                sheet.append_row(fila)
                st.balloons()
                st.toast("¡Guardado correctamente!", icon="✅")
                st.session_state.datos_extraidos = None # Reset
                st.rerun()
                
        except Exception as e:
            st.error(f"❌ Error al guardar: {e}")
            st.info("Verifica que hayas compartido el Excel con el email de la cuenta de servicio.")

if st.button("🧹 Limpiar"):
    st.session_state.datos_extraidos = None
    st.rerun()
