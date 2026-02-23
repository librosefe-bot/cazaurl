import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import json
import requests
from bs4 import BeautifulSoup
import re
import base64

# --- 1. FUNCIÓN DE LIMPIEZA DEFINITIVA (SOLUCIONA EL ERROR PEM / BYTE 61) ---
def sanear_llave_google(llave_sucia):
    if not llave_sucia: 
        return ""
    
    # Eliminar etiquetas y limpiar ruidos (espacios, saltos de línea literales)
    cuerpo = llave_sucia.replace("-----BEGIN PRIVATE KEY-----", "")
    cuerpo = cuerpo.replace("-----END PRIVATE KEY-----", "")
    cuerpo = cuerpo.replace("\\n", "").replace("\n", "").replace(" ", "").strip()
    
    # ELIMINACIÓN DE CARACTERES EXTRAÑOS: Solo permitimos Base64 puro
    # Esto elimina cualquier signo '=' que esté en una posición incorrecta (Byte 61)
    cuerpo = re.sub(r'[^A-Za-z0-9+/]', '', cuerpo)
    
    # REPARACIÓN DEL PADDING: El Base64 debe ser múltiplo de 4
    faltante = len(cuerpo) % 4
    if faltante:
        cuerpo += "=" * (4 - faltante)
    
    # FORMATEO PEM: Bloques de 64 caracteres
    lineas = [cuerpo[i:i+64] for i in range(0, len(cuerpo), 64)]
    cuerpo_final = "\n".join(lineas)
    
    return f"-----BEGIN PRIVATE KEY-----\n{cuerpo_final}\n-----END PRIVATE KEY-----\n"

# --- 2. CARGA DE CONFIGURACIÓN Y SECRETOS ---
try:
    API_KEY = st.secrets["GEMINI_API_KEY"].strip()
    EXCEL_NAME = st.secrets["EXCEL_NAME"]
    SHEET_NAME = st.secrets.get("SHEET_NAME", "Hoja 1")
    
    g_secrets = st.secrets["GCP_SERVICE_ACCOUNT"]
    
    # Aplicamos la limpieza a la clave privada antes de crear el diccionario
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
    st.error(f"⚠️ Error cargando Secrets: {e}")
    st.stop()

# --- 3. CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Catalogador Libros v4.2", layout="wide", page_icon="📚")

if 'datos_extraidos' not in st.session_state:
    st.session_state.datos_extraidos = None

# --- 4. FUNCIONES DE LÓGICA ---

def extraer_datos_web(url):
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        r = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(r.text, 'html.parser')
        
        # Imágenes de Todocolección
        imgs = [img.get('src') for img in soup.find_all('img') if 'tcimg' in str(img.get('src'))]
        
        # Texto de la descripción
        desc_div = soup.find('div', {'id': 'descriptionContents'})
        texto_lote = desc_div.get_text(separator=' ', strip=True) if desc_div else soup.get_text()[:3500]
        
        return texto_lote, imgs
    except Exception as e:
        st.error(f"Error al leer la web: {e}")
        return None, []

def analizar_con_ia(texto, fotos):
    # Usamos Gemini 1.5 Flash (o 2.0 si está disponible en tu región)
    url_ia = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={API_KEY}"
    
    prompt = """Extrae los datos del libro y devuelve ÚNICAMENTE un JSON. 
    Campos: Autor, Titulo, Traductor, Ilustrador, Editorial, Coleccion, Poblacion, Año, 
    Primera_Edicion, Tematica, Categorias, Encuadernacion, ISBN, Idioma, 
    Observaciones, Paginas, Medidas, Peso, Precio. Usa '---' si falta."""
    
    partes = [{"text": f"{prompt}\n\nTexto: {texto[:3000]}"}]
    
    if fotos:
        try:
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
            raw_text = res.json()['candidates'][0]['content']['parts'][0]['text']
            return json.loads(raw_text)
        else:
            st.error(f"Error Gemini API: {res.text}")
            return None
    except Exception as e:
        st.error(f"Error en análisis: {e}")
        return None

