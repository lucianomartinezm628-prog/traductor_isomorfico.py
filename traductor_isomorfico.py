import streamlit as st
import google.generativeai as genai
import json
import pandas as pd
import time
from io import BytesIO

# ==============================================================================
# 1. CONFIGURACIÓN INICIAL (SETUP)
# ==============================================================================
st.set_page_config(page_title="Sistema Isomórfico Full 2.0", page_icon="🏛️", layout="wide")

# Inicialización de Estado (Memoria de Sesión)
if "glossary" not in st.session_state:
    st.session_state.glossary = {} # P8: Glosario (Token -> Traducción)
if "glossary_meta" not in st.session_state:
    st.session_state.glossary_meta = {} # Metadatos (Categoría, Margen, Etiqueta)
if "user_rules" not in st.session_state:
    st.session_state.user_rules = [] # P0.3: Reglas de Usuario
if "stage" not in st.session_state:
    st.session_state.stage = "INPUT"
if "current_text" not in st.session_state:
    st.session_state.current_text = ""
if "pending_decisions" not in st.session_state:
    st.session_state.pending_decisions = []
if "translation_result" not in st.session_state:
    st.session_state.translation_result = ""

# ==============================================================================
# 2. DEFINICIÓN DE PROTOCOLOS (TEXTOS CONSTITUCIONALES P1-P10)
# ==============================================================================
# Estos textos se inyectarán en la IA para forzar el comportamiento (P2)

PROTOCOL_CONSTITUTION = """
ERES EL MOTOR DEL SISTEMA DE TRADUCCIÓN ISOMÓRFICA V2.0.
TU ÚNICO OBJETIVO ES OBEDECER LOS SIGUIENTES PROTOCOLOS SIN DESVIACIÓN:

PROTOCOLO 1 (DEFINICIONES):
- Input: Árabe Clásico. Output: Español.
- Literalidad Máxima e Isomorfismo Posicional.
- JERARQUÍA: ESTILO > IDENTIDAD > COHESIÓN.

PROTOCOLO 2 (CONSTITUCIÓN - INVIOLABLE):
- PROHIBIDO: Crear coherencia sin permiso, reordenar tokens, eliminar tokens, usar sinónimos para núcleos.
- OBLIGATORIO: Mapeo 1:1 en núcleos. Si es agramatical pero isomórfico, SE ACEPTA.
- La máquina NO lucha contra los protocolos.

PROTOCOLO 4 (NÚCLEOS):
- Invariables. Una traducción por token, siempre.
- JERARQUÍA ETIMOLÓGICA: Fuente > Latina > Griega > Árabe > Técnica.

PROTOCOLO 7 (REPARACIÓN):
- Solo inyecciones [...] permitidas para soporte mínimo (WHITELIST: hecho, cosa, algo, que).
- Nulidad {...} solo como último recurso.

PROTOCOLO 9 (FORMACIÓN):
- Si no hay equivalente: Transliteración (DIN 31635) o Neologismo (Raíz + Sufijo).
- Locuciones: ETYM(A)-ETYM(B)-... (con guiones).
"""

# ==============================================================================
# 3. FUNCIONES LÓGICAS (PYTHON - EL CUERPO)
# ==============================================================================

def configure_genai(api_key):
    if not api_key:
        return None
    genai.configure(api_key=api_key)
    # Usamos el modelo más compatible detectado anteriormente
    genai.GenerativeModel('gemini-1.5-flash')


def p10_a_cleaning(text):
    """P10.A: Limpieza y Normalización"""
    # Aquí se podrían añadir RegEx para limpiar números de página, etc.
    cleaned = text.strip()
    return cleaned

def p8_update_glossary(decisions):
    """P8.B: Registro en Glosario"""
    for token, data in decisions.items():
        st.session_state.glossary[token] = data['traduccion']
        st.session_state.glossary_meta[token] = {
            "categoria": data['categoria'],
            "origen": "USUARIO (P0)"
        }

def export_data():
    """P11.D: Exportación"""
    glossary_data = []
    for token, trad in st.session_state.glossary.items():
        meta = st.session_state.glossary_meta.get(token, {})
        glossary_data.append({
            "Token Fuente": token,
            "Traducción Target": trad,
            "Categoría": meta.get("categoria", "-"),
            "Origen": meta.get("origen", "-")
        })
    return pd.DataFrame(glossary_data)

