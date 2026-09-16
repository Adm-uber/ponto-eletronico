import streamlit as st
import pandas as pd
from datetime import datetime
import re

st.set_page_config(page_title="Gestão e Fechamento de Ponto", layout="wide")

st.title("⏱️ Sistema de Fechamento de Ponto")
st.markdown("Faça o upload do arquivo `.txt` do relógio de ponto e (opcionalmente) uma planilha de cadastro de funcionários.")

# --- Módulo de Processamento dos Arquivos ---
def processar_txt(uploaded_file, df_depara=None):
    linhas = uploaded_file.getvalue().decode("utf-8", errors="ignore").splitlines()
    registros = []
    
    # Criar dicionário de busca rápida para De-Para (CPF/PIS -> Nome)
    mapa_nomes = {}
    if df_depara is not None:
        try:
            # Limpa e padroniza colunas do De-Para
            col_doc = None
            col_nome = None
            
            for col in df_depara.columns:
                col_lower = str(col).lower()
                if any(k in col_lower for k in ["cpf", "pis", "matricula", "documento", "cód", "cod"]):
                    col_doc = col
                if any(k in col_lower for k in ["nome", "funcionario", "colaborador", "empregado"]):
                    col_nome = col
            
            if col_doc and col_nome:
                for _, row in df_depara.iterrows():
                    doc_val = re.sub(r'\D', '', str(row[col_doc]))
                    nome_val = str(row[col_nome]).strip()
                    if doc_val and nome_val:
                        mapa_nomes[doc_val] = nome_val
        except Exception as e:
            st.sidebar.warning("Não foi possível mapear a planilha de funcionários. Verifique o formato.")

    for linha in linhas:
        linha = linha.strip()
        if not linha:
            continue
            
        # Tratamento do Arquivo AFD / REP-C / REP-A
        # O Registro Tipo 3 é a marcação de ponto
        if len(linha) >= 30 and ("3" in linha[9:11] or linha.startswith("3")):
            try:
                # Busca todos os blocos numéricos da linha
                numeros = re.findall(r'\d+', linha)
                
                # Identifica PIS ou CPF na linha (sequências de 11 a 12 dígitos)
                pis_cpf = "Não Identificado"
                for num in numeros:
                    if len(num) in [11, 12]:
                        pis_cpf = num
                        break
                
                # Tenta extrair Data (DDMMAAAA) e Hora (HHMM ou HHMMSS)
                data_form = "Data Inválida"
                hora_form = "Hora Inválida"
                
                # Padrão AFD Padrão: posições 10-18 = Data (DDMMAAAA), 18-22 = Hora (HHMM)
                if len(linha) >= 22:
                    d_str = linha[10:18]
                    h_str = linha[18:22]
                    if d_str.isdigit() and len(d_str) == 8:
                        data_form = f"{d_str[4:8]}-{d_str[2:4]}-{d_str[0:2]}"
                    if h_str.isdigit() and len(h_str) == 4:
                        hora_form = f"{h_str[0:2]}:{h_str[2:4]}"
                
                # Identifica o nome pelo De-Para ou usa o PIS/CPF
                nome_exibicao = mapa_nomes.get(pis_cpf, pis_cpf)
                
                registros.append({
                    "Funcionário": nome_exibicao,
                    "PIS/CPF": pis_cpf,
                    "Data": data_form,
                    "Hora": hora_form,
                    "Origem": "Relógio (AFD)",
                    "Observação": ""
                })
            except Exception:
                continue
                
        # Padrão Texto Delimitado (CSV/TXT com ;, , ou TAB)
        elif ";" in linha or "," in linha or "\t" in linha:
            separador = ";" if ";" in linha else ("," if "," in linha else "\t")
            partes = [p.strip() for p in linha.split(separador)]
            if len(partes) >= 3:
                doc = re.sub(r'\D', '', partes[0])
                nome = mapa_nomes.get(doc, partes[0])
                registros.append({
                    "Funcionário": nome,
                    "PIS/CPF": doc,
                    "Data": partes[1],
                    "Hora": partes[2],
                    "Origem": "Arquivo TXT",
                    "Observação": partes[3] if len(partes) > 3 else ""
                })

    return pd.DataFrame(registros)