# --- 5. INTERFAZ DE USUARIO ---

st.title("📚 Catalogador Inteligente")
st.write("Extrae datos automáticamente y guarda en Google Sheets.")

with st.container(border=True):
    col_u, col_i, col_p = st.columns([3, 1, 1])
    url_input = col_u.text_input("🔗 URL del lote")
    id_input = col_i.text_input("🆔 ID Interno")
    ubi_input = col_p.text_input("📍 Ubicación")

if st.button("🚀 Analizar Lote", type="primary", use_container_width=True):
    if url_input and id_input:
        with st.spinner("Leyendo web y consultando a la IA..."):
            txt, imgs = extraer_datos_web(url_input)
            if txt:
                res = analizar_con_ia(txt, imgs)
                if res:
                    st.session_state.datos_extraidos = res
                    st.rerun()
    else:
        st.warning("Escribe la URL y el ID.")

# --- 6. FORMULARIO DE RESULTADOS ---

if st.session_state.datos_extraidos:
    st.divider()
    d = st.session_state.datos_extraidos
    
    c1, c2, c3 = st.columns(3)
    # Campos Autor...
    f_aut = c1.text_input("Autor", d.get('Autor', '---'))
    f_tit = c1.text_input("Título", d.get('Titulo', '---'))
    f_tra = c1.text_input("Traductor", d.get('Traductor', '---'))
    f_ilu = c1.text_input("Ilustrador", d.get('Ilustrador', '---'))
    f_edi = c1.text_input("Editorial", d.get('Editorial', '---'))
    f_col = c1.text_input("Colección", d.get('Coleccion', '---'))
    f_pob = c1.text_input("Población", d.get('Poblacion', '---'))
    # Campos Año...
    f_ano = c2.text_input("Año", d.get('Año', '---'))
    f_pri = c2.text_input("1ª Edición", d.get('Primera_Edicion', '---'))
    f_tem = c2.text_input("Temática", d.get('Tematica', '---'))
    f_cat = c2.text_input("Categoría", d.get('Categorias', '---'))
    f_enc = c2.text_input("Encuadernación", d.get('Encuadernacion', '---'))
    f_isb = c2.text_input("ISBN", d.get('ISBN', '---'))
    f_idi = c2.text_input("Idioma", d.get('Idioma', '---'))
    # Campos físicos...
    f_pag = c3.text_input("Páginas", d.get('Paginas', '---'))
    f_med = c3.text_input("Medidas", d.get('Medidas', '---'))
    f_pes = c3.text_input("Peso", d.get('Peso', '---'))
    f_pre = c3.text_input("Precio", d.get('Precio', '---'))
    f_obs = c3.text_area("Observaciones", d.get('Observaciones', '---'))

    if st.button("💾 GUARDAR EN GOOGLE SHEETS", type="primary", use_container_width=True):
        try:
            # Autenticación con Google
            scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
            creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
            client = gspread.authorize(creds)
            
            # Apertura de Hoja
            sh = client.open(EXCEL_NAME).worksheet(SHEET_NAME)
            
            # Fila a insertar
            fila = [
                id_input, ubi_input, f_aut, f_tit, f_tra, f_ilu, f_edi, f_col, f_pob, 
                f_ano, f_pri, f_tem, f_cat, f_enc, f_isb, f_idi, f_obs, f_pag, f_med, f_pes, f_pre
            ]
            
            sh.append_row(fila)
            st.success("✅ ¡Datos guardados correctamente!")
            st.session_state.datos_extraidos = None
            st.balloons()
            
        except Exception as e:
            st.error(f"❌ Error al guardar: {e}")

if st.button("🧹 Limpiar todo"):
    st.session_state.datos_extraidos = None
    st.rerun()
