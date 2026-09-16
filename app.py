import streamlit as st
import pandas as pd
from datetime import datetime
import re

st.set_page_config(page_title="Gestão e Fechamento de Ponto", layout="wide")

st.title("⏱️ Sistema de Fechamento de Ponto")
st.markdown("Faça o upload do arquivo `.txt` do relógio de ponto (padrão AFD) para processar as batidas.")

# --- Processamento do Arquivo AFD ---
def processar_arquivo_afd(uploaded_txt):
    linhas = uploaded_txt.getvalue().decode("utf-8", errors="ignore").splitlines()
    
    mapa_colaboradores = {}
    registros = []

    # Passo 1: Mapear colaboradores cadastrados no relógio (Registro Tipo 5)
    for linha in linhas:
        linha = linha.strip()
        if len(linha) >= 37 and linha[9] == '5':
            try:
                tipo_doc = linha[23:25]
                num_doc = linha[25:35].strip()
                doc_completo = f"{tipo_doc}{num_doc}"
                
                # O nome do funcionário fica posicionado a partir da coluna 35
                nome_raw = linha[35:87] if len(linha) >= 87 else linha[35:]
                match_nome = re.search(r'^[A-Za-zÀ-ÿ\s]+', nome_raw)
                nome = match_nome.group(0).strip() if match_nome else nome_raw.strip()
                
                if nome:
                    mapa_colaboradores[doc_completo] = nome
                    mapa_colaboradores[num_doc] = nome
                    mapa_colaboradores[num_doc.lstrip('0')] = nome
            except Exception:
                continue

    # Passo 2: Mapear batidas de ponto (Registro Tipo 3)
    for linha in linhas:
        linha = linha.strip()
        if len(linha) >= 34 and linha[9] == '3':
            try:
                data_raw = linha[10:18]   # DDMMAAAA
                hora_raw = linha[18:22]   # HHMM
                doc_completo = linha[22:34] # Documento/PIS de 12 dígitos
                num_doc = linha[24:34]      # 10 dígitos do documento
                
                # Formatadores de Data e Hora
                data_form = f"{data_raw[4:8]}-{data_raw[2:4]}-{data_raw[0:2]}"
                hora_form = f"{hora_raw[0:2]}:{hora_raw[2:4]}"
                
                # Busca o nome correspondente no cadastro mapeado no Passo 1
                nome = mapa_colaboradores.get(
                    doc_completo, 
                    mapa_colaboradores.get(
                        num_doc, 
                        mapa_colaboradores.get(num_doc.lstrip('0'), f"PIS/ID: {doc_completo}")
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

# --- Session State ---
if "df_ponto" not in st.session_state:
    st.session_state.df_ponto = pd.DataFrame(columns=["Colaborador", "PIS/CPF/ID", "Data", "Hora", "Origem", "Observação"])

# --- Sidebar ---
st.sidebar.header("📁 Importar Dados")
uploaded_txt = st.sidebar.file_uploader("Arquivo TXT do Relógio (.txt / .afd)", type=["txt", "csv", "afd"])

if uploaded_txt is not None and st.sidebar.button("Processar e Fechar Ponto"):
    df_res = processar_arquivo_afd(uploaded_txt)
    if not df_res.empty:
        st.session_state.df_ponto = df_res
        st.sidebar.success(f"Sucesso! {len(df_res)} registros processados.")
    else:
        st.sidebar.error("Não foi possível identificar registros de ponto válidos no arquivo enviado.")

# --- Área Principal ---
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
