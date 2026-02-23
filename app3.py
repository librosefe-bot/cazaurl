import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import json
import requests
from bs4 import BeautifulSoup
import re
import base64

# --- FUNCIÓN PARA LIMPIAR LA CLAVE DE GOOGLE SHEETS ---
def limpiar_llave_pem(llave):
    if not llave: return ""
    # Quitar espacios y comillas accidentales
    llave = llave.strip().strip('"').strip("'")
    # Convertir \n de texto a saltos de línea reales
    llave = llave.replace("\\n", "\n")
    # Asegurar que los encabezados PEM sean correctos
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
    
    # Reconstrucción del diccionario de credenciales
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
    st.error(f"❌ Error en la configuración de Secretos: {e}")
    st.stop()

st.set_page_config(page_title="Catalogador Libros IA", layout="wide")

if 'datos_extraidos' not in st.session_state:
    st.session_state.datos_extraidos = None

# --- 2. LÓGICA DE INTELIGENCIA ARTIFICIAL (GEMINI FLASH) ---

def analizar_con_ia(texto, fotos):
    # Usamos Flash 1.5 que tiene la cuota más alta y estable
    modelo = "models/gemini-1.5-flash"
    url_ia = f"https://generativelanguage.googleapis.com/v1beta/{modelo}:generateContent?key={API_KEY}"
    
    # Reducimos texto para no agotar la cuota de tokens (TPM)
    texto_reducido = texto[:2500] 
    
    prompt = """
    Extrae la información de este libro y devuélvela estrictamente en formato JSON plano.
    Campos: Autor, Titulo, Traductor, Ilustrador, Editorial, Coleccion, Poblacion, Año, 
    Primera_Edicion, Tematica, Categorias, Encuadernacion, ISBN, Idioma, 
    Observaciones, Paginas, Medidas, Peso, Precio.
    Reglas: Si no conoces un dato pon '---'. No escribas nada fuera del JSON.
    """
    
    partes = [{"text": f"{prompt}\n\nTexto extraído de la web: {texto_reducido}"}]
    
    # Limitamos a 2 fotos para no superar el límite de tokens por minuto (TPM)
    for f in fotos[:2]: 
        try:
            img_resp = requests.get(f, timeout=5)
            if img_resp.status_code == 200:
                img_data = base64.b64encode(img_resp.content).decode('utf-8')
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
        res_j = res.json()
        
        if 'candidates' in res_j:
            texto_respuesta = res_j['candidates'][0]['content']['parts'][0]['text']
            return json.loads(texto_respuesta)
        else:
            msg = res_j.get('error', {}).get('message', 'Error desconocido de cuota o seguridad')
            st.error(f"⚠️ Google dice: {msg}")
            return None
    except Exception as e:
        st.error(f"❌ Error al procesar con IA: {e}")
        return None

# --- 3. EXTRACCIÓN WEB (SCRAPING) ---

def extraer_datos_web(url):
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        r = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(r.text, 'html.parser')
        
        # Extraer imágenes del lote
        imgs = []
        for img in soup.find_all('img'):
            src = img.get('src', '')
            if 'tcimg' in src or 'cloudfront' in src:
                if src not in imgs: imgs.append(src)
        
        # Extraer descripción principal
        desc = soup.find('div', {'id': 'descriptionContents'})
        texto = desc.get_text(separator=' ', strip=True) if desc else soup.get_text()[:3000]
        
        return texto, imgs
    except Exception as e:
        st.error(f"Error de scraping: {e}")
        return None, []

# --- 4. INTERFAZ DE USUARIO ---

st.title("📚 Catalogador de Libros con IA")
st.markdown("Analiza automáticamente lotes de Todocolección y guarda en Google Sheets.")

with st.container(border=True):
    col1, col2, col3 = st.columns([3, 1, 1])
    with col1: url_input = st.text_input("🔗 URL del lote")
    with col2: id_input = st.text_input("🆔 ID / Código")
    with col3: ubi_input = st.text_input("📍 Ubicación")

if st.button("🚀 Analizar Libro", type="primary", use_container_width=True):
    if url_input and id_input:
        with st.spinner("Extrayendo información y consultando a la IA..."):
            texto_web, fotos = extraer_datos_web(url_input)
            if texto_web:
                resultado = analizar_con_ia(texto_web, fotos)
                if resultado:
                    st.session_state.datos_extraidos = resultado
                    st.success("✅ Análisis realizado con éxito.")
    else:
        st.warning("Por favor, introduce la URL y el ID.")

# --- 5. FORMULARIO Y GUARDADO EN SHEETS ---

if st.session_state.datos_extraidos:
    d = st.session_state.datos_extraidos
    st.divider()
    
    # Formulario dividido en 3 columnas
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
        f_cat = st.text_input("Categoría (CDU)", d.get('Categorias', '---'))
        f_enc = st.text_input("Encuadernación", d.get('Encuadernacion', '---'))
        f_isb = st.text_input("ISBN", d.get('ISBN', '---'))
        f_idi = st.text_input("Idioma", d.get('Idioma', '---'))
    with c3:
        f_pag = st.text_input("Páginas", d.get('Paginas', '---'))
        f_med = st.text_input("Medidas", d.get('Medidas', '---'))
        f_pes = st.text_input("Peso", d.get('Peso', '---'))
        f_pre = st.text_input("Precio", d.get('Precio', '---'))
        f_obs = st.text_area("Observaciones", d.get('Observaciones', '---'), height=155)

    if st.button("💾 CONFIRMAR Y GUARDAR EN EXCEL", type="primary", use_container_width=True):
        try:
            with st.spinner("Guardando en Google Sheets..."):
                scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
                creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
                client = gspread.authorize(creds)
                
                sheet = client.open(EXCEL_NAME).worksheet(SHEET_NAME)
                
                # Mapeo exacto de las 21 columnas
                fila = [
                    id_input, ubi_input, f_aut, f_tit, f_tra, 
                    f_ilu, f_edi, f_col, f_pob, f_ano, 
                    f_pri, f_tem, f_cat, f_enc, f_isb, 
                    f_idi, f_obs, f_pag, f_med, f_pes, f_pre
                ]
                
                sheet.append_row(fila)
                st.balloons()
                st.toast("¡Libro guardado con éxito!", icon="✅")
                st.session_state.datos_extraidos = None
                st.rerun()
        except Exception as e:
            st.error(f"Error al guardar: {e}")

if st.button("🧹 Limpiar"):
    st.session_state.datos_extraidos = None
    st.rerun()
