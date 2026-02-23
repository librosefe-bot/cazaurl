import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import json
import requests
from bs4 import BeautifulSoup
import re
import base64

# --- FUNCIÓN DE LIMPIEZA QUIRÚRGICA PARA LA CLAVE PRIVADA ---
def sanear_llave_google(llave_sucia):
    if not llave_sucia: return ""
    
    # 1. Extraer solo los caracteres válidos de Base64
    # Esto elimina ruidos, espacios accidentales y caracteres invisibles
    cuerpo = re.sub(r'[^A-Za-z0-9+/=]', '', llave_sucia)
    
    # 2. Corrección automática de Padding (Relleno)
    faltante = len(cuerpo) % 4
    if faltante:
        cuerpo += "=" * (4 - faltante)
    
    # 3. Formatear con saltos de línea cada 64 caracteres (Estándar PEM)
    cuerpo_formateado = "\n".join(re.findall(r'.{1,64}', cuerpo))
    
    # 4. Reconstrucción del bloque completo
    return f"-----BEGIN PRIVATE KEY-----\n{cuerpo_formateado}\n-----END PRIVATE KEY-----\n"

# --- 1. CONFIGURACIÓN E INICIALIZACIÓN ---
try:
    # Carga de secretos desde Streamlit Cloud
    API_KEY = st.secrets["GEMINI_API_KEY"]
    g_secrets = st.secrets["GCP_SERVICE_ACCOUNT"]
    EXCEL_NAME = st.secrets["EXCEL_NAME"]
    SHEET_NAME = st.secrets.get("SHEET_NAME", "Hoja 1")
    
    # Saneamiento de la clave para evitar errores de carga
    pk_fix = sanear_llave_google(g_secrets["private_key"])
    
    # Construcción del diccionario de credenciales
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
    st.error(f"❌ Error en la configuración de Secrets: {e}")
    st.stop()

st.set_page_config(page_title="Catalogador Gemini 2.5", layout="wide", page_icon="📚")

if 'datos_extraidos' not in st.session_state:
    st.session_state.datos_extraidos = None

# --- 2. LÓGICA DE IA (GEMINI 2.5 FLASH) ---

def analizar_con_ia(texto, fotos):
    # Usamos la versión estable de la serie 2.5 de tu cuenta
    modelo = "models/gemini-2.5-flash"
    url_ia = f"https://generativelanguage.googleapis.com/v1beta/{modelo}:generateContent?key={API_KEY}"
    
    prompt = """Extrae los datos del libro y devuelve ÚNICAMENTE un objeto JSON.
    Campos requeridos: Autor, Titulo, Traductor, Ilustrador, Editorial, Coleccion, Poblacion, Año, 
    Primera_Edicion, Tematica, Categorias, Encuadernacion, ISBN, Idioma, 
    Observaciones, Paginas, Medidas, Peso, Precio.
    Si no encuentras un dato, usa '---'."""
    
    # Preparación de partes (Texto + Primera Imagen)
    partes = [{"text": f"{prompt}\n\nContenido del lote: {texto[:3500]}"}]
    
    if fotos:
        try:
            # Intentamos procesar solo la primera imagen para no saturar la cuota
            img_resp = requests.get(fotos[0], timeout=5)
            img_data = base64.b64encode(img_resp.content).decode('utf-8')
            partes.append({"inline_data": {"mime_type": "image/jpeg", "data": img_data}})
        except: pass

    payload = {
        "contents": [{"parts": partes}],
        "generationConfig": {
            "temperature": 0.1,
            "response_mime_type": "application/json"
        }
    }

    try:
        res = requests.post(url_ia, json=payload, timeout=30)
        res_data = res.json()
        if 'candidates' in res_data:
            raw_text = res_data['candidates'][0]['content']['parts'][0]['text']
            return json.loads(raw_text)
        return None
    except Exception as e:
        st.error(f"Error en el análisis de IA: {e}")
        return None

# --- 3. EXTRACCIÓN WEB (SCRAPING) ---

