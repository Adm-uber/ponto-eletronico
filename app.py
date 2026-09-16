import streamlit as st
import pandas as pd
from datetime import datetime
import re

st.set_page_config(page_title="Gestão e Fechamento de Ponto", layout="wide")

st.title("⏱️ Sistema de Fechamento de Ponto")
st.markdown("Faça o upload do arquivo `.txt` do relógio de ponto e, opcionalmente, de uma planilha de cadastro para complementar os nomes ausentes.")

# --- Processamento do Arquivo AFD + Cadastro Opcional ---
def processar_arquivos(uploaded_txt, uploaded_excel=None):
    mapa_colaboradores = {}
    
    # 1. Mapear do Excel/CSV de cadastro (se fornecido)
    if uploaded_excel is not None:
        try:
            df_cad = pd.read_csv(uploaded_excel) if uploaded_excel.name.endswith('.csv') else pd.read_excel(uploaded_excel)
            col_nome, col_doc = None, None
            
            for c in df_cad.columns:
                c_str = str(c).strip().lower()
                if any(k in c_str for k in ["nome", "colaborador", "funcionario"]):
                    col_nome = c
                elif any(k in c_str for k in ["pis", "cpf", "doc", "id", "matricula", "cod"]):
                    col_doc = c
            
            if col_nome and col_doc:
                for _, row in df_cad.iterrows():
                    nome = str(row[col_nome]).strip()
                    doc_digits = re.sub(r'\D', '', str(row[col_doc]))
                    if nome and doc_digits:
                        mapa_colaboradores[doc_digits] = nome
                        mapa_colaboradores[doc_digits.lstrip('0')] = nome
                        mapa_colaboradores[doc_digits.zfill(10)] = nome
                        mapa_colaboradores[doc_digits.zfill(12)] = nome
        except Exception as e:
            st.sidebar.warning(f"Aviso ao ler planilha auxiliar: {e}")

    # 2. Mapear colaboradores do próprio TXT (Registro Tipo 5)
    linhas = uploaded_txt.getvalue().decode("utf-8", errors="ignore").splitlines()
    
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

    # 3. Mapear batidas de ponto (Registro Tipo 3)
    registros = []
    for linha in linhas:
        linha = linha.strip()
        if len(linha) >= 34 and linha[9] == '3':
            try:
                data_raw = linha[10:18]   # DDMMAAAA
                hora_raw = linha[18:22]   # HHMM
                doc_completo = linha[22:34] # 12 dígitos (TipoDoc + Documento)
                num_doc = linha[24:34]      # 10 dígitos do documento
                
                data_form = f"{data_raw[4:8]}-{data_raw[2:4]}-{data_raw[0:2]}"
                hora_form = f"{hora_raw[0:2]}:{hora_raw[2:4]}"
                
                # Busca nome no mapa ou exibe o ID
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

# --- Session State ---
if "df_ponto" not in st.session_state:
    st.session_state.df_ponto = pd.DataFrame(columns=["Colaborador", "PIS/CPF/ID", "Data", "Hora", "Origem", "Observação"])

# --- Sidebar ---
st.sidebar.header("📁 Importar Dados")
uploaded_txt = st.sidebar.file_uploader("1. Arquivo TXT do Relógio (.txt / .afd)", type=["txt", "csv", "afd"])
uploaded_excel = st.sidebar.file_uploader("2. Cadastro Auxiliar (Opcional .xlsx / .csv)", type=["xlsx", "xls", "csv"])

if uploaded_txt is not None and st.sidebar.button("Processar e Fechar Ponto"):
    df_res = processar_arquivos(uploaded_txt, uploaded_excel)
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