# --- Inicialização do Estado ---
if "df_ponto" not in st.session_state:
    st.session_state.df_ponto = pd.DataFrame(columns=["Funcionário", "PIS/CPF", "Data", "Hora", "Origem", "Observação"])

# --- Interface Sidebar ---
sidebar = st.sidebar
sidebar.header("📁 Importar Arquivos")

uploaded_txt = sidebar.file_uploader("1. Arquivo TXT do Relógio de Ponto", type=["txt", "csv", "afd"])
uploaded_excel = sidebar.file_uploader("2. Planilha de Cadastro (Opcional - Excel/CSV)", type=["xlsx", "xls", "csv"])

df_depara = None
if uploaded_excel is not None:
    try:
        if uploaded_excel.name.endswith('.csv'):
            df_depara = pd.read_csv(uploaded_excel)
        else:
            df_depara = pd.read_excel(uploaded_excel)
        sidebar.success("Planilha de cadastro carregada!")
    except Exception as e:
        sidebar.error("Erro ao ler planilha de cadastro.")

if uploaded_txt is not None and sidebar.button("Carregar Dados do Ponto"):
    df_carregado = processar_txt(uploaded_txt, df_depara)
    if not df_carregado.empty:
        st.session_state.df_ponto = df_carregado
        sidebar.success(f"{len(df_carregado)} registros carregados!")
    else:
        sidebar.error("Nenhum registro válido encontrado no arquivo TXT.")

# --- Painel de Edição ---
if not st.session_state.df_ponto.empty:
    funcionarios = sorted(st.session_state.df_ponto["Funcionário"].unique().tolist())
    func_selecionado = st.selectbox("Selecione o Funcionário:", funcionarios)
    
    df_func = st.session_state.df_ponto[st.session_state.df_ponto["Funcionário"] == func_selecionado].copy()
    
    st.subheader(f"Batidas de Ponto: {func_selecionado}")
    
    tab1, tab2 = st.tabs(["📝 Editar Batidas", "➕ Adicionar Nova Batida"])
    
    with tab1:
        edited_df = st.data_editor(
            df_func,
            num_rows="dynamic",
            use_container_width=True,
            key="editor"
        )
        
        if st.button("Salvar Alterações"):
            st.session_state.df_ponto = st.session_state.df_ponto[st.session_state.df_ponto["Funcionário"] != func_selecionado]
            st.session_state.df_ponto = pd.concat([st.session_state.df_ponto, edited_df]).reset_index(drop=True)
            st.success("Alterações salvas com sucesso!")

    with tab2:
        col1, col2, col3 = st.columns(3)
        nova_data = col1.date_input("Data", datetime.today())
        nova_hora = col2.time_input("Horário", datetime.now().time())
        justificativa = col3.text_input("Justificativa/Observação", "Ajuste Manual")
        
        if st.button("Adicionar Registro"):
            novo_registro = pd.DataFrame([{
                "Funcionário": func_selecionado,
                "PIS/CPF": df_func["PIS/CPF"].iloc[0] if not df_func.empty else "",
                "Data": nova_data.strftime("%Y-%m-%d"),
                "Hora": nova_hora.strftime("%H:%M"),
                "Origem": "Manual",
                "Observação": justificativa
            }])
            st.session_state.df_ponto = pd.concat([st.session_state.df_ponto, novo_registro]).reset_index(drop=True)
            st.success("Batida adicionada!")
            st.rerun()

    st.divider()
    st.subheader("📊 Exportar Fechamento")
    
    col_exp1, col_exp2 = st.columns(2)
    
    csv_func = edited_df.sort_values(by=["Data", "Hora"]).to_csv(index=False).encode('utf-8')
    col_exp1.download_button(
        label=f"📥 Baixar Ponto deste Funcionário (CSV)",
        data=csv_func,
        file_name=f"ponto_{func_selecionado}.csv",
        mime="text/csv"
    )
    
    csv_geral = st.session_state.df_ponto.sort_values(by=["Funcionário", "Data", "Hora"]).to_csv(index=False).encode('utf-8')
    col_exp2.download_button(
        label="📥 Baixar Espelho Geral de Todos (CSV)",
        data=csv_geral,
        file_name="espelho_ponto_geral.csv",
        mime="text/csv"
    )
else:
    st.info("Aguardando upload do arquivo `.txt` do relógio de ponto.")
