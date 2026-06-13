# Agente de Previsão da Copa do Mundo 2026

O projeto consiste em transformar um código de previsão estático em um agente de IA que atualiza as probabilidades do torneio em tempo real, rodada a rodada.

---

## Fundação

O ponto de partida é o código original de previsão, que já calcula probabilidades baseadas em métricas como Elo e ranking FIFA antes do torneio começar. O agente vai partir desse estado inicial e atualizá-lo conforme os resultados reais chegam.

Para isso, o primeiro passo é construir uma estrutura de estado do torneio — dataclasses representando grupos, times, partidas e o bracket eliminatório — com persistência em JSON para salvar o estado entre as rodadas sem perder nada.

---

## Motor de Simulação

O coração do projeto é um motor de Monte Carlo que roda inteiramente em Python, sem envolver o LLM nos cálculos. A lógica é: dado o estado atual da tabela com os resultados já registrados, simular os jogos restantes centenas de milhares de vezes usando as forças originais das seleções para calcular probabilidade condicional de classificação e título.

O modelo de Poisson gera resultados realistas por jogo — cada simulação parte do estado real já acumulado e completa os jogos que ainda não aconteceram. O percentual de vezes que cada time classifica ou vence o torneio nessas simulações vira a probabilidade exibida.

Isso garante que se o Brasil perdeu o primeiro jogo, as simulações partem de 0 pontos reais, e a probabilidade cai de forma matematicamente justa. Não é o LLM estimando — é estatística pura.

A ideia é que nós tenhamos uma pagina de simulação onde registramos os resultados da primeira rodada, por exemplo, e o agente rode as tools que precisam para gerar os resultados que precisamos até a resposta final utilizando as tools e fazendo todo o context engineering corretamente com as tools.
---

## Tools do Agente


O agente orquestra tres tools principais.  A primeira consulta o estado atual dos grupos. A segunda dispara o motor de Monte Carlo e devolve as probabilidades atualizadas para todas as seleções. A terceira identifica times já matematicamente eliminados.

A regra fundamental é que o LLM nunca calcula nada diretamente — ele decide quais tools chamar, em qual ordem, e interpreta os resultados para gerar narrativa.

---

## Modo Palpiteiro

A quarta tool é o destaque da live. Sempre que o Brasil não estiver na primeira posição do ranking de probabilidades de título — independente de ter perdido ou não —, o agente ativa o Modo Palpiteiro. A tool faz uma busca na internet por informações recentes da Seleção Brasileira, como declarações de jogadores, histórico no torneio ou qualquer dado relevante, e passa esse contexto para o LLM gerar uma frase motivacional curta para o torcedor brasileiro acreditar no hexa, mesmo que a matemática aponte outro favorito. Quanto menor a probabilidade do Brasil, mais dramática e criativa a frase.

---

## Visualização

Um dashboard em Streamlit exibe as tabelas de grupos com os percentuais de classificação de cada time, um gráfico de barras com as probabilidades de título de todas as seleções, e o bracket do mata-mata atualizando conforme os classificados são definidos. Tudo atualiza ao vivo durante a live após cada resultado digitado.

---

## Plano de Implementação & Atribuição de Skills

Com base nos seus requisitos de usar **LangChain e LangGraph** (evitando Deep Agents), usar o **Supabase** para persistência relacional das simulações, e usar **Tavily** para busca online no Modo Palpiteiro, aqui está o plano detalhado de tarefas com as respectivas habilidades do agente associadas:

### 📋 Quadro de Tarefas do Projeto

| ID | Tarefa | Módulo/Arquivo Afetado | Frameworks | Skills Atribuídas | Status |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **01** | **Fundação: Banco de Dados & Estado do Torneio** <br> Modelar e criar tabelas no Supabase para grupos, seleções, calendário e estado do mata-mata (bracket), garantindo uma migração suave do JSON para tabelas Postgres sem quebras. | [src/db.py](src/db.py) | Supabase SDK, SQL (DDL) | [supabase](.agents/skills/supabase/SKILL.md) e [supabase-postgres-best-practices](.agents/skills/supabase-postgres-best-practices/SKILL.md) | **Concluído** |
| **02** | **Motor de Simulação de Monte Carlo** <br> Integrar o código de simulação em python para ler o estado atual do Supabase, rodar Poisson/Monte Carlo para as partidas restantes e calcular probabilidades, gravando o resultado na tabela `gold_probabilidades_copa`. | [src/monte_carlo.py](src/monte_carlo.py) | Python (Pandas/Statsmodels), SQL | [langgraph-fundamentals](.agents/skills/langgraph-fundamentals/SKILL.md) e [supabase-postgres-best-practices](.agents/skills/supabase-postgres-best-practices/SKILL.md) | **Concluído** |
| **03** | **Orquestrador do Agente & Definição de Tools** <br> Criar o agente LangGraph ReAct para gerenciar a lógica de tomada de decisão. Definir as tools principais (Consulta de Estado, Gatilho de Simulação, e Validação de Eliminados). | Novo arquivo (ex: `src/agent.py`) | LangGraph, LangChain Core | [langchain-fundamentals](.agents/skills/langchain-fundamentals/SKILL.md) e [langgraph-fundamentals](.agents/skills/langgraph-fundamentals/SKILL.md) | **Concluído** |
| **04** | **Modo Palpiteiro** <br> Implementar a tool que verifica se o Brasil é o favorito. Se não for, usa a API de busca Tavily para coletar contexto de notícias da Seleção e passa para o LLM gerar a frase motivacional correspondente. | Novo arquivo (ex: `src/tools/palpiteiro.py`) | LangChain, Tavily Search | [langchain-fundamentals](.agents/skills/langchain-fundamentals/SKILL.md) e [langchain-middleware](.agents/skills/langchain-middleware/SKILL.md) | **Concluído** |
| **05** | **Dashboard Streamlit Premium** <br> Atualizar a interface do Streamlit para ler os dados em tempo real do Supabase e renderizar tabelas de grupos, chaves dinâmicas de mata-mata, gráficos Altair polidos e o texto motivacional do Modo Palpiteiro. | [app.py](app.py) | Streamlit, Altair | [supabase](.agents/skills/supabase/SKILL.md) | **Concluído** |
| **06** | **Configuração de Dependências & Ambiente** <br> Ajustar arquivos de dependências com as versões corretas de LangChain, LangGraph, Supabase, Psycopg2 e Tavily. | `requirements.txt` / `.env` | pip | [langchain-dependencies](.agents/skills/langchain-dependencies/SKILL.md) | **Concluído** |

---

> [!NOTE]
> **Fluxo de Dados Decidido:** 
> 1. O usuário edita/registra um placar no Streamlit.
> 2. O Streamlit envia a requisição ao agente ou banco de dados.
> 3. O agente executa a tool de simulação.
> 4. A simulação lê os resultados inseridos, roda o Monte Carlo em Python e grava em lote no banco Supabase.
> 5. O Streamlit atualiza automaticamente sua visualização ao ler os dados modificados do banco.

> [!TIP]
> **Inicialização do Projeto:**
> Antes de começar a programar o agente, certifique-se de ler o [ecosystem-primer](.agents/skills/ecosystem-primer/SKILL.md) para garantir que as variáveis de ambiente necessárias para o LangSmith (como `LANGSMITH_TRACING=true` e `LANGSMITH_API_KEY`) estejam configuradas corretamente para rastreabilidade.

