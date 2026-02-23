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
    if not llave: return ""
    llave = llave.strip().strip('"').strip("'")
    llave = llave.replace("\\n", "\n")
    inicio = "-----BEGIN PRIVATE KEY-----"
    fin = "-----END PRIVATE KEY-----"
    if inicio in llave and fin in llave:
        return inicio + llave.split(inicio)[1].split(fin)[0] + fin
    return llave

# --- 1. CONFIGURACIÓN DE SECRETOS ---
try:
    API_KEY = st.secrets["GEMINI_API_KEY"]
    g_secrets = st.secrets["GCP_SERVICE_ACCOUNT"]
    EXCEL_NAME = st.secrets["EXCEL_NAME"]
    SHEET_NAME = st.secrets.get("SHEET_NAME", "Hoja 1")
    
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

st.set_page_config(page_title="Catalogador IA v3", layout="wide", page_icon="📚")

if 'datos_extraidos' not in st.session_state:
    st.session_state.datos_extraidos = None

# --- 2. LÓGICA DE EXTRACCIÓN Y IA ---

def extraer_datos_web(url):
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        r = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(r.text, 'html.parser')
        imgs = [img.get('src') for img in soup.find_all('img') if 'tcimg' in str(img.get('src'))]
        desc = soup.find('div', {'id': 'descriptionContents'})
        texto = desc.get_text(separator=' ', strip=True) if desc else soup.get_text()[:4000]
        return texto, imgs[:5]
    except Exception as e:
        st.error(f"Error en el scraping: {e}")
        return None, []

def analizar_con_ia(texto, fotos):
    # Usamos el modelo 1.5-flash que es el más estable para JSON
    url_ia = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={API_KEY}"
    
    prompt = """
    Extrae la información de este libro y devuélvela estrictamente en formato JSON plano.
    Campos requeridos: Autor, Titulo, Traductor, Ilustrador, Editorial, Coleccion, Poblacion, Año, 
    Primera_Edicion, Tematica, Categorias, Encuadernacion, ISBN, Idioma, 
    Observaciones, Paginas, Medidas, Peso, Precio.
    Reglas: Si no sabes un dato pon '---'. No añadas texto fuera del JSON.
    """
    
    partes = [{"text": f"{prompt}\nTexto del lote: {texto}"}]
    
    for f in fotos:
        try:
            response = requests.get(f)
            if response.status_code == 200:
                img_data = base64.b64encode(response.content).decode('utf-8')
                partes.append({"inline_data": {"mime_type": "image/jpeg", "data": img_data}})
        except: continue

    payload = {
        "contents": [{"parts": partes}],
        "generationConfig": {
            "response_mime_type": "application/json",
            "temperature": 0.1
        }
    }
    
    try:
        res = requests.post(url_ia, json=payload)
        res_json = res.json()
        
        # DEBUG: Si no hay 'candidates', imprimimos el error real de Google
        if 'candidates' not in res_json:
            if 'error' in res_json:
                st.error(f"Error de Google API: {res_json['error']['message']}")
            else:
                st.error(f"La IA bloqueó la respuesta por seguridad o formato. Respuesta: {res_json}")
            return None
            
        texto_ia = res_json['candidates'][0]['content']['parts'][0]['text']
        return json.loads(texto_ia)
    except Exception as e:
        st.error(f"Error procesando respuesta de IA: {e}")
        return None

# --- 3. INTERFAZ ---

st.title("📖 Catalogador Automático Pro")

with st.expander("⚙️ Configuración de Entrada", expanded=True):
    col1, col2, col3 = st.columns([3, 1, 1])
    with col1: url_lote = st.text_input("🔗 URL de Todocolección")
    with col2: id_interno = st.text_input("🆔 ID Libro")
    with col3: ubicacion = st.text_input("📍 Ubicación")

if st.button("🔍 Analizar Libro", type="primary", use_container_width=True):
    if url_lote and id_interno:
        with st.spinner("Leyendo web y consultando a la IA..."):
            txt, imgs = extraer_datos_web(url_lote)
            if txt:
                resultado = analizar_con_ia(txt, imgs)
                if resultado:
                    st.session_state.datos_extraidos = resultado
                    st.success("¡Análisis completado!")
            else:
                st.error("No se pudo extraer texto de la URL.")
    else:
        st.warning("Faltan campos obligatorios (URL o ID).")

# --- 4. FORMULARIO Y GUARDADO ---

if st.session_state.datos_extraidos:
    d = st.session_state.datos_extraidos
    st.divider()
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

    if st.button("💾 GUARDAR EN GOOGLE SHEETS", type="primary", use_container_width=True):
        try:
            scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
            creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
            client = gspread.authorize(creds)
            sheet = client.open(EXCEL_NAME).worksheet(SHEET_NAME)
            
            fila = [id_interno, ubicacion, f_aut, f_tit, f_tra, f_ilu, f_edi, f_col, f_pob, f_ano, f_pri, f_tem, f_cat, f_enc, f_isb, f_idi, f_obs, f_pag, f_med, f_pes, f_pre]
            
            sheet.append_row(fila)
            st.balloons()
            st.success("✅ ¡Guardado!")
            st.session_state.datos_extraidos = None
            st.rerun()
        except Exception as e:
            st.error(f"Error al guardar: {e}")

if st.button("🧹 Limpiar"):
    st.session_state.datos_extraidos = None
    st.rerun()
