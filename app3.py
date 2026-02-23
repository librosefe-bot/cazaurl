import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import json
import requests
from bs4 import BeautifulSoup
import re
import base64

# --- 1. CONFIGURACIÓN DE SECRETOS ---
try:
    API_KEY = st.secrets["GEMINI_API_KEY"]
    # Cargamos el diccionario completo de la cuenta de servicio
    creds_dict = dict(st.secrets["GCP_SERVICE_ACCOUNT"])
    # Corregimos el formato de la clave privada (el error de Base64 suele venir de aquí)
    creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
    
    EXCEL_NAME = st.secrets["EXCEL_NAME"]
    # Si no defines SHEET_NAME en secretos, usará "Hoja 1" por defecto
    SHEET_NAME = st.secrets.get("SHEET_NAME", "Hoja 1")
except Exception as e:
    st.error(f"❌ Error en la configuración de Secrets: {e}")
    st.stop()

# Configuración de página
st.set_page_config(page_title="Catalogador IA Pro", layout="wide", page_icon="📚")

# Inicializar el estado de la sesión para mantener los datos tras recargar
if 'datos' not in st.session_state:
    st.session_state.datos = None

# --- 2. FUNCIONES DE APOYO ---

def limpiar_dato(dato):
    """Limpia los datos que vienen de la IA para que no den error en Sheets."""
    if isinstance(dato, list):
        return ", ".join(map(str, dato))
    if dato is None or str(dato).strip() in ["", "None", "---", "null"]:
        return "---"
    return str(dato)

def get_active_model():
    """Busca el modelo de Gemini disponible (pro o flash)."""
    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={API_KEY}"
    try:
        r = requests.get(url)
        models = r.json().get('models', [])
        for m in models:
            if 'generateContent' in m.get('supportedGenerationMethods', []):
                return m['name']
        return "models/gemini-1.5-flash" # Fallback
    except:
        return "models/gemini-1.5-flash"

def analizar_con_ia(texto_web, lista_imagenes):
    """Envía texto e imágenes a Gemini para extraer los 19 campos técnicos."""
    model_name = get_active_model()
    url = f"https://generativelanguage.googleapis.com/v1beta/{model_name}:generateContent?key={API_KEY}"
    
    # Preparar el contenido (Texto + hasta 4 imágenes para ahorrar cuota)
    prompt_texto = f"Analiza este libro para catalogación profesional. Texto extraído: {texto_web[:4000]}"
    partes = [{"text": prompt_texto}]
    
    for img_url in lista_imagenes[:4]:
        try:
            img_res = requests.get(img_url, timeout=10)
            if img_res.status_code == 200:
                partes.append({
                    "inline_data": {
                        "mime_type": "image/jpeg",
                        "data": base64.b64encode(img_res.content).decode('utf-8')
                    }
                })
        except:
            continue

    instrucciones = """
    Responde ÚNICAMENTE con un objeto JSON que tenga estas claves:
    Autor, Titulo, Traductor, Ilustrador, Editorial, Coleccion, Poblacion, Año, 
    Primera_Edicion, Tematica, Categorias, Encuadernacion, ISBN, Idioma, 
    Observaciones, Paginas, Medidas, Peso, Precio.

    REGLAS:
    - Categorías: Usa términos de la CDU (ej. 'Literatura española', 'Historia de América').
    - Observaciones: Basate en las fotos para ver manchas, lomos dañados o firmas.
    - Si no existe un dato, pon '---'.
    """
    partes.append({"text": instrucciones})
    
    payload = {
        "contents": [{"parts": partes}],
        "generationConfig": {"response_mime_type": "application/json"}
    }
    
    try:
        r = requests.post(url, json=payload, timeout=40)
        resultado = r.json()
        return resultado['candidates'][0]['content']['parts'][0]['text']
    except Exception as e:
        st.error(f"Error en la IA: {e}")
        return None

def extraer_web(url):
    """Scraping básico de Todocolección."""
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        r = requests.get(url, headers=headers, timeout=15)
        soup = BeautifulSoup(r.text, 'html.parser')
        
        # Extraer imágenes de calidad
        imagenes = []
        for img in soup.find_all('img', {'src': re.compile(r'tcimg|cloudfront')}):
            src = img.get('src')
            if src and ('galeria' in src or 'lote' in src) and src not in imagenes:
                imagenes.append(src)
        
        # Texto principal
        desc_div = soup.find('div', {'id': 'descriptionContents'})
        texto = desc_div.get_text(separator=' ', strip=True) if desc_div else soup.get_text()[:5000]
        
        return texto, imagenes
    except:
        return None, []

