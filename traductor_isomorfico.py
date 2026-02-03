import streamlit as st
import pandas as pd
from dataclasses import dataclass, field
from typing import List, Dict, Optional
from enum import Enum
import re
import json

# ==============================================================================
# PROTOCOLO 1 & 2: DEFINICIONES Y CONSTITUCIÓN
# ==============================================================================

class Categoria(Enum):
    NUCLEO = "NUCLEO"       # Sust, Adj, Adv, Verb
    PARTICULA = "PARTICULA" # Prep, Conj, Pron
    LOCUCION = "LOCUCION"   # Unidad compleja A-B-C
    PUNTUACION = "PUNTUACION"

class Status(Enum):
    PENDIENTE = "PENDIENTE"
    ASIGNADO = "ASIGNADO"
    BLOQUEADO = "BLOQUEADO" # Parte de una locución (ABSORBIDO)
    NULO = "NULO"           # {...} (Protocolo 7)

class Origen(Enum):
    FUENTE = "FUENTE"
    INYECCION = "INYECCION" # [...] P7
    POLIVALENCIA = "POLIVALENCIA" # P5

class Margen(Enum):
    IDIOM = 6      # Máximo
    COLLISION = 5
    NO_ROOT = 4
    TRANSLIT = 3
    ALT_1_1 = 2
    DIRECTO = 1    # Mínimo

class TipoConsulta(Enum):
    C1_CONFLICTO = "C1"
    C2_COLLISION = "C2"
    C3_LOCUCION = "C3"
    C4_SINONIMIA = "C4"
    C5_NO_REGISTRADO = "C5"

# ==============================================================================
# ESTRUCTURAS DE DATOS (P1.B, P8, P0)
# ==============================================================================

@dataclass
class Slot:
    """Representa un token en la Matriz Target (Mtx_T)"""
    id: str
    pos_index: int
    token_src: str
    token_tgt: str = ""
    categoria: Categoria = Categoria.NUCLEO
    status: Status = Status.PENDIENTE
    origen: Origen = Origen.FUENTE
    
    # Protocolo 7: Soporte Gramatical (Cirugía)
    inyecciones_previas: List[str] = field(default_factory=list)
    inyecciones_posteriores: List[str] = field(default_factory=list)

    def render(self, mode="BORRADOR"):
        """Renderizado P10.B"""
        # 1. Nulidad
        if self.status == Status.NULO:
            return f"{{{self.token_src}}}"
        
        # 2. Bloqueo (Locuciones)
        if self.status == Status.BLOQUEADO:
            # Si tiene texto y está bloqueado, es la cabecera de la locución.
            # Si no tiene texto y está bloqueado, está absorbido.
            if not self.token_tgt:
                return "" 

        # 3. Contenido
        nucleo = self.token_tgt if self.token_tgt else f"[{self.token_src}?]"
        if mode == "BORRADOR" and self.status == Status.PENDIENTE:
            nucleo = f"___{nucleo}___"

        # 4. Ensamblaje P7
        # Formato: [iny] [iny] NUCLEO [iny]
        prefix = "".join([f"[{x}] " for x in self.inyecciones_previas])
        suffix = "".join([f" [{x}]" for x in self.inyecciones_posteriores])
        
        return f"{prefix}{nucleo}{suffix}"

@dataclass
class EntradaGlosario:
    """Entrada única del Glosario P8"""
    token_src: str
    token_tgt: str
    categoria: Categoria
    status: Status
    margen: Margen
    bloqueado: bool = False # Para componentes de locución

@dataclass
class Consulta:
    """Objeto de Decisión P0"""
    id: str
    tipo: TipoConsulta
    contexto: str
    opciones: List[str]
    recomendacion: str
    resuelta: bool = False
    respuesta_usuario: str = ""

# ==============================================================================
# SISTEMA CENTRAL (LÓGICA P3, P8, P7)
# ==============================================================================

