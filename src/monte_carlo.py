import os
import sys
import pickle
import io
import pandas as pd
import numpy as np
import statsmodels.api as sm
from scipy.optimize import linear_sum_assignment
from dotenv import load_dotenv

# Garantir que o diretório src/ esteja no path para importações flat
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from db import get_engine, get_raw_connection

# Cache global para os gols esperados preditos
LAMBDA_CACHE = {}

def obter_lambdas(time_casa, time_visitante, neutro, elo_times, model_casa, model_visit, colunas_atributos):
    """
    Retorna os lambdas (gols esperados) para o confronto, buscando no cache ou predizendo.
    """
    key = (time_casa, time_visitante, neutro)
    if key not in LAMBDA_CACHE:
        elo_c = elo_times.get(time_casa, 1500.0)
        elo_v = elo_times.get(time_visitante, 1500.0)
        dif_elo = elo_c - elo_v
        
        # DataFrame de entrada
        df_row = pd.DataFrame([{
            "elo_casa": float(elo_c),
            "elo_visitante": float(elo_v),
            "dif_elo": float(dif_elo),
            "neutro": int(neutro),
            "peso_torneio": 3,  # Peso da Copa do Mundo
            "peso_recencia": 1.0  # Presente
        }])
        
        # Adicionar constante e ordenar as colunas
        X_row = sm.add_constant(df_row, has_constant="add")
        colunas_com_constante = ["const"] + colunas_atributos
        X_row = X_row[colunas_com_constante]
        
        # Predizer λ
        l_c = float(model_casa.predict(X_row).iloc[0])
        l_v = float(model_visit.predict(X_row).iloc[0])
        
        LAMBDA_CACHE[key] = (l_c, l_v)
        
    return LAMBDA_CACHE[key]

def designar_terceiros(terceiros, slots):
    """
    Associa de forma ótima os 8 melhores terceiros colocados aos slots do mata-mata
    utilizando matching bipartido (scipy.optimize.linear_sum_assignment).
    """
    # Matriz de custo 8x8
    cost_matrix = np.zeros((8, 8))
    
    for i, t in enumerate(terceiros):
        grupo = t["grupo"]
        for j, slot in enumerate(slots):
            # O slot de mata-mata é ex: '3ABCDF'
            grupos_elegiveis = slot[1:] # ex: 'ABCDF'
            if grupo in grupos_elegiveis:
                cost_matrix[i, j] = 0
            else:
                cost_matrix[i, j] = 9999.0  # Penalidade alta para inelegíveis
                
    row_ind, col_ind = linear_sum_assignment(cost_matrix)
    
    map_slots = {}
    for r, c in zip(row_ind, col_ind):
        map_slots[slots[c]] = terceiros[r]["time"]
        
    return map_slots

NOMES_RODADA = {
    "R32": "32-avos de final",
    "R16": "Oitavas de final",
    "QF": "Quartas de final",
    "SF": "Semifinal",
    "3rd": "Disputa do 3º lugar",
    "Final": "Final"
}

slots_terceiros = ['3ABCDF', '3CDFGH', '3CEFHI', '3EHIJK', '3BEFIJ', '3AEHIJ', '3EFGIJ', '3DEIJL']