def extraer_datos_web(url):
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        r = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(r.text, 'html.parser')
        
        # Obtener imágenes relevantes
        imgs = [img.get('src') for img in soup.find_all('img') if 'tcimg' in str(img.get('src'))]
        
        # Obtener descripción principal
        desc_div = soup.find('div', {'id': 'descriptionContents'})
        texto_lote = desc_div.get_text(separator=' ', strip=True) if desc_div else soup.get_text()[:4000]
        
        return texto_lote, imgs
    except Exception as e:
        st.error(f"Error al leer la web: {e}")
        return None, []

# --- 4. INTERFAZ DE USUARIO ---

st.title("📚 Catalogador Inteligente v4.0")
st.caption("Potenciado por Gemini 2.5 Flash y Google Sheets")

with st.container(border=True):
    c1, c2, c3 = st.columns([3, 1, 1])
    with c1: url_input = st.text_input("🔗 URL del Lote")
    with c2: id_input = st.text_input("🆔 ID Interno")
    with c3: ubi_input = st.text_input("📍 Ubicación")

if st.button("🚀 Analizar Libro", type="primary", use_container_width=True):
    if url_input and id_input:
        with st.spinner("Gemini 2.5 está leyendo el lote..."):
            texto, imagenes = extraer_datos_web(url_input)
            if texto:
                resultado = analizar_con_ia(texto, imagenes)
                if resultado:
                    st.session_state.datos_extraidos = resultado
                    st.success("¡Datos extraídos con éxito!")
    else:
        st.warning("Por favor, rellena al menos la URL y el ID.")

# --- 5. RESULTADOS Y GUARDADO ---

if st.session_state.datos_extraidos:
    d = st.session_state.datos_extraidos
    st.divider()
    
    # Formulario de edición
    col_a, col_b, col_c = st.columns(3)
    with col_a:
        f_aut = st.text_input("Autor", d.get('Autor', '---'))
        f_tit = st.text_input("Título", d.get('Titulo', '---'))
        f_tra = st.text_input("Traductor", d.get('Traductor', '---'))
        f_ilu = st.text_input("Ilustrador", d.get('Ilustrador', '---'))
        f_edi = st.text_input("Editorial", d.get('Editorial', '---'))
        f_col = st.text_input("Colección", d.get('Coleccion', '---'))
        f_pob = st.text_input("Población", d.get('Poblacion', '---'))
    with col_b:
        f_ano = st.text_input("Año", d.get('Año', '---'))
        f_pri = st.text_input("1ª Edición", d.get('Primera_Edicion', '---'))
        f_tem = st.text_input("Temática", d.get('Tematica', '---'))
        f_cat = st.text_input("Categoría", d.get('Categorias', '---'))
        f_enc = st.text_input("Encuadernación", d.get('Encuadernacion', '---'))
        f_isb = st.text_input("ISBN", d.get('ISBN', '---'))
        f_idi = st.text_input("Idioma", d.get('Idioma', '---'))
    with col_c:
        f_pag = st.text_input("Páginas", d.get('Paginas', '---'))
        f_med = st.text_input("Medidas", d.get('Medidas', '---'))
        f_pes = st.text_input("Peso", d.get('Peso', '---'))
        f_pre = st.text_input("Precio", d.get('Precio', '---'))
        f_obs = st.text_area("Observaciones", d.get('Observaciones', '---'), height=155)

    if st.button("💾 CONFIRMAR Y GUARDAR", type="primary", use_container_width=True):
        try:
            # Conexión a Google Sheets
            scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
            creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
            client = gspread.authorize(creds)
            
            # Apertura del documento
            sheet = client.open(EXCEL_NAME).worksheet(SHEET_NAME)
            
            # Preparación de la fila
            nueva_fila = [
                id_input, ubi_input, f_aut, f_tit, f_tra, f_ilu, f_edi, f_col, f_pob, 
                f_ano, f_pri, f_tem, f_cat, f_enc, f_isb, f_idi, f_obs, f_pag, f_med, f_pes, f_pre
            ]
            
            sheet.append_row(nueva_fila)
            st.balloons()
            st.toast("✅ Fila añadida correctamente al Excel")
            
            # Limpiar estado para el siguiente libro
            st.session_state.datos_extraidos = None
            st.rerun()
            
        except Exception as e:
            st.error(f"❌ Error al guardar en Google Sheets: {e}")

if st.button("🧹 Limpiar Formulario"):
    st.session_state.datos_extraidos = None
    st.rerun()
