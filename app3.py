import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import json
import requests
from bs4 import BeautifulSoup
import re
import base64

# --- LIMPIEZA DE CLAVE GOOGLE SHEETS ---
def limpiar_llave_pem(llave):
    if not llave: return ""
    llave = llave.strip().strip('"').strip("'").replace("\\n", "\n")
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
    st.error(f"❌ Error en Secretos: {e}")
    st.stop()

st.set_page_config(page_title="Catalogador Auto-Modelo", layout="wide")

if 'datos_extraidos' not in st.session_state:
    st.session_state.datos_extraidos = None

# --- 2. LÓGICA DE DETECCIÓN DE MODELOS ---

def listar_modelos_disponibles():
    """Consulta a la API qué modelos tiene permitidos esta cuenta."""
    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={API_KEY}"
    try:
        res = requests.get(url).json()
        return [m['name'] for m in res.get('models', []) if 'generateContent' in m['supportedGenerationMethods']]
    except:
        return []

def analizar_con_ia(texto, fotos):
    # Intentamos detectar modelos 2.0 o 1.5 disponibles
    modelos_en_cuenta = listar_modelos_disponibles()
    
    if not modelos_en_cuenta:
        st.error("No se detectaron modelos disponibles. Revisa tu API KEY.")
        return None

    # Prioridad: 2.0 Flash -> 1.5 Flash -> Primero de la lista
    modelo_elegido = None
    for m in modelos_en_cuenta:
        if "gemini-2.0-flash" in m:
            modelo_elegido = m
            break
    if not modelo_elegido:
        for m in modelos_en_cuenta:
            if "1.5-flash" in m:
                modelo_elegido = m
                break
    if not modelo_elegido:
        modelo_elegido = modelos_en_cuenta[0]

    st.info(f"Usando modelo detectado: {modelo_elegido}")
    
    url_ia = f"https://generativelanguage.googleapis.com/v1beta/{modelo_elegido}:generateContent?key={API_KEY}"
    
    prompt = """Responde SOLAMENTE con un objeto JSON. Extrae: Autor, Titulo, Traductor, Ilustrador, Editorial, Coleccion, Poblacion, Año, Primera_Edicion, Tematica, Categorias, Encuadernacion, ISBN, Idioma, Observaciones, Paginas, Medidas, Peso, Precio. Usa '---' si falta el dato."""
    
    partes = [{"text": f"{prompt}\n\nTexto: {texto[:2000]}"}]
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
        res = requests.post(url_ia, json=payload, timeout=25)
        res_j = res.json()
        if 'candidates' in res_j:
            return json.loads(res_j['candidates'][0]['content']['parts'][0]['text'])
        else:
            st.error(f"Error: {res_j.get('error', {}).get('message')}")
            st.write("Modelos disponibles en tu cuenta:", modelos_en_cuenta)
            return None
    except Exception as e:
        st.error(f"Error crítico: {e}")
        return None

# --- 3. SCRAPING Y RESTO ---

def extraer_datos_web(url):
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        r = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(r.text, 'html.parser')
        imgs = [img.get('src') for img in soup.find_all('img') if 'tcimg' in str(img.get('src'))]
        desc = soup.find('div', {'id': 'descriptionContents'})
        texto = desc.get_text(separator=' ', strip=True) if desc else soup.get_text()[:3000]
        return texto, imgs
    except: return None, []

st.title("📚 Catalogador con Auto-Selección de Modelo")

col1, col2, col3 = st.columns([3, 1, 1])
with col1: url_lote = st.text_input("🔗 URL")
with col2: id_lote = st.text_input("🆔 ID")
with col3: ubi_lote = st.text_input("📍 Ubicación")

if st.button("🚀 Analizar"):
    txt, imgs = extraer_datos_web(url_lote)
    if txt:
        res = analizar_con_ia(txt, imgs)
        if res: st.session_state.datos_extraidos = res

if st.session_state.datos_extraidos:
    d = st.session_state.datos_extraidos
    st.divider()
    c1, c2, c3 = st.columns(3)
    # [Campos de entrada iguales al código anterior para ahorrar espacio]
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

    if st.button("💾 GUARDAR"):
        try:
            scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
            creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
            client = gspread.authorize(creds)
            sheet = client.open(EXCEL_NAME).worksheet(SHEET_NAME)
            fila = [id_lote, ubi_lote, f_aut, f_tit, f_tra, f_ilu, f_edi, f_col, f_pob, f_ano, f_pri, f_tem, f_cat, f_enc, f_isb, f_idi, f_obs, f_pag, f_med, f_pes, f_pre]
            sheet.append_row(fila)
            st.success("Guardado")
            st.session_state.datos_extraidos = None
            st.rerun()
        except Exception as e: st.error(f"Error: {e}")