def preparar():
    """
    Carrega modelos e dados do Supabase e retorna um dicionário pronto para simulações.
    """
    dir_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    
    # 1. Carregar pickles de modelo
    with open(os.path.join(dir_path, "models/modelo_poisson_casa.pkl"), "rb") as f:
        model_casa = pickle.load(f)
    with open(os.path.join(dir_path, "models/modelo_poisson_visitante.pkl"), "rb") as f:
        model_visit = pickle.load(f)
    with open(os.path.join(dir_path, "models/colunas_atributos.pkl"), "rb") as f:
        colunas_atributos = pickle.load(f)
        
    # Carregar dados do banco de dados
    engine = get_engine()
    
    # ELOs do banco
    df_elo = pd.read_sql("SELECT selecao, elo FROM silver_elo_atual", engine)
    elo_times = dict(zip(df_elo["selecao"], df_elo["elo"]))
    
    # Grupos da copa_grupos
    df_grupos = pd.read_sql('SELECT grupo AS "group", posicao AS "position", selecao AS "nation" FROM copa_grupos', engine)
    
    # Calendário da copa_calendario_mata_mata
    df_calendario = pd.read_sql('SELECT match_id, rodada AS "round", match_date, match_time, home_slot, away_slot, winner_advances_to, loser_advances_to FROM copa_calendario_mata_mata ORDER BY CAST(SUBSTRING(match_id FROM 2) AS INTEGER)', engine)
    
    # Jogos de grupos da silver_copa2026
    df_jogos_copa = pd.read_sql('SELECT time_casa, time_visitante, neutro, gols_casa, gols_visitante FROM silver_copa2026', engine)
    
    # Resultados reais de mata-mata
    df_resultados_mata_mata = pd.read_sql('SELECT match_id, home_team, away_team, gols_casa, gols_visitante, vencedor, penaltis_vencedor FROM copa_mata_mata_resultados', engine)
    
    return {
        "model_casa": model_casa,
        "model_visit": model_visit,
        "colunas_atributos": colunas_atributos,
        "elo_times": elo_times,
        "df_grupos": df_grupos,
        "df_calendario": df_calendario,
        "df_jogos_copa": df_jogos_copa,
        "df_resultados_mata_mata": df_resultados_mata_mata
    }

