import streamlit as st
import pandas as pd
from datetime import datetime
import re
import base64

st.set_page_config(page_title="Gestão e Fechamento de Ponto", layout="wide")

st.title("⏱️ Sistema de Fechamento de Ponto")
st.markdown("Faça o upload do arquivo `.txt` do relógio de ponto para processar as batidas.")

# --- Função de Decodificação ---
def decodificar_id(valor):
    """
    Tenta decodificar identificadores codificados em Base64 ou limpa caracteres.
    """
    if not valor or not isinstance(valor, str):
        return ""
    
    valor_clean = valor.strip()
    
    # Tentativa de decodificação Base64 se parecer um hash
    if len(valor_clean) % 4 == 0 and re.match(r'^[A-Za-z0-9+/=]+$', valor_clean) and not valor_clean.isdigit():
        try:
            dec = base64.b64decode(valor_clean).decode('utf-8', errors='ignore').strip()
            if dec:
                return dec
        except Exception:
            pass

    return valor_clean

# --- Processamento ---
def processar_arquivo_txt(uploaded_txt):
    linhas = uploaded_txt.getvalue().decode("utf-8", errors="ignore").splitlines()
    registros = []

    for linha in linhas:
        linha = linha.strip()
        if not linha:
            continue
            
        # Padrão AFD (Registro Tipo 3 = Marcação de Ponto)
        if len(linha) >= 30 and (linha[9:10] == "3" or "3" in linha[9:11]):
            try:
                data_raw = linha[10:18]   # DDMMAAAA
                hora_raw = linha[18:22]   # HHMM
                doc_raw = linha[22:].strip() # PIS / CPF / Crachá / ID
                
                # Decodifica caso venha codificado em Base64 ou extrai dígitos
                doc_decodificado = decodificar_id(doc_raw)
                numeros_doc = re.findall(r'\d+', doc_decodificado)
                doc_limpo = numeros_doc[0] if numeros_doc else doc_decodificado
                
                # Trata Data e Hora
                data_form = f"{data_raw[4:8]}-{data_raw[2:4]}-{data_raw[0:2]}" if len(data_raw) == 8 and data_raw.isdigit() else "Data Invalida"
                hora_form = f"{hora_raw[0:2]}:{hora_raw[2:4]}" if len(hora_raw) == 4 and hora_raw.isdigit() else "Hora Invalida"
                
                # Identificador obtido diretamente do arquivo
                colaborador_id = f"Colaborador {doc_limpo}" if doc_limpo else "Desconhecido"

                registros.append({
                    "Colaborador": colaborador_id,
                    "PIS/CPF/ID": doc_limpo,
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
uploaded_txt = st.sidebar.file_uploader("Arquivo TXT do Relógio (.txt)", type=["txt", "csv", "afd"])

if uploaded_txt is not None and st.sidebar.button("Processar e Fechar Ponto"):
    df_res = processar_arquivo_txt(uploaded_txt)
    if not df_res.empty:
        st.session_state.df_ponto = df_res
        st.sidebar.success(f"Sucesso! {len(df_res)} registros processados.")
    else:
        st.sidebar.error("Não foi possível identificar registros de ponto válidos no arquivo TXT.")

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