# ==============================================================================
# 4. FUNCIONES DE IA (GEMINI - EL CEREBRO)
# ==============================================================================

def execute_p8_analysis(text, model, user_rules):
    """Ejecuta P8.A (Detección de dudas) usando la IA"""
    existing = list(st.session_state.glossary.keys())
    rules_text = "\n".join(user_rules)
    
    prompt = f"""
    {PROTOCOL_CONSTITUTION}
    
    CONFIGURACIÓN DE USUARIO (P0.3):
    {rules_text}
    
    TAREA (P8.A - ANÁLISIS LÉXICO):
    1. Analiza el siguiente texto árabe.
    2. Identifica NÚCLEOS nuevos, POSIBLES LOCUCIONES (P9.D) o TÉRMINOS AMBIGUOS (C6).
    3. IGNORA los términos que ya están en el GLOSARIO EXISTENTE: {existing}
    
    FORMATO DE SALIDA (JSON PURO, sin markdown):
    [
      {{
        "token_src": "palabra_arabe",
        "type": "C2_COLLISION" o "C3_IDIOM" o "C6_DUDOSO" o "NUEVO",
        "context": "breve explicación del contexto",
        "options": ["Opción A", "Opción B", "Opción C"],
        "recommendation": "Opción A"
      }}
    ]
    
    TEXTO FUENTE:
    {text}
    """
    try:
        response = model.generate_content(prompt)
        clean_json = response.text.replace("```json", "").replace("```", "").strip()
        return json.loads(clean_json)
    except Exception as e:
        st.error(f"Error P8.A: {e}")
        return []

def execute_p3_translation(text, model, user_rules):
    """Ejecuta P3-P7 (Traducción) usando la IA con Glosario Inyectado"""
    glossary_json = json.dumps(st.session_state.glossary, ensure_ascii=False)
    rules_text = "\n".join(user_rules)
    
    prompt = f"""
    {PROTOCOL_CONSTITUTION}
    
    CONFIGURACIÓN DE USUARIO (P0.3):
    {rules_text}
    
    GLOSARIO ACTIVO (P8 - INMUTABLE):
    Debes usar ESTAS traducciones exactas para estos tokens. PROHIBIDO SINÓNIMOS.
    {glossary_json}
    
    TAREA (P3 CORE + P7 REPARACIÓN):
    Traduce el texto aplicando isomorfismo y las reglas P10.B (Formato).
    
    TEXTO FUENTE:
    {text}
    """
    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"Error Crítico P3: {e}"

# ==============================================================================
# 5. INTERFAZ DE USUARIO (STREAMLIT - P0 & P11)
# ==============================================================================

# --- BARRA LATERAL (P11) ---
with st.sidebar:
    st.title("⚙️ P11: COMANDOS")
    
    # API Key
    api_key = st.text_input("Gemini API Key", type="password")
    model = configure_genai(api_key)
    
    st.divider()
    
    # Gestión de Glosario
    st.subheader("📚 Glosario (P8)")
    df = export_data()
    st.dataframe(df, hide_index=True, use_container_width=True)
    
    # Exportar (P11.D)
    if not df.empty:
        csv = df.to_csv(index=False).encode('utf-8')
        st.download_button("⬇️ Exportar CSV", csv, "glosario_isomorfico.csv", "text/csv")
        
        json_bytes = df.to_json(orient="records", force_ascii=False).encode('utf-8')
        st.download_button("⬇️ Exportar JSON", json_bytes, "glosario_isomorfico.json", "application/json")
    
    # Importar
    uploaded_file = st.file_uploader("⬆️ Importar Glosario (JSON/CSV)")
    if uploaded_file:
        try:
            if uploaded_file.name.endswith('.csv'):
                loaded_df = pd.read_csv(uploaded_file)
            else:
                loaded_df = pd.read_json(uploaded_file)
            
            # Cargar en sesión
            for _, row in loaded_df.iterrows():
                token = row.get("Token Fuente") or row.get("token_src")
                trad = row.get("Traducción Target") or row.get("token_tgt")
                if token and trad:
                    st.session_state.glossary[token] = trad
                    st.session_state.glossary_meta[token] = {"origen": "IMPORTADO"}
            st.success("Glosario importado.")
        except Exception as e:
            st.error("Error al importar.")

    st.divider()
    
    # Reglas de Usuario (P0.3)
    st.subheader("📝 Reglas (P0.3)")
    new_rule = st.text_input("Añadir Regla (ej: 'Siempre traduce X como Y')")
    if st.button("Añadir Regla"):
        if new_rule:
            st.session_state.user_rules.append(new_rule)
            st.success("Regla registrada.")
    
    if st.session_state.user_rules:
        st.write("Reglas Activas:")
        for i, rule in enumerate(st.session_state.user_rules):
            st.caption(f"{i+1}. {rule}")
        if st.button("Borrar todas las reglas"):
            st.session_state.user_rules = []
            st.rerun()

    st.divider()
    if st.button("⚠️ REINICIAR SISTEMA (P11.C)"):
        st.session_state.glossary = {}
        st.session_state.user_rules = []
        st.session_state.stage = "INPUT"
        st.rerun()