def simular_torneio_detalhado(preparado):
    """
    Executa UMA simulação detalhada da Copa 2026 considerando os resultados reais já inseridos, e retorna:
    - podio: dict com 'campeao', 'vice', 'terceiro', 'quarto'
    - grupos_classificacao: dict de DataFrames de classificação por grupo
    - mata_mata: lista de jogos simulados no mata-mata
    """
    model_casa = preparado["model_casa"]
    model_visit = preparado["model_visit"]
    colunas_atributos = preparado["colunas_atributos"]
    elo_times = preparado["elo_times"]
    df_jogos_copa = preparado["df_jogos_copa"]
    df_grupos = preparado["df_grupos"]
    df_calendario = preparado["df_calendario"]
    df_resultados_mata_mata = preparado.get("df_resultados_mata_mata", pd.DataFrame())
    
    grupos_letras = sorted(df_grupos["group"].unique())
    selecoes_todas = df_grupos["nation"].unique()
    
    # Dicionário de estatísticas do grupo para cada equipe
    stats = {
        t: {
            "vitorias": 0, "empates": 0, "derrotas": 0,
            "gols_pro": 0, "gols_contra": 0,
            "saldo": 0, "pontos": 0, "random": np.random.rand()
        } for t in selecoes_todas
    }
    
    # 1. Simular Fase de Grupos
    for _, row in df_jogos_copa.iterrows():
        t_casa = row["time_casa"]
        t_visit = row["time_visitante"]
        neutro = bool(row["neutro"])
        
        # Se os gols estão preenchidos no banco, é um resultado real
        if pd.notna(row["gols_casa"]) and pd.notna(row["gols_visitante"]):
            g_casa = int(row["gols_casa"])
            g_visit = int(row["gols_visitante"])
        else:
            l_c, l_v = obter_lambdas(t_casa, t_visit, neutro, elo_times, model_casa, model_visit, colunas_atributos)
            g_casa = np.random.poisson(l_c)
            g_visit = np.random.poisson(l_v)
            
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
            
    # Classificação por grupo
    slot_values = {}
    terceiros_candidatos = []
    grupos_classificacao = {}
    
    for g in grupos_letras:
        times_grupo = df_grupos[df_grupos["group"] == g]["nation"].tolist()
        
        # Ordenar por: pontos -> saldo -> gols_pro -> random (todos descrescentes)
        times_grupo.sort(
            key=lambda t: (stats[t]["pontos"], stats[t]["saldo"], stats[t]["gols_pro"], stats[t]["random"]),
            reverse=True
        )
        
        slot_values[f"1{g}"] = times_grupo[0]
        slot_values[f"2{g}"] = times_grupo[1]
        
        t3 = times_grupo[2]
        terceiros_candidatos.append({
            "time": t3,
            "grupo": g,
            "pontos": stats[t3]["pontos"],
            "saldo": stats[t3]["saldo"],
            "gols_pro": stats[t3]["gols_pro"],
            "random": stats[t3]["random"]
        })
        
        # Construir tabela do grupo formatada em português
        grupo_table = []
        for pos, t in enumerate(times_grupo):
            grupo_table.append({
                "posicao": pos + 1,
                "selecao": t,
                "jogos": 3,
                "vitorias": int(stats[t]["vitorias"]),
                "empates": int(stats[t]["empates"]),
                "derrotas": int(stats[t]["derrotas"]),
                "gols_pro": int(stats[t]["gols_pro"]),
                "gols_contra": int(stats[t]["gols_contra"]),
                "saldo_gols": int(stats[t]["saldo"]),
                "pontos": int(stats[t]["pontos"])
            })
        grupos_classificacao[g] = pd.DataFrame(grupo_table)
        
    # Terceiros colocados
    terceiros_candidatos.sort(
        key=lambda x: (x["pontos"], x["saldo"], x["gols_pro"], x["random"]),
        reverse=True
    )
    
    melhores_terceiros = terceiros_candidatos[:8]
    map_terceiros = designar_terceiros(melhores_terceiros, slots_terceiros)
    slot_values.update(map_terceiros)
    
    # 2. Simular Fase de Mata-mata
    mata_mata = []
    
    # Converter resultados reais do mata-mata para busca por match_id
    real_mm = {}
    if not df_resultados_mata_mata.empty:
        real_mm = dict(zip(df_resultados_mata_mata["match_id"], df_resultados_mata_mata.to_dict("records")))
        
    for _, row in df_calendario.iterrows():
        m_id = row["match_id"]
        rodada = row["round"]
        h_slot = row["home_slot"]
        a_slot = row["away_slot"]
        
        time_h = slot_values[h_slot]
        time_a = slot_values[a_slot]
        
        # Se já tiver resultado real para este jogo de mata-mata no banco
        if m_id in real_mm:
            match_real = real_mm[m_id]
            time_h = match_real["home_team"]
            time_a = match_real["away_team"]
            g_h = int(match_real["gols_casa"])
            g_a = int(match_real["gols_visitante"])
            winner = match_real["vencedor"]
            penaltis_vencedor = match_real["penaltis_vencedor"]
            if pd.isna(penaltis_vencedor):
                penaltis_vencedor = None
        else:
            l_c, l_v = obter_lambdas(time_h, time_a, neutro=True, elo_times=elo_times, model_casa=model_casa, model_visit=model_visit, colunas_atributos=colunas_atributos)
            
            g_h = np.random.poisson(l_c)
            g_a = np.random.poisson(l_v)
            
            penaltis_vencedor = None
            
            if g_h > g_a:
                winner, loser = time_h, time_a
            elif g_h < g_a:
                winner, loser = time_a, time_h
            else:
                # Pênaltis
                if np.random.rand() < 0.5:
                    winner, loser = time_h, time_a
                    penaltis_vencedor = time_h
                else:
                    winner, loser = time_a, time_h
                    penaltis_vencedor = time_a
                    
        slot_values[f"W{m_id[1:]}"] = winner
        slot_values[f"RU{m_id[1:]}"] = time_a if winner == time_h else time_h
        
        mata_mata.append({
            "match_id": m_id,
            "round": rodada,
            "home_team": time_h,
            "away_team": time_a,
            "gols_casa": int(g_h),
            "gols_visitante": int(g_a),
            "vencedor": winner,
            "penaltis_vencedor": penaltis_vencedor
        })
        
    # Extrair pódio
    partida_3 = next(m for m in mata_mata if m["match_id"] == "M103")
    partida_f = next(m for m in mata_mata if m["match_id"] == "M104")
    
    podio = {
        "campeao": partida_f["vencedor"],
        "vice": partida_f["home_team"] if partida_f["vencedor"] == partida_f["away_team"] else partida_f["away_team"],
        "terceiro": partida_3["vencedor"],
        "quarto": partida_3["home_team"] if partida_3["vencedor"] == partida_3["away_team"] else partida_3["away_team"]
    }
    
    return {
        "podio": podio,
        "grupos_classificacao": grupos_classificacao,
        "mata_mata": mata_mata
    }

