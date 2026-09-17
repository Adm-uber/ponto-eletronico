import streamlit as st
import pandas as pd
from datetime import datetime
import re
import json
import os

st.set_page_config(page_title="Gestão e Fechamento de Ponto", layout="wide")

ARQUIVO_MEMORIA = "mapa_colaboradores.json"

# --- Funções para Mapeamento em Memória (JSON) ---
def carregar_memoria():
    if os.path.exists(ARQUIVO_MEMORIA):
        try:
            with open(ARQUIVO_MEMORIA, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def salvar_memoria(mapa):
    try:
        with open(ARQUIVO_MEMORIA, "w", encoding="utf-8") as f:
            json.dump(mapa, f, ensure_ascii=False, indent=4)
    except Exception as e:
        st.error(f"Erro ao salvar mapa em disco: {e}")

# --- Processamento do Arquivo AFD ---
def processar_arquivos(uploaded_txt, mapa_salvo):
    mapa_colaboradores = dict(mapa_salvo)
    
    linhas = uploaded_txt.getvalue().decode("utf-8", errors="ignore").splitlines()
    
    # 1. Mapear colaboradores do próprio TXT (Registro Tipo 5)
    for linha in linhas:
        linha = linha.strip()
        if len(linha) >= 37 and linha[9] == '5':
            try:
                num_doc = linha[25:35].strip()
                nome_raw = linha[35:87] if len(linha) >= 87 else linha[35:]
                match_nome = re.search(r'^[A-Za-zÀ-ÿ\s]+', nome_raw)
                nome = match_nome.group(0).strip() if match_nome else nome_raw.strip()
                
                if nome and num_doc:
                    mapa_colaboradores[num_doc] = nome
                    mapa_colaboradores[num_doc.lstrip('0')] = nome
            except Exception:
                continue

    # 2. Mapear batidas de ponto (Registro Tipo 3)
    registros = []
    for linha in linhas:
        linha = linha.strip()
        if len(linha) >= 34 and linha[9] == '3':
            try:
                data_raw = linha[10:18]   # DDMMAAAA
                hora_raw = linha[18:22]   # HHMM
                doc_completo = linha[22:34] # 12 dígitos
                num_doc = linha[24:34]      # 10 dígitos
                
                data_form = f"{data_raw[4:8]}-{data_raw[2:4]}-{data_raw[0:2]}"
                hora_form = f"{hora_raw[0:2]}:{hora_raw[2:4]}"
                
                # Busca nome no mapa ou mantém tag de não identificado
                nome = mapa_colaboradores.get(
                    num_doc, 
                    mapa_colaboradores.get(
                        num_doc.lstrip('0'), 
                        mapa_colaboradores.get(doc_completo, f"PIS/ID: {doc_completo}")
                    )
                )
                
                registros.append({
                    "Colaborador": nome,
                    "PIS/CPF/ID": doc_completo,
                    "Data": data_form,
                    "Hora": hora_form,
                    "Origem": "Relógio (AFD)",
                    "Observação": ""
                })
            except Exception:
                continue

    return pd.DataFrame(registros)

# --- Inicialização da Memória ---
if "mapa_memoria" not in st.session_state:
    st.session_state.mapa_memoria = carregar_memoria()

if "df_ponto" not in st.session_state:
    st.session_state.df_ponto = pd.DataFrame(columns=["Colaborador", "PIS/CPF/ID", "Data", "Hora", "Origem", "Observação"])

# --- Sidebar ---
st.sidebar.header("📁 Importar Dados")
uploaded_txt = st.sidebar.file_uploader("Arquivo TXT do Relógio (.txt / .afd)", type=["txt", "csv", "afd"])

if uploaded_txt is not None and st.sidebar.button("Processar e Fechar Ponto"):
    df_res = processar_arquivos(uploaded_txt, st.session_state.mapa_memoria)
    if not df_res.empty:
        st.session_state.df_ponto = df_res
        st.sidebar.success(f"Sucesso! {len(df_res)} registros processados.")
    else:
        st.sidebar.error("Não foi possível identificar registros de ponto válidos.")

# --- Bloco de Gerenciamento "De-Para" de Nomes ---
with st.sidebar.expander("👤 Cadastrar/Vincular Nome ao PIS"):
    st.write("Vincule um PIS/ID ao Nome do Colaborador para salvar permanentemente:")
    
    # Identifica IDs sem nome atribuído
    ids_desconhecidos = []
    if not st.session_state.df_ponto.empty:
        df_unkn = st.session_state.df_ponto[st.session_state.df_ponto["Colaborador"].str.startswith("PIS/ID:", na=False)]
        ids_desconhecidos = sorted(df_unkn["PIS/CPF/ID"].unique().tolist())

    if ids_desconhecidos:
        id_selecionado = st.selectbox("Selecione um PIS sem Nome:", ids_desconhecidos)
    else:
        id_selecionado = st.text_input("Digite o PIS/ID (12 dígitos):")

    novo_nome = st.text_input("Nome do Colaborador:")

    if st.button("Salvar Vinculação"):
        if id_selecionado and novo_nome:
            doc_limpo = re.sub(r'\D', '', id_selecionado)
            num_10 = doc_limpo[2:] if len(doc_limpo) == 12 else doc_limpo
            
            # Atualiza memória e salva no JSON
            st.session_state.mapa_memoria[doc_limpo] = novo_nome.strip()
            st.session_state.mapa_memoria[num_10] = novo_nome.strip()
            st.session_state.mapa_memoria[num_10.lstrip('0')] = novo_nome.strip()
            
            salvar_memoria(st.session_state.mapa_memoria)
            
            # Atualiza na tabela atual se já estiver aberta
            if not st.session_state.df_ponto.empty:
                st.session_state.df_ponto.loc[
                    st.session_state.df_ponto["PIS/CPF/ID"] == id_selecionado, "Colaborador"
                ] = novo_nome.strip()
            
            st.success(f"Vinculado: {id_selecionado} ➔ {novo_nome}")
            st.rerun()
        else:
            st.warning("Preencha o ID e o Nome.")

# --- Área Principal ---
st.title("⏱️ Fechamento de Ponto Eletrônico")

if not st.session_state.df_ponto.empty:
    colaboradores = sorted(st.session_state.df_ponto["Colaborador"].unique().tolist())
    colab_sel = st.selectbox("Selecione o Colaborador:", colaboradores)
    
    df_colab = st.session_state.df_ponto[st.session_state.df_ponto["Colaborador"] == colab_sel].copy()
    
    st.subheader(f"Batidas de Ponto - {colab_sel}")
    
    tab1, tab2 = st.tabs(["📝 Editar Batidas", "➕ Adicionar Nova Batida"])
    
    with tab1:
        edited_df = st.data_editor(
            df_colab,
            num_rows="dynamic",
            use_container_width=True,
            key="editor_ponto"
        )
        
        if st.button("Salvar Alterações"):
            st.session_state.df_ponto = st.session_state.df_ponto[st.session_state.df_ponto["Colaborador"] != colab_sel]
            st.session_state.df_ponto = pd.concat([st.session_state.df_ponto, edited_df]).reset_index(drop=True)
            st.success("Alterações salvas!")

    with tab2:
        c1, c2, c3 = st.columns(3)
        nova_data = c1.date_input("Data", datetime.today())
        nova_hora = c2.time_input("Horário", datetime.now().time())
        obs = c3.text_input("Observação / Atestado", "Ajuste Manual")
        
        if st.button("Adicionar Registro"):
            pis_val = df_colab["PIS/CPF/ID"].iloc[0] if not df_colab.empty else ""
            novo_reg = pd.DataFrame([{
                "Colaborador": colab_sel,
                "PIS/CPF/ID": pis_val,
                "Data": nova_data.strftime("%Y-%m-%d"),
                "Hora": nova_hora.strftime("%H:%M"),
                "Origem": "Manual",
                "Observação": obs
            }])
            st.session_state.df_ponto = pd.concat([st.session_state.df_ponto, novo_reg]).reset_index(drop=True)
            st.success("Registro adicionado com sucesso!")
            st.rerun()

    st.divider()
    st.subheader("📊 Exportar Relatório de Ponto")
    
    c_exp1, c_exp2 = st.columns(2)
    
    csv_individual = edited_df.sort_values(by=["Data", "Hora"]).to_csv(index=False).encode('utf-8')
    c_exp1.download_button(
        label=f"📥 Baixar Ponto de {colab_sel} (CSV)",
        data=csv_individual,
        file_name=f"ponto_{colab_sel}.csv",
        mime="text/csv"
    )
    
    csv_geral = st.session_state.df_ponto.sort_values(by=["Colaborador", "Data", "Hora"]).to_csv(index=False).encode('utf-8')
    c_exp2.download_button(
        label="📥 Baixar Espelho Geral de Todos (CSV)",
        data=csv_geral,
        file_name="espelho_ponto_geral.csv",
        mime="text/csv"
    )
else:
    st.info("Por favor, faça o upload do arquivo TXT no menu lateral para iniciar.")