class SistemaTraduccion:
    def __init__(self):
        self.mtx_s: List[Slot] = [] 
        self.mtx_t: List[Slot] = [] 
        self.glosario: Dict[str, EntradaGlosario] = {}
        self.consultas_pendientes: List[Consulta] = []
        self.modo_salida = "BORRADOR"

    # --- P8.A & P10: PROCESAMIENTO INICIAL ---
    
    def _detectar_categoria(self, token: str) -> Categoria:
        if re.match(r"[^\w\s]", token): return Categoria.PUNTUACION
        if token.lower() in {"el", "la", "de", "en", "y", "que", "a"}: return Categoria.PARTICULA
        return Categoria.NUCLEO

    def registrar_token(self, token_src, categoria, margen=Margen.DIRECTO):
        if token_src not in self.glosario:
            self.glosario[token_src] = EntradaGlosario(
                token_src=token_src, token_tgt="", categoria=categoria,
                status=Status.PENDIENTE, margen=margen
            )

    def procesar_texto_input(self, texto_crudo: str):
        # P10.A Limpieza
        texto_limpio = texto_crudo.replace("\r", "")
        tokens_raw = re.findall(r"(\w+|[^\w\s])", texto_limpio)
        
        self.mtx_s = []
        self.mtx_t = []

        # P8.A Tokenización
        for i, token in enumerate(tokens_raw):
            cat = self._detectar_categoria(token)
            token_key = token.lower() if cat != Categoria.PUNTUACION else token
            
            self.registrar_token(token_key, cat)
            
            # Crear Slots
            self.mtx_s.append(Slot(id=f"S_{i}", pos_index=i, token_src=token, categoria=cat))
            self.mtx_t.append(Slot(id=f"T_{i}", pos_index=i, token_src=token))

    # --- P8.A AVANZADO: LOCUCIONES ---

    def crear_locucion(self, start_index: int, end_index: int, traduccion_locucion: str):
        if not (0 <= start_index < len(self.mtx_s)) or not (0 <= end_index < len(self.mtx_s)):
            return False, "Índices inválidos."
        if start_index > end_index:
            return False, "Inicio > Fin."

        # Key compuesta
        tokens_src = [self.mtx_s[i].token_src for i in range(start_index, end_index + 1)]
        key_locucion = " ".join(tokens_src).lower()

        # Registrar locución
        self.glosario[key_locucion] = EntradaGlosario(
            token_src=key_locucion, token_tgt=traduccion_locucion,
            categoria=Categoria.LOCUCION, status=Status.ASIGNADO, margen=Margen.IDIOM
        )

        # Aplicar Bloqueo en Matriz Target
        for i in range(start_index, end_index + 1):
            slot = self.mtx_t[i]
            slot.status = Status.BLOQUEADO
            if i == start_index:
                slot.token_tgt = traduccion_locucion
                slot.categoria = Categoria.LOCUCION
            else:
                slot.token_tgt = "" # Absorbido
        
        return True, f"Locución '{key_locucion}' creada."

    # --- P3: CORE DE TRADUCCIÓN ---

    def ejecutar_core_p3(self):
        for i, slot_s in enumerate(self.mtx_s):
            slot_t = self.mtx_t[i]
            
            # Respetar bloqueos de locuciones ya establecidas manualmente
            if slot_t.status == Status.BLOQUEADO and slot_t.categoria == Categoria.LOCUCION:
                continue
            if slot_t.status == Status.BLOQUEADO and not slot_t.token_tgt:
                continue

            token_key = slot_s.token_src.lower()
            entrada = self.glosario.get(token_key)
            if not entrada and slot_s.categoria == Categoria.PUNTUACION:
                 entrada = self.glosario.get(slot_s.token_src)

            if entrada and entrada.token_tgt:
                slot_t.token_tgt = entrada.token_tgt
                slot_t.status = Status.ASIGNADO
                slot_t.categoria = entrada.categoria
            else:
                if slot_t.status != Status.NULO: # Respetar anulaciones P7
                    slot_t.token_tgt = ""
                    slot_t.status = Status.PENDIENTE

    # --- P7: REPARACIÓN SINTÁCTICA ---

    def inyectar_token(self, index: int, texto: str, posicion="PRE"):
        if 0 <= index < len(self.mtx_t):
            slot = self.mtx_t[index]
            if posicion == "PRE": slot.inyecciones_previas.append(texto)
            else: slot.inyecciones_posteriores.append(texto)
            return True, "Inyección exitosa."
        return False, "Índice error."

    def alternar_nulidad(self, index: int):
        if 0 <= index < len(self.mtx_t):
            slot = self.mtx_t[index]
            if slot.status == Status.NULO:
                slot.status = Status.ASIGNADO if slot.token_tgt else Status.PENDIENTE
                return True, "Restaurado."
            else:
                slot.status = Status.NULO
                return True, "Anulado."
        return False, "Error."
        
    def limpiar_inyecciones(self, index: int):
        if 0 <= index < len(self.mtx_t):
            self.mtx_t[index].inyecciones_previas = []
            self.mtx_t[index].inyecciones_posteriores = []

    # --- P10: RENDERIZADO FINAL ---

    def renderizar_texto_final(self):
        buffer = []
        for slot in self.mtx_t:
            texto = slot.render(self.modo_salida)
            if not texto: continue

            # Lógica simple de puntuación (sin espacios antes de , . ; )
            is_punct = slot.categoria == Categoria.PUNTUACION or texto.strip() in [",", ".", ";", ":"]
            
            if is_punct and buffer and buffer[-1] == " ":
                buffer.pop()
            
            buffer.append(texto)
            if texto not in ["(", "¿", "¡"]:
                buffer.append(" ")
        return "".join(buffer).strip()

    # --- P0: CONSULTAS ---
    def resolver_consulta(self, cid: str):
        # Simplificado para demo: solo marca como resuelta
        self.consultas_pendientes = [c for c in self.consultas_pendientes if c.id != cid]