def main():
    load_dotenv()
    
    print("Carregando dados preparados a partir do Supabase...")
    preparado = preparar()
    
    elo_times = preparado["elo_times"]
    df_jogos_copa = preparado["df_jogos_copa"]
    df_grupos = preparado["df_grupos"]
    df_calendario = preparado["df_calendario"]
    df_resultados_mata_mata = preparado["df_resultados_mata_mata"]
    model_casa = preparado["model_casa"]
    model_visit = preparado["model_visit"]
    colunas_atributos = preparado["colunas_atributos"]
    
    grupos_letras = sorted(df_grupos["group"].unique()) # A a L
    selecoes_todas = df_grupos["nation"].unique()
    
    # Mapear seleções para a contagem de sucessos por fase
    contadores = {
        time: {"grupo": 0, "oitavas": 0, "quartas": 0, "semi": 0, "final": 0, "campea": 0}
        for time in selecoes_todas
    }
    
    # Definir parâmetros de simulação
    N = 1000
    seed = 42
    np.random.seed(seed)
    
    print(f"\nIniciando {N} simulações de Monte Carlo (seed={seed})...")
    
    # Converter resultados reais do mata-mata para busca rápida por match_id
    real_mm = {}
    if not df_resultados_mata_mata.empty:
        real_mm = dict(zip(df_resultados_mata_mata["match_id"], df_resultados_mata_mata.to_dict("records")))
        
    for sim in range(N):
        # Dicionário de estatísticas da rodada para cada seleção
        stats = {
            t: {"pontos": 0, "saldo": 0, "gols_pro": 0, "random": np.random.rand()}
            for t in selecoes_todas
        }
        
        # 1. Simular Fase de Grupos
        for _, row in df_jogos_copa.iterrows():
            t_casa = row["time_casa"]
            t_visit = row["time_visitante"]
            neutro = bool(row["neutro"])
            
            if pd.notna(row["gols_casa"]) and pd.notna(row["gols_visitante"]):
                g_casa = int(row["gols_casa"])
                g_visit = int(row["gols_visitante"])
            else:
                l_c, l_v = obter_lambdas(t_casa, t_visit, neutro, elo_times, model_casa, model_visit, colunas_atributos)
                g_casa = np.random.poisson(l_c)
                g_visit = np.random.poisson(l_v)
                
            stats[t_casa]["gols_pro"] += g_casa
            stats[t_casa]["saldo"] += (g_casa - g_visit)
            stats[t_visit]["gols_pro"] += g_visit
            stats[t_visit]["saldo"] += (g_visit - g_casa)
            
            if g_casa > g_visit:
                stats[t_casa]["pontos"] += 3
            elif g_casa == g_visit:
                stats[t_casa]["pontos"] += 1
                stats[t_visit]["pontos"] += 1
            else:
                stats[t_visit]["pontos"] += 3
                
        # Classificação por grupo
        slot_values = {}
        terceiros_candidatos = []
        
        for g in grupos_letras:
            times_grupo = df_grupos[df_grupos["group"] == g]["nation"].tolist()
            
            times_grupo.sort(
                key=lambda t: (stats[t]["pontos"], stats[t]["saldo"], stats[t]["gols_pro"], stats[t]["random"]),
                reverse=True
            )
            
            slot_values[f"1{g}"] = times_grupo[0]
            slot_values[f"2{g}"] = times_grupo[1]
            
            t3 = times_grupo[2]
            terceiros_candidatos.append({
                "time": t3,
                "grupo": g,
                "pontos": stats[t3]["pontos"],
                "saldo": stats[t3]["saldo"],
                "gols_pro": stats[t3]["gols_pro"],
                "random": stats[t3]["random"]
            })
            
        terceiros_candidatos.sort(
            key=lambda x: (x["pontos"], x["saldo"], x["gols_pro"], x["random"]),
            reverse=True
        )
        
        melhores_terceiros = terceiros_candidatos[:8]
        map_terceiros = designar_terceiros(melhores_terceiros, slots_terceiros)
        slot_values.update(map_terceiros)
        
        classificados_32 = [slot_values[f"1{g}"] for g in grupos_letras] + \
                           [slot_values[f"2{g}"] for g in grupos_letras] + \
                           [slot_values[s] for s in slots_terceiros]
                           
        for t in classificados_32:
            contadores[t]["grupo"] += 1
            
        # 2. Simular Fase de Mata-mata
        for _, row in df_calendario.iterrows():
            m_id = row["match_id"]
            rodada = row["round"]
            h_slot = row["home_slot"]
            a_slot = row["away_slot"]
            
            time_h = slot_values[h_slot]
            time_a = slot_values[a_slot]
            
            if m_id in real_mm:
                match_real = real_mm[m_id]
                time_h = match_real["home_team"]
                time_a = match_real["away_team"]
                g_h = int(match_real["gols_casa"])
                g_a = int(match_real["gols_visitante"])
                winner = match_real["vencedor"]
            else:
                l_c, l_v = obter_lambdas(time_h, time_a, neutro=True, elo_times=elo_times, model_casa=model_casa, model_visit=model_visit, colunas_atributos=colunas_atributos)
                
                g_h = np.random.poisson(l_c)
                g_a = np.random.poisson(l_v)
                
                if g_h > g_a:
                    winner, loser = time_h, time_a
                elif g_h < g_a:
                    winner, loser = time_a, time_h
                else:
                    if np.random.rand() < 0.5:
                        winner, loser = time_h, time_a
                    else:
                        winner, loser = time_a, time_h
                        
            slot_values[f"W{m_id[1:]}"] = winner
            slot_values[f"RU{m_id[1:]}"] = time_a if winner == time_h else time_h
            
            if rodada == "R32":
                contadores[winner]["oitavas"] += 1
            elif rodada == "R16":
                contadores[winner]["quartas"] += 1
            elif rodada == "QF":
                contadores[winner]["semi"] += 1
            elif rodada == "SF":
                contadores[winner]["final"] += 1
            elif rodada == "Final":
                contadores[winner]["campea"] += 1
                
    # 3. Converter contagens absolutas em probabilidades
    prob_list = []
    for t in selecoes_todas:
        prob_list.append({
            "selecao": t,
            "prob_grupo": contadores[t]["grupo"] / N,
            "prob_oitavas": contadores[t]["oitavas"] / N,
            "prob_quartas": contadores[t]["quartas"] / N,
            "prob_semi": contadores[t]["semi"] / N,
            "prob_final": contadores[t]["final"] / N,
            "prob_campea": contadores[t]["campea"] / N
        })
    df_prob = pd.DataFrame(prob_list)
    df_prob = df_prob.sort_values(by="prob_campea", ascending=False).reset_index(drop=True)
    
    # Imprimir favoritas
    print("\n" + "=" * 60)
    print(" FAVORITAS AO TÍTULO (MONTE CARLO) ".center(60))
    print("=" * 60)
    for idx, row in df_prob.head(10).iterrows():
        print(f"  {idx+1:>2}. {row['selecao']:<20} | Semis: {row['prob_semi']*100:>5.1f}% | Final: {row['prob_final']*100:>5.1f}% | Campeã: {row['prob_campea']*100:>5.1f}%")
    print("=" * 60 + "\n")
    
    # 4. Gravação no banco de dados
    print("Conectando ao banco de dados para gravação...")
    conn = get_raw_connection()
    try:
        with conn.cursor() as cur:
            print("Removendo tabela gold_probabilidades_copa anterior...")
            cur.execute("DROP TABLE IF EXISTS gold_probabilidades_copa CASCADE;")
            
            print("Criando tabela gold_probabilidades_copa...")
            cur.execute("""
                CREATE TABLE gold_probabilidades_copa (
                    id bigint generated always as identity primary key,
                    selecao text NOT NULL UNIQUE,
                    prob_grupo double precision NOT NULL,
                    prob_oitavas double precision NOT NULL,
                    prob_quartas double precision NOT NULL,
                    prob_semi double precision NOT NULL,
                    prob_final double precision NOT NULL,
                    prob_campea double precision NOT NULL
                );
                ALTER TABLE gold_probabilidades_copa ENABLE ROW LEVEL SECURITY;
            """)
            
            print("Preparando buffer e executando COPY para gold_probabilidades_copa...")
            buf = io.StringIO()
            df_prob.to_csv(buf, index=False, header=False, na_rep="")
            buf.seek(0)
            
            cur.copy_expert("""
                COPY gold_probabilidades_copa (
                    selecao, prob_grupo, prob_oitavas, prob_quartas, prob_semi, prob_final, prob_campea
                ) FROM STDIN WITH CSV NULL ''
            """, buf)
            
        conn.commit()
        print("Tabela gold_probabilidades_copa atualizada com sucesso no Supabase!")
        
    except Exception as e:
        conn.rollback()
        print(f"Erro ao gravar probabilidades no banco: {e}")
        sys.exit(1)
    finally:
        conn.close()

if __name__ == "__main__":
    main()
