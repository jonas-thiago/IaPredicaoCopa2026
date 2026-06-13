# Feature 11 — Orquestração de IA com LangGraph e Chat no Dashboard

## Contexto
O objetivo é transformar a interface estática do app em um dashboard dinâmico onde o usuário possa registrar placares reais de futebol, e um agente inteligente seja capaz de executar e explicar novas simulações de probabilidade estatística, além de buscar notícias online.

## Objetivo
Implementar o Agente de IA com **LangChain e LangGraph** e as ferramentas de suporte (incluindo Tavily), integrando-os a uma interface de chat e de entrada de dados no Streamlit.

## Componentes

1. **Agente LangGraph ReAct** ([src/agent.py](src/agent.py)):
   - Inicializa a partir de `ChatGoogleGenerativeAI` usando o modelo `gemini-1.5-flash`.
   - Utiliza `create_react_agent` nativo do LangGraph com um prompt do sistema que instrui a IA a nunca calcular dados de cabeça, mas sim delegar às tools correspondentes.

2. **Ferramentas (Tools)**:
   - **`consultar_estado_grupos`**: Calcula a tabela de classificação do grupo dinamicamente no banco a partir das linhas com placares reais registrados na tabela `silver_copa2026`.
   - **`rodar_simulacao_monte_carlo`**: Aciona o motor estático de Monte Carlo e atualiza a tabela `gold_probabilidades_copa`. Retorna a lista de 10 seleções mais favoritas.
   - **`identificar_eliminados`**: Varre a tabela de probabilidades buscando seleções com chance 0% de classificação para a fase seguinte.
   - **`gerar_palpite_brasil`** ([src/tools/palpiteiro.py](src/tools/palpiteiro.py)): Ativa o Modo Palpiteiro. Se o Brasil não for líder, realiza busca de notícias da Seleção via **Tavily** e gera uma frase motivacional dramática com o Gemini LLM.

3. **Dashboard e Entrada de Dados** ([app.py](app.py)):
   - **Configuração de Chaves de API**: Inputs confidenciais de formulário na barra lateral para carregar `GEMINI_API_KEY` e `TAVILY_API_KEY` dinamicamente no `os.environ`.
   - **Registro de Placares**: Filtros por equipe e dropdown de partidas na fase de grupos para que o usuário insira gols e grave no banco via query SQL (UPDATE).
   - **Limpeza de Dados (Reset)**: Botão para resetar o torneio de volta ao estado inicial simulado (gols nulos e mata-mata limpo).
   - **Chat Container**: Interface interativa de chat em tempo real que consome o agente LangGraph ReAct.

---

## Requisitos
1. Integrar as chaves na lateral com validação segura para evitar crashes quando os tokens de API estiverem vazios.
2. Limpar o cache de visualização do Streamlit (`st.cache_resource.clear()` / `st.cache_data.clear()`) sempre que uma partida for inserida ou a simulação for concluída, forçando a re-renderização instantânea.
3. Não envolver o LLM em cálculos matemáticos diretos.

## Critérios de aceite
- O app do Streamlit exibe a página **"Painel do Agente & Resultados"** com seções separadas para chat e registro de partidas.
- Ao salvar um placar de grupo, a tabela de classificação atualiza instantaneamente.
- O agente responde no chat invocando e formatando as respostas das tools correspondentes com sucesso.

## Verificação
```bash
streamlit run app.py
```
- Insira as chaves de API do Gemini e Tavily na barra lateral.
- Mande mensagem no chat: "Rode a simulação da Copa" e verifique a ativação da tool no terminal.
- Digite um placar e verifique se as tabelas de classificação e gráficos Altair atualizam dinamicamente.
