import streamlit as st
import pandas as pd
from datetime import datetime

st.set_page_config(page_title="Gestão e Fechamento de Ponto", layout="wide")

st.title("⏱️ Sistema de Fechamento de Ponto")
st.markdown("Faça o upload do arquivo `.txt` do relógio de ponto para processar e ajustar as batidas por funcionário.")

def processar_txt(uploaded_file):
    linhas = uploaded_file.getvalue().decode("utf-8", errors="ignore").splitlines()
    registros = []
    
    for linha in linhas:
        linha = linha.strip()
        if not linha:
            continue
            
        # Padrão AFD do Relógio de Ponto (REP-C / REP-A / Portaria 671/1510)
        # O campo '3' na posição 9 (index 9) identifica marcação de ponto
        if len(linha) >= 34 and linha[9:10] == "3":
            try:
                data_str = linha[10:18] # DDMMAAAA
                hora_str = linha[18:22] # HHMM
                pis = linha[22:34].strip() # PIS
                
                # Validação básica de tamanho/numérico do PIS para evitar capturar fuso ou texto
                if not pis.isdigit():
                    # Tenta buscar CPF/PIS em posições alternativas se o arquivo for REP-C com fuso
                    # Procurar sequência de 11 ou 12 dígitos
                    import re
                    digitos = re.findall(r'\d{11,12}', linha[22:])
                    if digitos:
                        pis = digitos[0]
                
                dia = data_str[0:2]
                mes = data_str[2:4]
                ano = data_str[4:8]
                data_form = f"{ano}-{mes}-{dia}"
                hora_form = f"{hora_str[0:2]}:{hora_str[2:4]}"
                
                registros.append({
                    "Funcionário (PIS/CPF)": pis if pis else "Não Identificado",
                    "Data": data_form,
                    "Hora": hora_form,
                    "Origem": "Relógio (AFD)",
                    "Observação": ""
                })
            except Exception:
                continue
                
        # Padrão Delimitado (CSV/TXT com vírgula, ponto e vírgula ou tabulação)
        elif ";" in linha or "," in linha or "\t" in linha:
            separador = ";" if ";" in linha else ("," if "," in linha else "\t")
            partes = [p.strip() for p in linha.split(separador)]
            if len(partes) >= 3:
                registros.append({
                    "Funcionário (PIS/CPF)": partes[0],
                    "Data": partes[1],
                    "Hora": partes[2],
                    "Origem": "Arquivo TXT",
                    "Observação": partes[3] if len(partes) > 3 else ""
                })
                
    df = pd.DataFrame(registros)
    return df

# Estado Global
if "df_ponto" not in st.session_state:
    st.session_state.df_ponto = pd.DataFrame(columns=["Funcionário (PIS/CPF)", "Data", "Hora", "Origem", "Observação"])

sidebar = st.sidebar
sidebar.header("📁 Importar Dados")
uploaded_file = sidebar.file_uploader("Selecione o arquivo TXT do ponto", type=["txt", "csv", "afd"])

if uploaded_file is not None and st.sidebar.button("Carregar Arquivo"):
    df_carregado = processar_txt(uploaded_file)
    if not df_carregado.empty:
        st.session_state.df_ponto = pd.concat([st.session_state.df_ponto, df_carregado]).drop_duplicates().reset_index(drop=True)
        st.sidebar.success(f"{len(df_carregado)} registros carregados!")
    else:
        st.sidebar.error("Nenhum registro de ponto reconhecido no arquivo. Verifique a estrutura do TXT.")

if not st.session_state.df_ponto.empty:
    funcionarios = sorted(st.session_state.df_ponto["Funcionário (PIS/CPF)"].unique().tolist())
    func_selecionado = st.selectbox("Selecione o Funcionário:", funcionarios)
    
    df_func = st.session_state.df_ponto[st.session_state.df_ponto["Funcionário (PIS/CPF)"] == func_selecionado].copy()
    
    st.subheader(f"Batidas de Ponto - Funcionário: {func_selecionado}")
    
    tab1, tab2 = st.tabs(["📝 Editar Batidas", "➕ Adicionar Nova Batida"])
    
    with tab1:
        st.write("Altere ou ajuste os dados na tabela abaixo:")
        edited_df = st.data_editor(
            df_func,
            num_rows="dynamic",
            use_container_width=True,
            key="editor"
        )
        
        if st.button("Salvar Alterações da Tabela"):
            st.session_state.df_ponto = st.session_state.df_ponto[st.session_state.df_ponto["Funcionário (PIS/CPF)"] != func_selecionado]
            st.session_state.df_ponto = pd.concat([st.session_state.df_ponto, edited_df]).reset_index(drop=True)
            st.success("Alterações salvas com sucesso!")

    with tab2:
        st.write("Adicionar ajuste manual:")
        col1, col2, col3 = st.columns(3)
        nova_data = col1.date_input("Data", datetime.today())
        nova_hora = col2.time_input("Horário", datetime.now().time())
        justificativa = col3.text_input("Justificativa/Observação", "Ajuste Manual")
        
        if st.button("Adicionar Registro"):
            novo_registro = pd.DataFrame([{
                "Funcionário (PIS/CPF)": func_selecionado,
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
    
    csv_geral = st.session_state.df_ponto.sort_values(by=["Funcionário (PIS/CPF)", "Data", "Hora"]).to_csv(index=False).encode('utf-8')
    col_exp2.download_button(
        label="📥 Baixar Espelho Geral de Todos (CSV)",
        data=csv_geral,
        file_name="espelho_ponto_geral.csv",
        mime="text/csv"
    )
else:
    st.info("Aguardando upload do arquivo `.txt` do relógio de ponto.")
