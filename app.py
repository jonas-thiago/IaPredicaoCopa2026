import os
import sys
import altair as alt
import pandas as pd
import streamlit as st
from dotenv import load_dotenv

# Carregar variáveis de ambiente do arquivo .env
load_dotenv()

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

from db import get_engine, get_raw_connection
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

# Barra Lateral (Menu de Navegação)
st.sidebar.title("Navegação")
pagina = st.sidebar.radio(
    "Ir para:",
    ["Probabilidades pré-computadas", "Simulação ao vivo", "Explorador de partidas", "Painel do Agente & Resultados"]
)

st.sidebar.markdown("---")
st.sidebar.info(
    "**IAPredict** é um modelo matemático baseado em distribuição Poisson e ELO dinâmico que estima a probabilidade de desempenho de cada seleção na Copa de 2026. Feito com ❤️ e dados históricos reais."
)

# Título principal do dashboard
st.title("🏆 IAPredict — Previsão da Copa do Mundo 2026")
st.markdown("---")

# Funções Auxiliares para gravação e limpeza de dados
def salvar_resultado_banco(time_casa, time_visitante, gols_casa, gols_visitante):
    conn = get_raw_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE silver_copa2026
                SET gols_casa = %s, gols_visitante = %s
                WHERE time_casa = %s AND time_visitante = %s;
            """, (gols_casa, gols_visitante, time_casa, time_visitante))
        conn.commit()
        return True
    except Exception as e:
        st.error(f"Erro ao salvar resultado: {e}")
        return False
    finally:
        conn.close()

def resetar_resultados_banco():
    conn = get_raw_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("UPDATE silver_copa2026 SET gols_casa = NULL, gols_visitante = NULL;")
            cur.execute("DELETE FROM copa_mata_mata_resultados;")
        conn.commit()
        return True
    except Exception as e:
        st.error(f"Erro ao resetar: {e}")
        return False
    finally:
        conn.close()

# --- PÁGINA 1: Probabilidades Pré-computadas ---
if pagina == "Probabilidades pré-computadas":
    st.header("📊 Probabilidades do Torneio (Visão Geral)")
    st.markdown(
        "Essas probabilidades são calculadas rodando as simulações de Monte Carlo baseadas nos resultados reais gravados no banco de dados."
    )
    
    try:
        df_prob = carregar_probabilidades_banco()
    except Exception as e:
        st.error(f"Erro ao carregar dados do banco: {e}")
        st.info("💡 Dica: Se o banco estiver vazio, acesse a página 'Painel do Agente & Resultados' e clique para rodar uma simulação inicial.")
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
        "Abaixo, rodamos **uma única simulação aleatória** do torneio completo a partir do estado atual registrado no banco de dados. Clique para ver uma projeção possível."
    )
    
    # Botão para re-simular
    if st.button("🔄 Rodar Nova Simulação"):
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
                
                # Destacar vencedor usando HTML <b>
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

# --- PÁGINA 4: Painel do Agente & Resultados ---
elif pagina == "Painel do Agente & Resultados":
    st.header("🤖 Painel do Agente Predictor & Registro de Resultados")
    st.markdown(
        "Nesta página, você pode registrar resultados reais das partidas da Copa do Mundo para atualizar o modelo de simulação de Monte Carlo. Você também pode conversar diretamente com o Agente de IA para fazer perguntas e comandar simulações."
    )
    
    col_reg, col_chat = st.columns(2)
    
    with col_reg:
        st.subheader("📝 Registrar Placar da Fase de Grupos")
        
        # Ler jogos da Copa do banco
        df_jogos_copa = preparado["df_jogos_copa"]
        
        # Filtros de busca
        times_disponiveis = sorted(list(set(df_jogos_copa["time_casa"].tolist() + df_jogos_copa["time_visitante"].tolist())))
        time_busca = st.selectbox("Filtrar jogos por seleção:", ["Todos"] + times_disponiveis)
        
        if time_busca != "Todos":
            jogos_filtrados = df_jogos_copa[(df_jogos_copa["time_casa"] == time_busca) | (df_jogos_copa["time_visitante"] == time_busca)]
        else:
            jogos_filtrados = df_jogos_copa
            
        # Criar texto legível para o dropdown de partidas
        def format_jogo(row):
            status = ""
            if pd.notna(row["gols_casa"]) and pd.notna(row["gols_visitante"]):
                status = f" (Placar: {int(row['gols_casa'])}x{int(row['gols_visitante'])})"
            return f"{row['time_casa']} vs {row['time_visitante']}{status}"
            
        lista_opcoes = [format_jogo(row) for _, row in jogos_filtrados.iterrows()]
        
        if not lista_opcoes:
            st.info("Nenhum jogo encontrado para a seleção filtrada.")
        else:
            jogo_selecionado_txt = st.selectbox("Selecione a partida para atualizar:", lista_opcoes)
            
            # Recuperar linha correspondente
            index_selecionado = lista_opcoes.index(jogo_selecionado_txt)
            row_selecionado = jogos_filtrados.iloc[index_selecionado]
            
            time_c = row_selecionado["time_casa"]
            time_v = row_selecionado["time_visitante"]
            
            gols_c_atual = int(row_selecionado["gols_casa"]) if pd.notna(row_selecionado["gols_casa"]) else 0
            gols_v_atual = int(row_selecionado["gols_visitante"]) if pd.notna(row_selecionado["gols_visitante"]) else 0
            
            st.markdown(f"**Atualizando placar de:** {com_bandeira(time_c)} vs {com_bandeira(time_v)}")
            
            col_c, col_v = st.columns(2)
            with col_c:
                gols_c = st.number_input(f"Gols - {time_c}", min_value=0, max_value=20, value=gols_c_atual, step=1, key="gols_c_input")
            with col_v:
                gols_v = st.number_input(f"Gols - {time_v}", min_value=0, max_value=20, value=gols_v_atual, step=1, key="gols_v_input")
                
            if st.button("💾 Salvar Resultado", use_container_width=True):
                if salvar_resultado_banco(time_c, time_v, gols_c, gols_v):
                    st.success(f"Resultado salvo! {time_c} {gols_c} x {gols_v} {time_v}")
                    # Limpar cache e recarregar dados do banco
                    st.cache_resource.clear()
                    st.cache_data.clear()
                    st.rerun()
                    
        st.markdown("---")
        st.subheader("⚙️ Ações Globais")
        
        if st.button("🚨 Resetar Todos os Resultados Reais", use_container_width=True, help="Limpa todos os resultados reais e volta a Copa para o estado original 0x0 simulado"):
            if resetar_resultados_banco():
                st.success("Copa do Mundo resetada com sucesso para o estado inicial!")
                st.cache_resource.clear()
                st.cache_data.clear()
                st.rerun()
                
    with col_chat:
        st.subheader("🤖 Conversar com o IA Predictor")
        
        # Verificar se as chaves de API estão definidas no .env
        api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        
        if not api_key:
            st.warning("⚠️ **Chave de API do Gemini não configurada no arquivo .env!**")
            st.info("Para conversar com o agente de IA, configure a variável **GEMINI_API_KEY** em seu arquivo **.env** na raiz do projeto e reinicie o app.")
        else:
            try:
                from agent import obter_agente
                agent = obter_agente()
            except Exception as e:
                st.error(f"Erro ao inicializar o agente: {e}")
                agent = None
                
            if agent:
                # Inicializar chat history na sessão
                if "messages" not in st.session_state:
                    st.session_state.messages = [
                        {"role": "assistant", "content": "Olá! Sou o IA Predictor. Posso ajudar você a ver a classificação atual da Copa, simular o torneio com base nos resultados inseridos, apontar quem está eliminado e te dar palpites dramáticos sobre o Brasil! O que deseja fazer?"}
                    ]
                    
                # Exibir mensagens
                for msg in st.session_state.messages:
                    with st.chat_message(msg["role"]):
                        st.write(msg["content"])
                        
                # Entrada do usuário
                if prompt := st.chat_input("Ex: 'Rode a simulação da Copa', 'Quem está eliminado?', 'Qual a classificação do grupo C?'"):
                    # Exibir entrada
                    with st.chat_message("user"):
                        st.write(prompt)
                    st.session_state.messages.append({"role": "user", "content": prompt})
                    
                    # Chamar agente
                    with st.chat_message("assistant"):
                        with st.spinner("Processando e raciocinando..."):
                            try:
                                config = {"configurable": {"thread_id": "streamlit-session"}}
                                result = agent.invoke({"messages": [{"role": "user", "content": prompt}]}, config=config)
                                raw_content = result["messages"][-1].content
                                
                                # Processar se for lista (blocos de conteúdo) ou string pura
                                if isinstance(raw_content, list):
                                    response_text = ""
                                    for block in raw_content:
                                        if isinstance(block, dict) and block.get("type") == "text":
                                            response_text += block.get("text", "")
                                        elif isinstance(block, str):
                                            response_text += block
                                else:
                                    response_text = str(raw_content)
                                    
                                st.write(response_text)
                                st.session_state.messages.append({"role": "assistant", "content": response_text})
                                
                                # Se a resposta menciona que a simulação foi executada, limpa o cache de dados das tabelas
                                if "SIMULAÇÃO CONCLUÍDA" in response_text or "atualizada com sucesso" in response_text.lower():
                                    st.cache_data.clear()
                            except Exception as ex:
                                st.error(f"Erro ao executar o agente: {ex}")
