# Feature 10 — Fundação e Persistência do Torneio no Supabase

## Contexto
Atendendo à necessidade de acompanhar a Copa do Mundo 2026 rodada a rodada de forma persistente, o estado do torneio (configuração estática de grupos, calendário de chaves e resultados parciais) deve ser migrado de arquivos locais JSON/CSV para tabelas relacionais persistentes no banco de dados Supabase.

## Objetivo
Estruturar o banco de dados Supabase Postgres criando as tabelas de configuração estática e tabelas dinâmicas de resultados, populando-as a partir dos arquivos locais de referência.

## Tabelas no Banco (Schema)

1. **`copa_grupos`**:
   - `id` (bigint PK gerado automaticamente)
   - `grupo` (text) — Letra de A a L
   - `posicao` (integer) — Posição de 1 a 4
   - `selecao` (text) — Nome da seleção nacional

2. **`copa_calendario_mata_mata`**:
   - `match_id` (text PK) — Código de M73 a M104
   - `rodada` (text) — Fase (R32, R16, QF, SF, 3rd, Final)
   - `match_date` (date) — Data da partida
   - `match_time` (text) — Horário da partida
   - `home_slot` (text) — Origem do time da casa (ex: 1A, W73)
   - `away_slot` (text) — Origem do time visitante (ex: 2B, RU74)
   - `winner_advances_to` (text) — ID da partida que o vencedor avança
   - `loser_advances_to` (text) — ID da partida que o perdedor avança (para disputa de 3º lugar)

3. **`copa_mata_mata_resultados`**:
   - `match_id` (text PK referenciando `copa_calendario_mata_mata`)
   - `home_team` (text) — Nome da seleção da casa resolvida
   - `away_team` (text) — Nome da seleção visitante resolvida
   - `gols_casa` (integer) — Gols do time da casa
   - `gols_visitante` (integer) — Gols do time visitante
   - `vencedor` (text) — Nome do vencedor (após prorrogação ou pênaltis)
   - `penaltis_vencedor` (text, nullable) — Nome do vencedor nos pênaltis, se empate

---

## Requisitos
1. Criar um script de inicialização idempotente: [src/inicializar_db.py](src/inicializar_db.py).
2. O script deve ler as tabelas de referência de [data/grupos_copa2026.csv](data/grupos_copa2026.csv) e [data/calendario_copa2026.csv](data/calendario_copa2026.csv) e inseri-las de forma limpa no Supabase.
3. Configurar as chaves estrangeiras apropriadas para garantir consistência relacional.
4. Tratar nulos em `loser_advances_to` (que só existe nas semifinais).

## Critérios de aceite
- Execução bem-sucedida do script `python src/inicializar_db.py` sem falhas.
- `copa_grupos` criada com 48 registros correspondentes aos 12 grupos.
- `copa_calendario_mata_mata` criada com 32 registros de partidas eliminatórias.
- `copa_mata_mata_resultados` criada e inicialmente vazia (pronta para receber placares).

## Verificação
```bash
./.venv/bin/python src/inicializar_db.py
./.venv/bin/python src/inspect_db.py
```