# ==============================================================================
# INTERFAZ DE USUARIO (STREAMLIT)
# ==============================================================================

def init_state():
    if 'sistema' not in st.session_state:
        st.session_state.sistema = SistemaTraduccion()
    if 'fase' not in st.session_state:
        st.session_state.fase = "INPUT"
    if 'input_text' not in st.session_state:
        st.session_state.input_text = ""

def main():
    st.set_page_config(layout="wide", page_title="SysTrad Isomórfica v2.0")
    init_state()
    sistema = st.session_state.sistema

    # --- SIDEBAR P11 ---
    with st.sidebar:
        st.title("Protocolos Activos")
        st.code("P2: Constitución\nP3: Isomorfismo\nP8: Glosario\nP7: Reparación")
        
        sistema.modo_salida = st.radio("Modo Visualización", ["BORRADOR", "FINAL"])
        
        st.divider()
        st.metric("Glosario Total", len(sistema.glosario))
        st.metric("Consultas", len(sistema.consultas_pendientes))
        
        if st.button("REINICIAR SISTEMA"):
            st.session_state.clear()
            st.rerun()

    st.title("Sistema de Traducción Isomórfica v2.0")

    # --- ÁREA PRINCIPAL ---
    col_izq, col_der = st.columns([1, 1])

    # Columna Izquierda: Input y Control
    with col_izq:
        st.subheader("1. Texto Fuente")
        txt_in = st.text_area("Ingrese texto aquí:", height=200, key="txt_in_widget")
        
        c1, c2 = st.columns(2)
        with c1:
            if st.button("PROCESAR (P10 -> P8)", use_container_width=True):
                st.session_state.input_text = txt_in
                sistema.procesar_texto_input(txt_in)
                st.session_state.fase = "TRABAJO"
                st.rerun()
        with c2:
            if st.button("Cargar Ejemplo", use_container_width=True):
                st.session_state.txt_in_widget = "Kitab al-ilm wal-ma'rifa." # Ejemplo simple
                st.rerun()

    # Columna Derecha: Trabajo
    with col_der:
        if st.session_state.fase == "INPUT":
            st.info("Esperando carga de texto...")
        
        else:
            tabs = st.tabs(["🏗️ Matriz & Cirugía (P7)", "📖 Glosario (P8)", "⚠️ Consultas (P0)"])

            # --- TAB 1: MATRIZ Y CIRUGÍA ---
            with tabs[0]:
                st.subheader("Matriz Isomórfica Target")
                
                # Visualización HTML de Tokens
                html_tokens = []
                for i, slot in enumerate(sistema.mtx_t):
                    bg = "#eee"
                    if slot.status == Status.ASIGNADO: bg = "#d4edda" # Verde
                    if slot.status == Status.BLOQUEADO: bg = "#f8d7da" # Rojo (Loc)
                    if slot.status == Status.NULO: bg = "#ccc"; text_dec = "line-through"
                    else: text_dec = "none"

                    val = slot.render(sistema.modo_salida)
                    tooltip = f"ID:{i} | SRC:{slot.token_src}"
                    
                    html_tokens.append(
                        f"<div style='display:inline-block; background:{bg}; padding:2px 5px; "
                        f"margin:2px; border:1px solid #ccc; border-radius:4px; "
                        f"font-family:monospace; text-decoration:{text_dec}' title='{tooltip}'>"
                        f"<small style='color:#666; font-size:0.6em'>{i}</small><br>"
                        f"<b>{val}</b></div>"
                    )
                st.markdown("".join(html_tokens), unsafe_allow_html=True)

                st.divider()
                
                # Herramientas
                c_tools1, c_tools2 = st.columns(2)
                
                with c_tools1:
                    with st.expander("🛠️ Crear Locución (P8.A)", expanded=False):
                        l_start = st.number_input("ID Inicio", 0, len(sistema.mtx_s), key="ls")
                        l_end = st.number_input("ID Fin", 0, len(sistema.mtx_s), key="le")
                        l_txt = st.text_input("Traducción (A-B-C)")
                        if st.button("Fusionar"):
                            ok, msg = sistema.crear_locucion(l_start, l_end, l_txt)
                            if ok: st.success(msg); st.rerun()
                            else: st.error(msg)

                with c_tools2:
                    with st.expander("🔧 Reparación Sintáctica (P7)", expanded=False):
                        r_id = st.number_input("Target ID", 0, len(sistema.mtx_s), key="rid")
                        r_txt = st.text_input("Inyección", key="rin")
                        cc1, cc2, cc3 = st.columns(3)
                        if cc1.button("PRE"):
                            sistema.inyectar_token(r_id, r_txt, "PRE"); st.rerun()
                        if cc2.button("POST"):
                            sistema.inyectar_token(r_id, r_txt, "POST"); st.rerun()
                        if cc3.button("ANULAR"):
                            sistema.alternar_nulidad(r_id); st.rerun()
                        if st.button("Limpiar ID"):
                             sistema.limpiar_inyecciones(r_id); st.rerun()

            # --- TAB 2: GLOSARIO ---
            with tabs[1]:
                st.subheader("Editor de Núcleos")
                
                # Preparar datos para editor
                data_glos = []
                # Solo mostrar núcleos y partículas individuales (no locuciones completas ni puntuación)
                for k, v in sistema.glosario.items():
                    if v.categoria not in [Categoria.PUNTUACION, Categoria.LOCUCION]:
                        data_glos.append({
                            "Token Fuente": k,
                            "Traducción": v.token_tgt,
                            "Categoría": v.categoria.value,
                            "Status": v.status.value
                        })
                
                if data_glos:
                    df = pd.DataFrame(data_glos)
                    edited = st.data_editor(df, key="main_editor", use_container_width=True, disabled=["Token Fuente"])
                    
                    if st.button("GUARDAR Y RE-PROCESAR"):
                        # Sincronizar cambios
                        for i, row in edited.iterrows():
                            key = row["Token Fuente"]
                            new_tgt = row["Traducción"]
                            if sistema.glosario[key].token_tgt != new_tgt:
                                sistema.glosario[key].token_tgt = new_tgt
                                sistema.glosario[key].status = Status.ASIGNADO
                        
                        sistema.ejecutar_core_p3()
                        st.success("Matriz regenerada.")
                        st.rerun()
                else:
                    st.info("Sin tokens pendientes.")

            # --- TAB 3: SALIDA ---
            with tabs[2]:
                st.warning("Panel de Consultas (Demo)")
                if sistema.consultas_pendientes:
                    for c in sistema.consultas_pendientes:
                        st.write(f"**{c.tipo.value}**: {c.contexto}")
                else:
                    st.success("Sin alertas activas.")

    # --- FOOTER: EXPORTACIÓN ---
    if st.session_state.fase == "TRABAJO":
        st.markdown("---")
        st.subheader("Salida Final")
        final_txt = sistema.renderizar_texto_final()
        st.code(final_txt)
        st.download_button("Descargar .TXT", final_txt, "traduccion.txt")

if __name__ == "__main__":
    main()
