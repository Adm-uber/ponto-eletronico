import streamlit as st
import pandas as pd
from datetime import datetime
import re
import json
import os

st.set_page_config(page_title="Gestão e Fechamento de Ponto", layout="wide")

ARQUIVO_MEMORIA = "mapa_colaboradores.json"
CARGA_DIARIA_MINUTOS = 520  # 8h 40min = 520 minutos

# --- Funções Auxiliares de Horas ---
def hhmm_para_minutos(horastr):
    try:
        h, m = map(int, horastr.split(':'))
        return h * 60 + m
    except Exception:
        return 0

def minutos_para_hhmm(minutos):
    sinal = "-" if minutos < 0 else ""
    m = abs(int(minutos))
    horas = m // 60
    mins = m % 60
    return f"{sinal}{horas:02d}:{mins:02d}"

# --- Mapeamento em Memória (JSON) ---
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
    
    # Mapear colaboradores do Registro Tipo 5 (se houver)
    for linha in linhas:
        linha = linha.strip()
        if len(linha) >= 37 and linha[9] == '5':
            try:
                num_doc = linha[25:35].strip()
                nome_raw = linha[35:87] if len(linha) >= 87 else linha[35:]
                match_nome = re.search(r'^[A-Za-zÀ-ÿ\s]+', nome_raw)
                nome = match_nome.group(0).strip() if match_nome else nome_raw.strip()
                
                if nome and num_doc:
                    if num_doc not in mapa_colaboradores:
                        mapa_colaboradores[num_doc] = {"nome": nome, "jornada": "07:00 às 16:40"}
                    if num_doc.lstrip('0') not in mapa_colaboradores:
                        mapa_colaboradores[num_doc.lstrip('0')] = {"nome": nome, "jornada": "07:00 às 16:40"}
            except Exception:
                continue

    # Mapear batidas do Registro Tipo 3
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
                
                info = mapa_colaboradores.get(num_doc) or mapa_colaboradores.get(num_doc.lstrip('0')) or mapa_colaboradores.get(doc_completo)
                
                if isinstance(info, dict):
                    nome = info.get("nome", f"PIS/ID: {doc_completo}")
                    jornada = info.get("jornada", "07:00 às 16:40")
                elif isinstance(info, str):
                    nome = info
                    jornada = "07:00 às 16:40"
                else:
                    nome = f"PIS/ID: {doc_completo}"
                    jornada = "07:00 às 16:40"
                
                registros.append({
                    "Colaborador": nome,
                    "PIS/CPF/ID": doc_completo,
                    "Jornada": jornada,
                    "Data": data_form,
                    "Hora": hora_form,
                    "Origem": "Relógio (AFD)",
                    "Observação": ""
                })
            except Exception:
                continue

    return pd.DataFrame(registros)

# --- Cálculo de Horas Extras e Atrasos ---
def calcular_horas_diarias(df_colab):
    if df_colab.empty:
        return pd.DataFrame()
    
    resumo_dias = []
    
    for (data, colab), group in df_colab.groupby(["Data", "Colaborador"]):
        horas = sorted(group["Hora"].tolist())
        minutos_batidas = [hhmm_para_minutos(h) for h in horas]
        
        jornada = group["Jornada"].iloc[0] if "Jornada" in group.columns else "07:00 às 16:40"
        
        tempo_trabalhado_min = 0
        
        # Cálculo dependendo da quantidade de batidas
        if len(minutos_batidas) >= 4:
            # Entrada 1 -> Saída 1 + Entrada 2 -> Saída 2
            tempo_trabalhado_min = (minutos_batidas[1] - minutos_batidas[0]) + (minutos_batidas[3] - minutos_batidas[2])
        elif len(minutos_batidas) == 2:
            # Entrada 1 -> Saída 2 (deduz 1h de almoço = 60min)
            tempo_trabalhado_min = (minutos_batidas[1] - minutos_batidas[0]) - 60
            if tempo_trabalhado_min < 0:
                tempo_trabalhado_min = 0
        elif len(minutos_batidas) == 3:
            tempo_trabalhado_min = (minutos_batidas[1] - minutos_batidas[0]) + (minutos_batidas[2] - minutos_batidas[1])
        
        saldo_min = tempo_trabalhado_min - CARGA_DIARIA_MINUTOS
        horas_extras_min = max(0, saldo_min)
        atraso_min = max(0, -saldo_min) if tempo_trabalhado_min < CARGA_DIARIA_MINUTOS else 0
        
        resumo_dias.append({
            "Data": data,
            "Colaborador": colab,
            "Jornada": jornada,
            "Batidas": ", ".join(horas),
            "Qtd Batidas": len(horas),
            "Trabalhado": minutos_para_hhmm(tempo_trabalhado_min),
            "Meta": "08:40",
            "Hora Extra": minutos_para_hhmm(horas_extras_min),
            "Atraso/Falta": minutos_para_hhmm(atraso_min),
            "Saldo Minutos": saldo_min,
            "Saldo": minutos_para_hhmm(saldo_min)
        })
        
    return pd.DataFrame(resumo_dias)

