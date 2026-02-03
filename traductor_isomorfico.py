import streamlit as st
import pandas as pd
import google.generativeai as genai
from dataclasses import dataclass, field
from typing import List, Dict
from enum import Enum
import re
import json
import time

# ==============================================================================
# CONFIGURACIÓN Y ENUMS
# ==============================================================================

class Categoria(Enum):
    NUCLEO = "NUCLEO"
    PARTICULA = "PARTICULA"
    LOCUCION = "LOCUCION"
    PUNTUACION = "PUNTUACION"

class Status(Enum):
    PENDIENTE = "PENDIENTE"
    ASIGNADO = "ASIGNADO"
    BLOQUEADO = "BLOQUEADO"
    NULO = "NULO"

class Origen(Enum):
    FUENTE = "FUENTE"
    IA = "IA_SUGERENCIA"

# ==============================================================================
# ESTRUCTURAS DE DATOS
# ==============================================================================

@dataclass
class Slot:
    id: str
    pos_index: int
    token_src: str
    token_tgt: str = ""
    categoria: Categoria = Categoria.NUCLEO
    status: Status = Status.PENDIENTE
    origen: Origen = Origen.FUENTE
    inyecciones_previas: List[str] = field(default_factory=list)
    inyecciones_posteriores: List[str] = field(default_factory=list)

    def render(self, mode="BORRADOR"):
        if self.status == Status.NULO: return f"{{{self.token_src}}}"
        if self.status == Status.BLOQUEADO:
             if not self.token_tgt: return "" 
        
        nucleo = self.token_tgt if self.token_tgt else f"[{self.token_src}?]"
        if mode == "BORRADOR" and self.status == Status.PENDIENTE:
            nucleo = f"__{nucleo}__"
            
        prefix = "".join([f"[{x}] " for x in self.inyecciones_previas])
        suffix = "".join([f" [{x}]" for x in self.inyecciones_posteriores])
        return f"{prefix}{nucleo}{suffix}"

@dataclass
class EntradaGlosario:
    token_src: str
    token_tgt: str
    categoria: Categoria
    status: Status
    etimologia_ia: str = "" 

# ==============================================================================
# SISTEMA CENTRAL (CON CEREBRO IA)
# ==============================================================================

class SistemaTraduccion:
    def __init__(self):
        self.mtx_s: List[Slot] = [] 
        self.mtx_t: List[Slot] = [] 
        self.glosario: Dict[str, EntradaGlosario] = {}
        self.modo_salida = "BORRADOR"
        self.api_key = ""

    def _detectar_categoria(self, token: str) -> Categoria:
        if re.match(r"[^\w\s]", token): return Categoria.PUNTUACION
        particulas = {"el", "la", "de", "en", "y", "que", "a", "al", "wa", "fi", "min", "bi"}
        if token.lower() in particulas: return Categoria.PARTICULA
        return Categoria.NUCLEO

    def registrar_token(self, token_src, categoria):
        if token_src not in self.glosario:
            self.glosario[token_src] = EntradaGlosario(
                token_src=token_src, token_tgt="", categoria=categoria, status=Status.PENDIENTE
            )

    def procesar_texto_input(self, texto_crudo: str):
        texto_limpio = texto_crudo.replace("\r", "")
        tokens_raw = re.findall(r"(\w+|[^\w\s])", texto_limpio)
        self.mtx_s = []; self.mtx_t = []

        for i, token in enumerate(tokens_raw):
            cat = self._detectar_categoria(token)
            token_key = token.lower() if cat != Categoria.PUNTUACION else token
            self.registrar_token(token_key, cat)
            self.mtx_s.append(Slot(id=f"S_{i}", pos_index=i, token_src=token, categoria=cat))
            self.mtx_t.append(Slot(id=f"T_{i}", pos_index=i, token_src=token))

    def consultar_ia_glosario(self):
        if not self.api_key:
            return False, "Falta API Key"

        pendientes = [k for k, v in self.glosario.items() 
                      if v.status == Status.PENDIENTE and v.categoria == Categoria.NUCLEO]
        
        if not pendientes:
            return False, "No hay núcleos pendientes."

        try:
            genai.configure(api_key=self.api_key)
            # SE ACTUALIZA A GEMINI-1.5-FLASH PARA EVITAR ERROR 404
            model = genai.GenerativeModel('gemini-1.5-flash')
            
            prompt = f"""
            Actúa como un traductor etimológico estricto (Protocolo Isomórfico).
            Tengo una lista de tokens fuente. Necesito su raíz/traducción literal en español.
            
            REGLAS:
            1. Prioriza la etimología sobre el uso técnico moderno.
            2. Devuelve SOLO un objeto JSON válido.
            3. Formato: {{"token_fuente": "traduccion_literal"}}
            
            TOKENS A TRADUCIR:
            {json.dumps(pendientes)}
            """
            
            with st.spinner(f"Consultando raíces etimológicas para {len(pendientes)} tokens..."):
                response = model.generate_content(prompt)
                texto_resp = response.text.replace("```json", "").replace("```", "")
                diccionario_ia = json.loads(texto_resp)
                
                count = 0
                for k, v in diccionario_ia.items():
                    if k in self.glosario:
                        self.glosario[k].token_tgt = v
                        self.glosario[k].status = Status.ASIGNADO
                        self.glosario[k].etimologia_ia = "Sugerido por Gemini"
                        count += 1
                
                return True, f"IA completó {count} definiciones."

        except Exception as e:
            return False, f"Error IA: {str(e)}"

    def ejecutar_core_p3(self):
        for i, slot_s in enumerate(self.mtx_s):
            slot_t = self.mtx_t[i]
            if slot_t.status == Status.BLOQUEADO and (slot_t.categoria == Categoria.LOCUCION or not slot_t.token_tgt):
                continue
            
            token_key = slot_s.token_src.lower()
            entrada = self.glosario.get(token_key)
            if not entrada and slot_s.categoria == Categoria.PUNTUACION:
                 entrada = self.glosario.get(slot_s.token_src)

            if entrada and entrada.token_tgt:
                slot_t.token_tgt = entrada.token_tgt
                slot_t.status = Status.ASIGNADO
            else:
                if slot_t.status != Status.NULO:
                    slot_t.token_tgt = ""
                    slot_t.status = Status.PENDIENTE

    def crear_locucion(self, start, end, texto):
        if not (0 <= start <= end < len(self.mtx_s)): return False, "Rango inválido"
        tokens = [self.mtx_s[i].token_src for i in range(start, end+1)]
        key = " ".join(tokens).lower()
        self.glosario[key] = EntradaGlosario(key, texto, Categoria.LOCUCION, Status.ASIGNADO)
        for i in range(start, end+1):
            self.mtx_t[i].status = Status.BLOQUEADO
            self.mtx_t[i].token_tgt = texto if i == start else ""
            if i == start: self.mtx_t[i].categoria = Categoria.LOCUCION
        return True, f"Locución '{key}' creada."

    def renderizar_texto_final(self):
        buffer = []
        for slot in self.mtx_t:
            txt = slot.render(self.modo_salida)
            if not txt: continue
            is_punct = slot.categoria == Categoria.PUNTUACION or txt in [",", ".", ";"]
            if is_punct and buffer and buffer[-1] == " ": buffer.pop()
            buffer.append(txt)
            if txt not in ["("]: buffer.append(" ")
        return "".join(buffer).strip()

