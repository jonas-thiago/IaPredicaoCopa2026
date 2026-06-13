import os
import pandas as pd
from dotenv import load_dotenv
from tavily import TavilyClient
from langchain_core.tools import tool
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
from db import get_engine

load_dotenv()

def obter_llm():
    """
    Retorna a instância do modelo Gemini se a chave de API estiver configurada.
    Caso contrário, retorna um modelo mock para evitar falhas de inicialização.
    """
    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        return None
    return ChatGoogleGenerativeAI(model="gemini-3.5-flash", google_api_key=api_key, temperature=0.7)

@tool
def gerar_palpite_brasil() -> str:
    """
    Verifica se o Brasil é o líder de probabilidade de título. Se não for, busca
    notícias sobre a Seleção via Tavily e gera uma frase motivacional/dramática
    usando o LLM. Se for o líder, celebra o favoritismo.
    """
    engine = get_engine()
    
    # 1. Obter probabilidade de título de todas as seleções
    try:
        df_prob = pd.read_sql("SELECT selecao, prob_campea FROM gold_probabilidades_copa ORDER BY prob_campea DESC", engine)
    except Exception as e:
        return f"Erro ao ler as probabilidades do banco de dados: {e}"
        
    if df_prob.empty:
        return "Nenhuma probabilidade calculada ainda. Por favor, rode a simulação do Monte Carlo primeiro."
        
    lider = df_prob.iloc[0]["selecao"]
    
    # Encontrar a probabilidade do Brasil
    df_brasil = df_prob[df_prob["selecao"] == "Brazil"]
    prob_brasil = float(df_brasil.iloc[0]["prob_campea"]) if not df_brasil.empty else 0.0
    
    # Se o Brasil for o líder de probabilidade
    if lider == "Brazil":
        return "🏆 O Brasil é atualmente o favorito matemático ao título da Copa de 2026! O hexa é realidade, não há necessidade de drama!"
        
    # Se o Brasil não for o líder, ativa o Modo Palpiteiro
    tavily_key = os.getenv("TAVILY_API_KEY")
    if not tavily_key:
        # Fallback caso a chave do Tavily não esteja configurada
        import random
        frases_mock = [
            f"A matemática diz {prob_brasil*100:.1f}%, mas o coração diz 100%! O hexa vem pela raça brasileira!",
            f"Eles têm a estatística, nós temos a camisa pentacampeã. A caminhada ao hexa já começou!",
            f"Contra dados não há argumentos? Para a Seleção, a superação é a única verdade. Acredita, Brasil!"
        ]
        return f"⚠️ [TAVILY_API_KEY não configurada] Modo Palpiteiro (Mock):\n{random.choice(frases_mock)}"
        
    # Executar busca na internet
    print("Modo Palpiteiro ativado! Executando busca de notícias da Seleção Brasileira...")
    try:
        tavily = TavilyClient(api_key=tavily_key)
        resultados_busca = tavily.search(
            query="Seleção Brasileira futebol preparação convocação notícias recentes",
            max_results=3
        )
        contexto_noticias = "\n".join([f"- {r['title']}: {r['snippet']}" for r in resultados_busca.get("results", [])])
    except Exception as e:
        contexto_noticias = f"Não foi possível buscar notícias na web devido ao erro: {e}"
        
    # Inicializar LLM
    llm = obter_llm()
    if not llm:
        return (
            f"⚠️ [GEMINI_API_KEY não configurada] Modo Palpiteiro:\n"
            f"Mesmo com apenas {prob_brasil*100:.1f}% de chances matemáticas, a Seleção Brasileira "
            f"vai calar os críticos e buscar a glória no mata-mata!"
        )
        
    # Criar prompt e invocar LLM
    prompt = ChatPromptTemplate.from_messages([
        ("system", (
            "Você é o 'Agente Palpiteiro', um torcedor brasileiro fanático, passional, criativo e "
            "dramático. Seu objetivo é consolar e empolgar o torcedor brasileiro, fazendo-o acreditar no hexa "
            "mesmo que a estatística aponte outro favorito.\n\n"
            "Diretrizes:\n"
            "- Crie uma frase motivacional curta (no máximo 2 frases).\n"
            "- Seja muito emocional, dramático e use gírias brasileiras de futebol se apropriado.\n"
            "- Use as notícias recentes fornecidas para dar um tom de atualidade à sua frase.\n"
            "- Quanto menor a probabilidade do Brasil, mais dramático, poético e emocionante você deve ser."
        )),
        ("human", (
            "Notícias recentes da Seleção:\n{noticias}\n\n"
            "Probabilidade matemática atual do Brasil ser campeão: {probabilidade:.1f}%\n"
            "Líder das probabilidades: {lider_atual}\n\n"
            "Gere a frase motivacional do palpiteiro:"
        ))
    ])
    
    chain = prompt | llm
    try:
        resposta = chain.invoke({
            "noticias": contexto_noticias,
            "probabilidade": prob_brasil * 100,
            "lider_atual": lider
        })
        return f"🔥 Modo Palpiteiro:\n{resposta.content}"
    except Exception as e:
        return f"Erro ao gerar a resposta do LLM: {e}"
