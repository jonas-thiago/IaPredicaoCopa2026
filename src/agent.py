import os
import sys
import pandas as pd
from dotenv import load_dotenv
from langchain_core.tools import tool
from langgraph.prebuilt import create_react_agent
from db import get_engine
from tools.palpiteiro import gerar_palpite_brasil, obter_llm
import monte_carlo

load_dotenv()

# Garantir que o diretório src/ esteja no path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

@tool
def consultar_estado_grupos() -> str:
    """
    Calcula e retorna a classificação atualizada da fase de grupos com base
    apenas nas partidas que já foram jogadas (resultados reais inseridos).
    """
    engine = get_engine()
    try:
        # Carregar grupos
        df_grupos = pd.read_sql('SELECT grupo AS "group", posicao AS "position", selecao AS "nation" FROM copa_grupos', engine)
        
        # Carregar jogos que já têm gols registrados
        df_jogos = pd.read_sql('SELECT time_casa, time_visitante, gols_casa, gols_visitante FROM silver_copa2026 WHERE gols_casa IS NOT NULL AND gols_visitante IS NOT NULL', engine)
    except Exception as e:
        return f"Erro ao ler banco de dados: {e}"
        
    grupos_letras = sorted(df_grupos["group"].unique())
    selecoes_todas = df_grupos["nation"].unique()
    
    # Dicionário de estatísticas
    stats = {
        t: {
            "vitorias": 0, "empates": 0, "derrotas": 0,
            "gols_pro": 0, "gols_contra": 0,
            "saldo": 0, "pontos": 0, "jogos": 0
        } for t in selecoes_todas
    }
    
    # Processar jogos reais
    for _, row in df_jogos.iterrows():
        t_casa = row["time_casa"]
        t_visit = row["time_visitante"]
        g_casa = int(row["gols_casa"])
        g_visit = int(row["gols_visitante"])
        
        stats[t_casa]["jogos"] += 1
        stats[t_visit]["jogos"] += 1
        
        stats[t_casa]["gols_pro"] += g_casa
        stats[t_casa]["gols_contra"] += g_visit
        stats[t_casa]["saldo"] += (g_casa - g_visit)
        
        stats[t_visit]["gols_pro"] += g_visit
        stats[t_visit]["gols_contra"] += g_casa
        stats[t_visit]["saldo"] += (g_visit - g_casa)
        
        if g_casa > g_visit:
            stats[t_casa]["pontos"] += 3
            stats[t_casa]["vitorias"] += 1
            stats[t_visit]["derrotas"] += 1
        elif g_casa == g_visit:
            stats[t_casa]["pontos"] += 1
            stats[t_visit]["pontos"] += 1
            stats[t_casa]["empates"] += 1
            stats[t_visit]["empates"] += 1
        else:
            stats[t_visit]["pontos"] += 3
            stats[t_visit]["vitorias"] += 1
            stats[t_casa]["derrotas"] += 1
            
    # Formatar classificação em texto legível
    output = []
    output.append("=== CLASSIFICAÇÃO ATUAL DA FASE DE GRUPOS ===\n")
    
    for g in grupos_letras:
        times_grupo = df_grupos[df_grupos["group"] == g]["nation"].tolist()
        
        # Ordenar por: pontos -> saldo -> gols_pro -> nome (alfabético)
        times_grupo.sort(
            key=lambda t: (stats[t]["pontos"], stats[t]["saldo"], stats[t]["gols_pro"], t),
            reverse=True
        )
        
        output.append(f"Grupo {g}:")
        for pos, t in enumerate(times_grupo):
            s = stats[t]
            output.append(
                f"  {pos+1}. {t:<18} | Pts: {s['pontos']:>2} | J: {s['jogos']} | V: {s['vitorias']} | E: {s['empates']} | D: {s['derrotas']} | GP: {s['gols_pro']} | GC: {s['gols_contra']} | SG: {s['saldo']}"
            )
        output.append("")
        
    return "\n".join(output)

