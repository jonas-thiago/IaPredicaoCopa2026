import os
import sys
import altair as alt
import pandas as pd
import streamlit as st

# Configuração da página Streamlit (deve ser a primeira chamada Streamlit)
st.set_page_config(
    page_title="IAPredict — Copa 2026",
    page_icon="⚽",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Adicionar o diretório src/ no path para importações flat
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

# Ponte de segredo: se estiver rodando no Streamlit Cloud, st.secrets estará presente
try:
    if "DATABASE_URL" in st.secrets and "DATABASE_URL" not in os.environ:
        os.environ["DATABASE_URL"] = st.secrets["DATABASE_URL"]
except Exception:
    pass

from db import get_engine
from previsao import prever_jogo
from monte_carlo import NOMES_RODADA, preparar, simular_torneio_detalhado, slots_terceiros
from bandeiras import com_bandeira, obter_bandeira

# Cache resource para carregamento dos modelos e dados estáticos da Copa
@st.cache_resource
def carregar_dados_preparados():
    return preparar()

# Cache data para carregar as probabilidades pré-computadas do banco de dados
@st.cache_data
def carregar_probabilidades_banco():
    engine = get_engine()
    df = pd.read_sql("SELECT selecao, prob_grupo, prob_oitavas, prob_quartas, prob_semi, prob_final, prob_campea FROM gold_probabilidades_copa ORDER BY prob_campea DESC", engine)
    return df

# Inicialização do app e carregamento dos recursos
preparado = carregar_dados_preparados()
df_grupos = preparado["df_grupos"]
selecoes_todas = sorted(df_grupos["nation"].unique())

# Título principal do dashboard
st.title("🏆 IAPredict — Previsão da Copa do Mundo 2026")
st.markdown("---")

# Barra Lateral (Menu de Navegação)
st.sidebar.title("Navegação")
pagina = st.sidebar.radio(
    "Ir para:",
    ["Probabilidades pré-computadas", "Simulação ao vivo", "Explorador de partidas"]
)

st.sidebar.markdown("---")
st.sidebar.info(
    "**IAPredict** é um modelo matemático baseado em distribuição Poisson e ELO dinâmico que estima a probabilidade de desempenho de cada seleção na Copa de 2026. Feito com ❤️ e dados históricos reais."
)

# --- PÁGINA 1: Probabilidades Pré-computadas ---
if pagina == "Probabilidades pré-computadas":
    st.header("📊 Probabilidades do Torneio (Visão Geral)")
    st.markdown(
        "Essas probabilidades são derivadas de **1.000 simulações de Monte Carlo** completas da Copa 2026. Abaixo estão as 12 seleções favoritas ao título."
    )
    
    try:
        df_prob = carregar_probabilidades_banco()
    except Exception as e:
        st.error(f"Erro ao carregar dados do banco: {e}")
        st.stop()
        
    df_top12 = df_prob.head(12).copy()
    
    # Preparar DataFrame para o gráfico Altair
    chart_df = df_top12.copy()
    chart_df["Seleção"] = chart_df["selecao"].apply(com_bandeira)
    chart_df["Chance de Título (%)"] = chart_df["prob_campea"] * 100
    
    # Gráfico Altair ordenado de forma decrescente por probabilidade de título
    chart = alt.Chart(chart_df).mark_bar(color="#E74C3C").encode(
        x=alt.X("Chance de Título (%):Q", title="Probabilidade de ser Campeã (%)"),
        y=alt.Y("Seleção:N", sort="-x", title="Seleção"),
        tooltip=["Seleção", alt.Tooltip("Chance de Título (%)", format=".2f")]
    ).properties(
        height=400,
        title="Probabilidade de Título (%) das Top 12 Favoritas"
    )
    
    st.altair_chart(chart, width="stretch")
    
    # Tabela detalhada por fase
    st.subheader("📋 Chances de Avanço por Seleção (Top 12)")
    
    table_df = df_top12.copy()
    table_df["Seleção"] = table_df["selecao"].apply(com_bandeira)
    table_df = table_df.rename(columns={
        "prob_grupo": "Avançar do Grupo (R32)",
        "prob_oitavas": "Oitavas de Final (R16)",
        "prob_quartas": "Quartas de Final (QF)",
        "prob_semi": "Semifinal (SF)",
        "prob_final": "Chegar à Final",
        "prob_campea": "Campeã 🏆"
    })
    
    cols_pct = [
        "Avançar do Grupo (R32)", "Oitavas de Final (R16)", 
        "Quartas de Final (QF)", "Semifinal (SF)", "Chegar à Final", "Campeã 🏆"
    ]
    for col in cols_pct:
        table_df[col] = (table_df[col] * 100).map('{:.1f}%'.format)
        
    st.dataframe(
        table_df[["Seleção"] + cols_pct],
        width="stretch",
        hide_index=True
    )

# --- PÁGINA 2: Simulação Ao Vivo ---
elif pagina == "Simulação ao vivo":
    st.header("⚡ Simulação em Tempo Real do Torneio")
    st.markdown(
        "Abaixo, rodamos **uma única simulação aleatória** do torneio completo (fase de grupos e todas as etapas de mata-mata até a final). Cada clique no botão roda uma nova simulação."
    )
    
    # Botão para re-simular
    if st.button("🔄 Rodar Nova Simulação"):
        # Limpar cache da simulação para forçar re-execução
        st.cache_resource.clear()
        
    # Executar simulação de uma rodada
    resultado = simular_torneio_detalhado(preparado)
    podio = resultado["podio"]
    mata_mata = resultado["mata_mata"]
    grupos_classificacao = resultado["grupos_classificacao"]
    
    # Renderizar Pódio / Campeão
    st.subheader("🥇 O Grande Campeão!")
    
    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown(
            f"<div style='text-align: center; border: 2px solid #F1C40F; border-radius: 10px; padding: 15px; background: linear-gradient(135deg, #FFFDEB 0%, #FEF5C3 100%); transform: scale(1.03); color: #1A252F;'>"
            f"<h4 style='color: #7D6608; font-size: 15px; margin: 0 0 5px 0; font-weight: bold;'>🏆 CAMPEÃO 🏆</h4>"
            f"<span style='font-size: 36px; display: inline-block; margin: 5px 0;'>{obter_bandeira(podio['campeao'])}</span>"
            f"<h3 style='color: #1A252F; font-size: 18px; margin: 5px 0 0 0; font-weight: bold;'>{podio['campeao']}</h3>"
            f"</div>",
            unsafe_allow_html=True
        )
    with col2:
        st.markdown(
            f"<div style='text-align: center; border: 2px solid #BDC3C7; border-radius: 10px; padding: 15px; background: linear-gradient(135deg, #F8F9F9 0%, #EBEDEF 100%); color: #2C3E50;'>"
            f"<h4 style='color: #5D6D7E; font-size: 14px; margin: 0 0 5px 0; font-weight: bold;'>🥈 Vice-Campeão</h4>"
            f"<span style='font-size: 28px; display: inline-block; margin: 5px 0;'>{obter_bandeira(podio['vice'])}</span>"
            f"<h3 style='color: #2C3E50; font-size: 16px; margin: 5px 0 0 0; font-weight: bold;'>{podio['vice']}</h3>"
            f"</div>",
            unsafe_allow_html=True
        )
    with col3:
        st.markdown(
            f"<div style='text-align: center; border: 2px solid #D35400; border-radius: 10px; padding: 15px; background: linear-gradient(135deg, #FBEEE6 0%, #F5CBA7 100%); color: #2C3E50;'>"
            f"<h4 style='color: #A04000; font-size: 14px; margin: 0 0 5px 0; font-weight: bold;'>🥉 3º Colocado</h4>"
            f"<span style='font-size: 28px; display: inline-block; margin: 5px 0;'>{obter_bandeira(podio['terceiro'])}</span>"
            f"<h3 style='color: #2C3E50; font-size: 16px; margin: 5px 0 0 0; font-weight: bold;'>{podio['terceiro']}</h3>"
            f"</div>",
            unsafe_allow_html=True
        )
        
    st.markdown("---")
    
    # Layout de chaves do mata-mata
    st.subheader("🎟️ Chaveamento e Mata-Mata")
    
    rodadas = ["R32", "R16", "QF", "SF", "3rd", "Final"]
    
    for r in rodadas:
        nome_exibicao = NOMES_RODADA[r]
        st.markdown(f"### 📍 {nome_exibicao}")
        
        jogos_rodada = [m for m in mata_mata if m["round"] == r]
        
        # Agrupar jogos em colunas para economizar espaço vertical
        cols = st.columns(4 if len(jogos_rodada) >= 4 else len(jogos_rodada))
        
        for idx, jogo in enumerate(jogos_rodada):
            col_target = cols[idx % len(cols)]
            with col_target:
                t_casa = com_bandeira(jogo["home_team"])
                t_visit = com_bandeira(jogo["away_team"])
                g_c = jogo["gols_casa"]
                g_v = jogo["gols_visitante"]
                venc = jogo["vencedor"]
                pen_v = jogo["penaltis_vencedor"]
                
                # Destacar vencedor usando HTML <b> (evitando conflito com asteriscos do markdown)
                styled_casa = f"<b>{t_casa}</b>" if venc == jogo["home_team"] else t_casa
                styled_visit = f"<b>{t_visit}</b>" if venc == jogo["away_team"] else t_visit
                
                pen_text = f" <span style='font-size:11px; color:gray;'>(Pen: {obter_bandeira(pen_v)} {pen_v})</span>" if pen_v else ""
                
                st.markdown(
                    f"<div style='border: 1px solid #EAEDED; border-radius: 5px; padding: 8px; margin-bottom: 10px; background-color: white; color: #1A252F; text-align: center; font-size: 13px;'>"
                    f"{styled_casa} &nbsp;<b>{g_c}x{g_v}</b>&nbsp; {styled_visit}{pen_text}"
                    f"</div>",
                    unsafe_allow_html=True
                )
                
    st.markdown("---")
    
    # Classificação da Fase de Grupos
    st.subheader("⚽ Classificação da Fase de Grupos")
    
    grupos_letras = sorted(df_grupos["group"].unique())
    tab_names = [f"Grupo {g}" for g in grupos_letras]
    tabs = st.tabs(tab_names)
    
    for idx, g in enumerate(grupos_letras):
        with tabs[idx]:
            df_g = grupos_classificacao[g].copy()
            df_g["Seleção"] = df_g["selecao"].apply(com_bandeira)
            
            df_g_display = df_g.rename(columns={
                "posicao": "Pos",
                "jogos": "J",
                "vitorias": "V",
                "empates": "E",
                "derrotas": "D",
                "gols_pro": "GP",
                "gols_contra": "GC",
                "saldo_gols": "SG",
                "pontos": "Pts"
            })
            
            columns_order = ["Pos", "Seleção", "J", "V", "E", "D", "GP", "GC", "SG", "Pts"]
            st.dataframe(
                df_g_display[columns_order],
                width="stretch",
                hide_index=True
            )

# --- PÁGINA 3: Explorador de Partidas ---
elif pagina == "Explorador de partidas":
    st.header("🔍 Explorador de Confrontos Diretos")
    st.markdown(
        "Selecione duas equipes nacionais para prever os gols esperados (xG) e as probabilidades exatas de vitória, empate ou derrota em um confronto simulado."
    )
    
    col1, col2 = st.columns(2)
    with col1:
        time_casa = st.selectbox(
            "Time da Casa",
            selecoes_todas,
            index=selecoes_todas.index("Brazil") if "Brazil" in selecoes_todas else 0,
            format_func=com_bandeira
        )
    with col2:
        time_visitante = st.selectbox(
            "Time Visitante",
            selecoes_todas,
            index=selecoes_todas.index("Spain") if "Spain" in selecoes_todas else 1,
            format_func=com_bandeira
        )
        
    neutro = st.checkbox("Jogo em Campo Neutro", value=True)
    
    st.markdown(" ")
    if st.button("🔮 Prever Partida"):
        if time_casa == time_visitante:
            st.warning("Selecione duas seleções diferentes para simular o confronto!")
        else:
            model_casa = preparado["model_casa"]
            model_visit = preparado["model_visit"]
            colunas_atributos = preparado["colunas_atributos"]
            elo_times = preparado["elo_times"]
            
            # Executar predição
            l_c, l_v, p_v, p_e, p_d = prever_jogo(
                time_casa, time_visitante, neutro, peso_torneio=3,
                elo_times=elo_times, model_casa=model_casa, model_visit=model_visit,
                colunas_atributos=colunas_atributos
            )
            
            st.markdown("---")
            st.subheader(f"📊 Análise do Confronto: {com_bandeira(time_casa)} vs {com_bandeira(time_visitante)}")
            
            # Exibir xG (gols esperados)
            col_xg1, col_xg2 = st.columns(2)
            with col_xg1:
                st.metric(label=f"Gols Esperados (xG) - {time_casa}", value=f"{l_c:.2f}")
            with col_xg2:
                st.metric(label=f"Gols Esperados (xG) - {time_visitante}", value=f"{l_v:.2f}")
                
            st.markdown(" ")
            st.subheader("Probabilidade dos Resultados:")
            
            # Mostrar probabilidade como barra de progresso ou colunas
            col_p1, col_p2, col_p3 = st.columns(3)
            with col_p1:
                st.markdown(f"**Vitória {time_casa}**")
                st.markdown(f"### {p_v * 100:.1f}%")
                st.progress(p_v)
            with col_p2:
                st.markdown("**Empate**")
                st.markdown(f"### {p_e * 100:.1f}%")
                st.progress(p_e)
            with col_p3:
                st.markdown(f"**Vitória {time_visitante}**")
                st.markdown(f"### {p_d * 100:.1f}%")
                st.progress(p_d)
                
            # Detalhamento de ELO
            st.markdown(" ")
            st.markdown(
                f"ℹ️ *Informações de força: ELO {time_casa} = **{elo_times.get(time_casa, 1500.0):.1f}** | "
                f"ELO {time_visitante} = **{elo_times.get(time_visitante, 1500.0):.1f}***"
            )