# --- Inicialização da Memória ---
if "mapa_memoria" not in st.session_state:
    st.session_state.mapa_memoria = carregar_memoria()

if "df_ponto" not in st.session_state:
    st.session_state.df_ponto = pd.DataFrame(columns=["Colaborador", "PIS/CPF/ID", "Jornada", "Data", "Hora", "Origem", "Observação"])

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

# --- Bloco de Gerenciamento "De-Para" e Jornada ---
with st.sidebar.expander("👤 Cadastrar / Alterar Jornada"):
    st.write("Vincule o PIS ao Nome e selecione a Jornada de Trabalho:")
    
    ids_desconhecidos = []
    if not st.session_state.df_ponto.empty:
        df_unkn = st.session_state.df_ponto[st.session_state.df_ponto["Colaborador"].str.startswith("PIS/ID:", na=False)]
        ids_desconhecidos = sorted(df_unkn["PIS/CPF/ID"].unique().tolist())

    if ids_desconhecidos:
        id_selecionado = st.selectbox("Selecione um PIS sem Nome:", ids_desconhecidos)
    else:
        id_selecionado = st.text_input("Digite o PIS/ID (12 dígitos):")

    novo_nome = st.text_input("Nome do Colaborador:")
    jornada_sel = st.selectbox("Jornada de Trabalho:", ["07:00 às 16:40", "08:00 às 17:40"])

    if st.button("Salvar Vinculação"):
        if id_selecionado and novo_nome:
            doc_limpo = re.sub(r'\D', '', id_selecionado)
            num_10 = doc_limpo[2:] if len(doc_limpo) == 12 else doc_limpo
            
            dado = {"nome": novo_nome.strip(), "jornada": jornada_sel}
            
            st.session_state.mapa_memoria[doc_limpo] = dado
            st.session_state.mapa_memoria[num_10] = dado
            st.session_state.mapa_memoria[num_10.lstrip('0')] = dado
            
            salvar_memoria(st.session_state.mapa_memoria)
            
            if not st.session_state.df_ponto.empty:
                st.session_state.df_ponto.loc[
                    st.session_state.df_ponto["PIS/CPF/ID"] == id_selecionado, "Colaborador"
                ] = novo_nome.strip()
                st.session_state.df_ponto.loc[
                    st.session_state.df_ponto["PIS/CPF/ID"] == id_selecionado, "Jornada"
                ] = jornada_sel
            
            st.success(f"Salvo: {novo_nome} ({jornada_sel})")
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
    
    tab1, tab2, tab3 = st.tabs(["📝 Editar Batidas", "➕ Adicionar Nova Batida", "📊 Carga Horária & Extras"])
    
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
            jornada_val = df_colab["Jornada"].iloc[0] if not df_colab.empty else "07:00 às 16:40"
            novo_reg = pd.DataFrame([{
                "Colaborador": colab_sel,
                "PIS/CPF/ID": pis_val,
                "Jornada": jornada_val,
                "Data": nova_data.strftime("%Y-%m-%d"),
                "Hora": nova_hora.strftime("%H:%M"),
                "Origem": "Manual",
                "Observação": obs
            }])
            st.session_state.df_ponto = pd.concat([st.session_state.df_ponto, novo_reg]).reset_index(drop=True)
            st.success("Registro adicionado com sucesso!")
            st.rerun()

    with tab3:
        st.write("Calculado com base na meta diária de **08:40**.")
        df_calculado = calcular_horas_diarias(df_colab)
        
        if not df_calculado.empty:
            # Métricas em destaque
            total_saldo_min = df_calculado["Saldo Minutos"].sum()
            total_extras_min = df_calculado["Saldo Minutos"].apply(lambda x: max(0, x)).sum()
            total_atrasos_min = df_calculado["Saldo Minutos"].apply(lambda x: max(0, -x)).sum()
            
            m1, m2, m3 = st.columns(3)
            m1.metric("Total Horas Extras", minutos_para_hhmm(total_extras_min))
            m2.metric("Total Atrasos/Faltas", minutos_para_hhmm(total_atrasos_min))
            m3.metric("Saldo Acumulado", minutos_para_hhmm(total_saldo_min))
            
            st.dataframe(
                df_calculado[["Data", "Jornada", "Batidas", "Qtd Batidas", "Trabalhado", "Meta", "Hora Extra", "Atraso/Falta", "Saldo"]],
                use_container_width=True
            )
        else:
            st.info("Nenhuma batida encontrada para calcular.")

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
