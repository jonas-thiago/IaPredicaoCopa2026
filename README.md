# 🏆 IA Predição Copa 2026

Este projeto consiste em um **Agente de Inteligência Artificial** integrado com um **Motor Estatístico de Monte Carlo** para prever as chances das seleções na Copa do Mundo de 2026 em tempo real, rodada a rodada, conforme os resultados reais do torneio acontecem.

---

## 🎯 Contexto e Funcionamento

O sistema é alimentado por dados históricos e modelos matemáticos de distribuição de Poisson que estimam a expectativa de gols (xG) baseados no ELO dinâmico de cada seleção. 
A grande inovação está na **orquestração de IA com LangChain e LangGraph** para ler o estado de jogos inseridos na base de dados, disparar simulações estatísticas em Python (Monte Carlo) para completar as rodadas restantes e interpretar os resultados de maneira criativa e automatizada, incluindo o divertido **Modo Palpiteiro** (que consola e empolga a torcida brasileira quando o hexa está matematicamente sob ameaça).

---

## 📂 Organização do Projeto e Arquivos

O projeto está estruturado de forma limpa e modularizada dentro das seguintes pastas:

### 🖥️ Interface e Visualização
* **[app.py](app.py):** Painel interativo premium desenvolvido em Streamlit. Contém visualizações gráficas das probabilidades (usando Altair), chaveamento dinâmico de mata-mata, simulador ao vivo, registro manual de resultados de partidas e uma área de chat integrada com o Agente de IA.

### ⚙️ Motor Estatístico e Regras
* **[src/monte_carlo.py](src/monte_carlo.py):** O coração analítico do projeto. Executa simulações completas da Copa do Mundo 2026 em Python. Ele é agnóstico ao LLM para cálculos matemáticos, lendo os placares reais já digitados e simulando os jogos restantes. No fim, salva os novos resultados na tabela `gold_probabilidades_copa`.
* **[src/previsao.py](src/previsao.py):** Lógica que estima o xG (gols esperados) para partidas diretas baseado no modelo de Poisson e nos valores de ELO das seleções.

### 🤖 Agente e Ferramentas (LangChain & LangGraph)
* **[src/agent.py](src/agent.py):** Definição do agente de tomada de decisão construído sobre o runtime de grafos do LangGraph (usando `create_react_agent`). Equipado com as ferramentas customizadas do assistente oficial da Copa.
* **[src/tools/palpiteiro.py](src/tools/palpiteiro.py):** Implementação da ferramenta do **Modo Palpiteiro**. Se o Brasil não for líder em probabilidade de título, o agente faz uma varredura de notícias recentes usando a API **Tavily** e gera uma frase motivacional/dramática/criativa via Gemini LLM para incentivar a torcida.

### 🗄️ Persistência de Dados e Utilitários
* **[src/db.py](src/db.py):** Conexão com o banco de dados PostgreSQL do Supabase, incluindo tratamentos para credenciais com caracteres especiais.
* **[src/inicializar_db.py](src/inicializar_db.py):** Script de carga inicial para estruturar e popular as configurações de grupos, equipes e calendário da fase de mata-mata no banco.
* **[src/inspect_db.py](src/inspect_db.py):** Utilitário para verificar a integridade e contar os registros das tabelas no Supabase.

### 📋 Configurações
* **[requirements.txt](requirements.txt):** Dependências do projeto (pandas, sqlalchemy, streamlit, langchain, langgraph, langchain-google-genai, langchain-tavily).
* **[idea.md](idea.md):** Quadro Kanban de planejamento, atribuição de skills e cronograma de implementação do agente.

---

## 🔀 Orquestração e Fluxo de Dados

A sincronização de ponta a ponta obedece ao seguinte fluxo determinístico:

```mermaid
graph TD
    A[Usuário insere Placar Real no Streamlit] -->|Salvar| B[(Supabase: silver_copa2026)]
    C[Usuário conversa com o Agente de IA] -->|Chat Input| D[Agente: LangGraph ReAct]
    D -->|Chama Tool| E(Tool: rodar_simulacao_monte_carlo)
    E -->|Executa| F[monte_carlo.py: Roda 1000 Poisson]
    F -->|Lê resultados inseridos| B
    F -->|Grava novas probabilidades calculadas| G[(Supabase: gold_probabilidades_copa)]
    G -->|Leitura Automática| H[Streamlit UI: Atualiza tabelas e gráficos Altair]
    D -->|Se o Brasil não for o líder nas probab.| I(Tool: gerar_palpite_brasil)
    I -->|Faz Busca Web| J[Tavily Search API]
    J -->|Extrai notícias| K[Prompt no Gemini LLM]
    K -->|Gera texto passional e dramático| L[Chat UI: Frase do Palpiteiro]
```

---

## 🚀 Como Executar

### 1. Preparar o Ambiente
Crie e ative o ambiente virtual, em seguida instale as dependências:
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configurar o Banco de Dados e Variáveis
Configure suas chaves e o link do Supabase no arquivo `.env` na raiz do projeto:
```env
DATABASE_URL=postgresql://seu_usuario:sua_senha@host:port/postgres
TAVILY_API_KEY=sua_tavily_key
GEMINI_API_KEY=sua_gemini_key
```

Inicialize o banco de dados (tabelas e parâmetros da Copa):
```bash
python src/inicializar_db.py
```

### 3. Executar o Dashboard
Rode o aplicativo Streamlit localmente:
```bash
streamlit run app.py
```
Acesse a página **"Painel do Agente & Resultados"** no menu lateral para registrar placares reais ou interagir com o agente.