# --- ÁREA PRINCIPAL ---
st.title("🏛️ Sistema de Traducción Isomórfica Full 2.0")

if not api_key:
    st.warning("🔴 Por favor, ingresa tu API Key en la barra lateral para activar el sistema.")
else:
    # FASE 1: INPUT
    if st.session_state.stage == "INPUT":
        st.markdown("### 1. Input (P10.A)")
        text_in = st.text_area("Texto Fuente (Árabe):", height=150, value=st.session_state.current_text)
        
        if st.button("Analizar Léxico (P8.A) ➡️"):
            st.session_state.current_text = p10_a_cleaning(text_in)
            with st.spinner("Ejecutando P8.A..."):
                dudas = execute_p8_analysis(st.session_state.current_text, model, st.session_state.user_rules)
                if dudas:
                    st.session_state.pending_decisions = dudas
                    st.session_state.stage = "DECISION"
                else:
                    st.session_state.stage = "TRANSLATION"
            st.rerun()

    # FASE 2: DECISIÓN (P0)
    elif st.session_state.stage == "DECISION":
        st.markdown("### 2. Consultas y Decisiones (P0)")
        st.info("El sistema requiere tu autoridad para los siguientes tokens nuevos o conflictivos.")
        
        with st.form("form_decisiones"):
            results = {}
            for i, item in enumerate(st.session_state.pending_decisions):
                col_a, col_b = st.columns([1, 2])
                with col_a:
                    st.markdown(f"**Token:** `{item['token_src']}`")
                    st.caption(f"Tipo: {item.get('type', 'NUEVO')}")
                with col_b:
                    opts = item['options'] + ["MANUAL"]
                    sel = st.radio(f"Opción para '{item['token_src']}'", opts, key=f"d_{i}")
                    
                    val_final = sel
                    if sel == "MANUAL":
                        val_final = st.text_input(f"Traducción manual para {item['token_src']}", key=f"m_{i}")
                    
                    # Guardamos temporalmente
                    results[item['token_src']] = {
                        "traduccion": val_final,
                        "categoria": item.get('type', 'GENERAL')
                    }
                st.markdown("---")
            
            if st.form_submit_button("Sellar Glosario y Traducir (P3) ➡️"):
                p8_update_glossary(results)
                st.session_state.stage = "TRANSLATION"
                st.rerun()

    # FASE 3: TRADUCCIÓN (P3-P7)
    elif st.session_state.stage == "TRANSLATION":
        st.markdown("### 3. Resultado Isomórfico (P10.B)")
        
        if not st.session_state.translation_result:
            with st.spinner("Aplicando P3 (Core) + P7 (Reparación) + Glosario Inmutable..."):
                st.session_state.translation_result = execute_p3_translation(
                    st.session_state.current_text, 
                    model, 
                    st.session_state.user_rules
                )
        
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**Fuente (Árabe)**")
            st.code(st.session_state.current_text, language="text")
        with c2:
            st.markdown("**Target (Español Isomórfico)**")
            st.text_area("Salida", st.session_state.translation_result, height=300)
        
        st.success("Proceso completado bajo protocolo.")
        
        if st.button("⬅️ Traducir nuevo fragmento (Conservar Glosario)"):
            st.session_state.stage = "INPUT"
            st.session_state.current_text = ""
            st.session_state.translation_result = ""
            st.session_state.pending_decisions = []
            st.rerun()