# --- 3. INTERFAZ DE USUARIO ---

st.title("📚 Catalogador Inteligente")
st.markdown("Extrae datos automáticamente de Todocolección y guárdalos en Google Sheets.")

with st.container(border=True):
    c1, c2, c3 = st.columns([3, 1, 1])
    with c1: url_input = st.text_input("🔗 URL del lote:", placeholder="https://www.todocoleccion.net/...")
    with c2: user_id = st.text_input("🆔 ID Interno:", placeholder="Lote-001")
    with c3: ubi_input = st.text_input("📍 Ubicación:", placeholder="Estante A1")

if st.button("🚀 Iniciar Análisis", type="primary", use_container_width=True):
    if not url_input or not user_id:
        st.warning("⚠️ Por favor, introduce la URL y el ID del libro.")
    else:
        with st.spinner("Analizando contenido..."):
            texto_web, fotos = extraer_web(url_input)
            if texto_web:
                json_raw = analizar_con_ia(texto_web, fotos)
                if json_raw:
                    st.session_state.datos = json.loads(json_raw)
                    st.success("✅ Análisis completado con éxito.")

# --- 4. FORMULARIO DE EDICIÓN Y GUARDADO ---

if st.session_state.datos:
    d = st.session_state.datos
    st.divider()
    st.subheader("📝 Revisión de Datos")
    
    # Organizar campos en 3 columnas para que sea cómodo de editar
    col_a, col_b, col_c = st.columns(3)
    
    with col_a:
        f_aut = st.text_input("Autor", value=limpiar_dato(d.get("Autor")))
        f_tit = st.text_input("Título", value=limpiar_dato(d.get("Titulo")))
        f_tra = st.text_input("Traductor", value=limpiar_dato(d.get("Traductor")))
        f_ilu = st.text_input("Ilustrador", value=limpiar_dato(d.get("Ilustrador")))
        f_edi = st.text_input("Editorial", value=limpiar_dato(d.get("Editorial")))
        f_col = st.text_input("Colección", value=limpiar_dato(d.get("Coleccion")))
        f_pob = st.text_input("Población", value=limpiar_dato(d.get("Poblacion")))

    with col_b:
        f_ano = st.text_input("Año", value=limpiar_dato(d.get("Año")))
        f_pri = st.text_input("Primera Edición", value=limpiar_dato(d.get("Primera_Edicion")))
        f_tem = st.text_input("Temática", value=limpiar_dato(d.get("Tematica")))
        f_cat = st.text_input("Categoría (CDU)", value=limpiar_dato(d.get("Categorias")))
        f_enc = st.text_input("Encuadernación", value=limpiar_dato(d.get("Encuadernacion")))
        f_isb = st.text_input("ISBN", value=limpiar_dato(d.get("ISBN")))
        f_idi = st.text_input("Idioma", value=limpiar_dato(d.get("Idioma")))

    with col_c:
        f_pag = st.text_input("Páginas", value=limpiar_dato(d.get("Paginas")))
        f_med = st.text_input("Medidas", value=limpiar_dato(d.get("Medidas")))
        f_pes = st.text_input("Peso", value=limpiar_dato(d.get("Peso")))
        f_pre = st.text_input("Precio", value=limpiar_dato(d.get("Precio")))
        f_obs = st.text_area("Observaciones (Estado)", value=limpiar_dato(d.get("Observaciones")), height=155)

    if st.button("💾 CONFIRMAR Y GUARDAR EN SHEETS", type="primary", use_container_width=True):
        try:
            with st.spinner("Conectando con Google Sheets..."):
                # Autenticación con la librería moderna
                scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
                credentials = Credentials.from_service_account_info(creds_dict, scopes=scope)
                client = gspread.authorize(credentials)
                
                # Apertura de la hoja
                sheet = client.open(EXCEL_NAME).worksheet(SHEET_NAME)
                
                # Mapeo de las 21 columnas exactas
                nueva_fila = [
                    user_id, ubi_input, f_aut, f_tit, f_tra, 
                    f_ilu, f_edi, f_col, f_pob, f_ano, 
                    f_pri, f_tem, f_cat, f_enc, f_isb, 
                    f_idi, f_obs, f_pag, f_med, f_pes, f_pre
                ]
                
                sheet.append_row(nueva_fila)
                
                st.balloons()
                st.toast("¡Libro guardado con éxito!", icon="✅")
                # Limpiar datos para el siguiente libro
                st.session_state.datos = None
                st.rerun()
                
        except Exception as e:
            st.error(f"❌ Error al guardar en Sheets: {e}")

if st.button("🧹 Limpiar todo"):
    st.session_state.datos = None
    st.rerun()
