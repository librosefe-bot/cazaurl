import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import json
import requests
from bs4 import BeautifulSoup
import re
import base64

# --- FUNCIÓN DE LIMPIEZA DEFINITIVA PARA PEM ---
def limpiar_llave_pem(llave):
    if not llave: return ""
    
    # 1. Convertir a string por si acaso y quitar espacios laterales
    llave = str(llave).strip()
    
    # 2. Arreglar saltos de línea literales (\n) que a veces se pegan mal
    llave = llave.replace("\\n", "\n")
    
    # 3. Eliminar comillas que a veces envuelven la clave en los Secrets
    llave = llave.replace('"', '').replace("'", "")
    
    # 4. Localizar el inicio real del bloque PEM (evita el error de InvalidByte antes del guion)
    inicio_tag = "-----BEGIN PRIVATE KEY-----"
    fin_tag = "-----END PRIVATE KEY-----"
    
    if inicio_tag in llave:
        # Cortamos cualquier carácter extraño que haya antes del primer '-'
        llave = llave[llave.find(inicio_tag):]
        
    return llave

# --- 1. CONFIGURACIÓN DE SECRETOS ---
try:
    API_KEY = st.secrets["GEMINI_API_KEY"]
    g_secrets = st.secrets["GCP_SERVICE_ACCOUNT"]
    EXCEL_NAME = st.secrets["EXCEL_NAME"]
    SHEET_NAME = st.secrets.get("SHEET_NAME", "Hoja 1")
    
    # Aplicamos la limpieza a la clave privada antes de crear las credenciales
    private_key_limpia = limpiar_llave_pem(g_secrets["private_key"])
    
    creds_dict = {
        "type": g_secrets["type"],
        "project_id": g_secrets["project_id"],
        "private_key_id": g_secrets["private_key_id"],
        "private_key": private_key_limpia,
        "client_email": g_secrets["client_email"],
        "client_id": g_secrets["client_id"],
        "auth_uri": g_secrets["auth_uri"],
        "token_uri": g_secrets["token_uri"],
        "auth_provider_x509_cert_url": g_secrets["auth_provider_x509_cert_url"],
        "client_x509_cert_url": g_secrets["client_x509_cert_url"]
    }
except Exception as e:
    st.error(f"❌ Error en la carga de Secretos: {e}")
    st.stop()