# ==============================================================================
# UI
# ==============================================================================
def main():
    st.set_page_config(layout="wide", page_title="SysTrad AI 2.0")
    if 'sistema' not in st.session_state: st.session_state.sistema = SistemaTraduccion()
    sys = st.session_state.sistema

    with st.sidebar:
        st.title("⚙️ Configuración")
        st.markdown("### 🧠 Cerebro IA (Gemini)")
        api_key = st.text_input("Google API Key", type="password")
        if api_key: sys.api_key = api_key
        
        sys.modo_salida = st.radio("Modo Visual", ["BORRADOR", "FINAL"])
        if st.button("REINICIAR"): st.session_state.clear(); st.rerun()

    st.title("Traductor Isomórfico + IA 🤖")

    c1, c2 = st.columns([1, 1])
    with c1:
        txt = st.text_area("Texto Fuente", height=150)
        if st.button("PROCESAR TEXTO"):
            sys.procesar_texto_input(txt)
            st.rerun()

    with c2:
        tabs = st.tabs(["Matriz", "Glosario (IA)", "Salida"])
        
        with tabs[0]:
            html = []
            for i, s in enumerate(sys.mtx_t):
                color = "#d4edda" if s.status == Status.ASIGNADO else "#eee"
                if s.status == Status.NULO: color = "#ccc"
                val = s.render(sys.modo_salida)
                html.append(f"<div style='background:{color};display:inline-block;padding:2px;margin:2px;border-radius:4px;font-family:monospace' title='ID {i}'>{val}<sub style='color:#555'>{i}</sub></div>")
            st.markdown("".join(html), unsafe_allow_html=True)
            
            st.divider()
            with st.expander("Herramientas P7/P8"):
                cc1, cc2, cc3 = st.columns(3)
                ls = cc1.number_input("Loc Inicio", 0, value=0)
                le = cc2.number_input("Loc Fin", 0, value=0)
                lt = cc3.text_input("Locución Txt")
                if st.button("Crear Locución"): sys.crear_locucion(ls, le, lt); st.rerun()

        with tabs[1]:
            st.info("Paso 1: Ingresa tu API Key en la barra lateral.")
            if st.button("🤖 AUTO-COMPLETAR GLOSARIO (GEMINI)", type="primary"):
                ok, msg = sys.consultar_ia_glosario()
                if ok: 
                    sys.ejecutar_core_p3()
                    st.success(msg)
                    st.rerun()
                else: st.error(msg)
            
            data = [{"Token": k, "Traducción": v.token_tgt, "Status": v.status.value} 
                    for k,v in sys.glosario.items() if v.categoria == Categoria.NUCLEO]
            if data:
                edited = st.data_editor(pd.DataFrame(data), key="editor", disabled=["Token"], use_container_width=True)
                if st.button("GUARDAR MANUAL"):
                    for i, row in edited.iterrows():
                        sys.glosario[row["Token"]].token_tgt = row["Traducción"]
                        sys.glosario[row["Token"]].status = Status.ASIGNADO
                    sys.ejecutar_core_p3()
                    st.rerun()

        with tabs[2]:
            st.code(sys.renderizar_texto_final())

if __name__ == "__main__":
    main()