@tool
def rodar_simulacao_monte_carlo() -> str:
    """
    Roda o motor de simulação de Monte Carlo por 1000 vezes usando a força atual das seleções
    e os resultados reais registrados no banco de dados. Atualiza as probabilidades de todas
    as seleções no Supabase e retorna as top 10 favoritas ao título.
    """
    try:
        print("Disparando motor de Monte Carlo...")
        # Executar a simulação (que atualiza as tabelas no Supabase)
        monte_carlo.main()
        
        # Ler os novos resultados
        engine = get_engine()
        df_prob = pd.read_sql("SELECT selecao, prob_campea, prob_semi, prob_final FROM gold_probabilidades_copa ORDER BY prob_campea DESC LIMIT 10", engine)
        
        output = ["=== SIMULAÇÃO CONCLUÍDA! TOP 10 FAVORITAS AO TÍTULO ===\n"]
        for idx, row in df_prob.iterrows():
            output.append(
                f"{idx+1:>2}. {row['selecao']:<18} | Campeã: {row['prob_campea']*100:>5.1f}% | Final: {row['prob_final']*100:>5.1f}% | Semis: {row['prob_semi']*100:>5.1f}%"
            )
        return "\n".join(output)
    except Exception as e:
        return f"Erro ao rodar a simulação do Monte Carlo: {e}"

@tool
def identificar_eliminados() -> str:
    """
    Identifica todas as seleções que estão matematicamente eliminadas do torneio
    (ou seja, cuja probabilidade acumulada de classificação para o mata-mata é 0.0%).
    """
    engine = get_engine()
    try:
        df = pd.read_sql("SELECT selecao FROM gold_probabilidades_copa WHERE prob_grupo = 0.0 ORDER BY selecao", engine)
        if df.empty:
            return "Nenhuma seleção está matematicamente eliminada ainda!"
        
        lista_eliminados = df["selecao"].tolist()
        return "❌ Seleções matematicamente eliminadas:\n" + "\n".join([f"- {t}" for t in lista_eliminados])
    except Exception as e:
        return f"Erro ao consultar o banco de dados: {e}"

def obter_agente():
    """
    Constrói e compila o agente LangGraph ReAct equipado com as tools da Copa.
    """
    llm = obter_llm()
    
    # Se não houver LLM configurado, retorna None. O Streamlit lidará com o fallback.
    if not llm:
        return None
        
    tools = [
        consultar_estado_grupos,
        rodar_simulacao_monte_carlo,
        identificar_eliminados,
        gerar_palpite_brasil
    ]
    
    system_prompt = (
        "Você é o 'IA Predictor', o assistente inteligente oficial da Copa do Mundo 2026.\n"
        "Seu objetivo é interpretar o andamento da Copa do Mundo e apresentar probabilidades baseadas em dados.\n\n"
        "Suas regras de conduta:\n"
        "1. Nunca calcule ou estime probabilidades de cabeça. Use sempre as tools disponíveis.\n"
        "2. Se o usuário pedir para rodar a simulação, use a tool 'rodar_simulacao_monte_carlo'.\n"
        "3. Se o usuário quiser ver a classificação dos grupos, use a tool 'consultar_estado_grupos'.\n"
        "4. Se o usuário perguntar quem já está eliminado, use a tool 'identificar_eliminados'.\n"
        "5. Sempre que o Brasil não estiver na liderança das probabilidades, ou a pedido do usuário, use a tool 'gerar_palpite_brasil' para dar um palpite emocional.\n"
        "6. Explique os resultados das tools com clareza e com entusiasmo futebolístico, mantendo viva a emoção da Copa!"
    )
    
    # Criar agente ReAct nativo do LangGraph
    agent = create_react_agent(
        model=llm,
        tools=tools,
        prompt=system_prompt
    )
    return agent
