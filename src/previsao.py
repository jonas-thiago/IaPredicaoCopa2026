import os
import sys
import pickle
import io
import pandas as pd
import numpy as np
import statsmodels.api as sm
from dotenv import load_dotenv

# Garantir que o diretório src/ esteja no path para importações flat
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from db import get_engine, get_raw_connection
from poisson import calcular_probabilidades_resultado

# Data de referência canônica
DATA_REF = pd.to_datetime("2026-06-11")

def prever_jogo(time_casa, time_visitante, neutro, peso_torneio, elo_times, model_casa, model_visit, colunas_atributos):
    """
    Prediz o resultado probabilístico de um jogo com base no ELO das seleções e nos modelos de Poisson.
    Retorna (gols_casa_esp, gols_visit_esp, prob_vitoria, prob_empate, prob_derrota).
    """
    # ELOs pré-jogo das seleções (default 1500)
    elo_casa = elo_times.get(time_casa, 1500.0)
    elo_visitante = elo_times.get(time_visitante, 1500.0)
    dif_elo = elo_casa - elo_visitante
    
    # Montar linha de features (peso_recencia = 1.0 para previsões no presente)
    df_row = pd.DataFrame([{
        "elo_casa": float(elo_casa),
        "elo_visitante": float(elo_visitante),
        "dif_elo": float(dif_elo),
        "neutro": int(neutro),
        "peso_torneio": int(peso_torneio),
        "peso_recencia": 1.0
    }])
    
    # Adicionar constante e ordenar as colunas conforme colunas_atributos + const
    X_row = sm.add_constant(df_row, has_constant="add")
    colunas_com_constante = ["const"] + colunas_atributos
    X_row = X_row[colunas_com_constante]
    
    # Obter gols esperados (lambdas)
    lambda_casa = float(model_casa.predict(X_row).iloc[0])
    lambda_visit = float(model_visit.predict(X_row).iloc[0])
    
    # Calcular probabilidades de resultado (V/E/D)
    prob_v, prob_e, prob_d = calcular_probabilidades_resultado(lambda_casa, lambda_visit)
    
    return lambda_casa, lambda_visit, prob_v, prob_e, prob_d

def main():
    load_dotenv()
    
    print("Carregando modelos e colunas de atributos...")
    try:
        with open("models/modelo_poisson_casa.pkl", "rb") as f:
            model_casa = pickle.load(f)
        with open("models/modelo_poisson_visitante.pkl", "rb") as f:
            model_visit = pickle.load(f)
        with open("models/colunas_atributos.pkl", "rb") as f:
            colunas_atributos = pickle.load(f)
    except Exception as e:
        print(f"Erro ao carregar arquivos pickle: {e}")
        sys.exit(1)
        
    engine = get_engine()
    
    # Carregar ELOs atuais
    print("Carregando ELOs atuais das seleções...")
    try:
        df_elo = pd.read_sql("SELECT selecao, elo FROM silver_elo_atual", engine)
    except Exception as e:
        print(f"Erro ao ler tabela silver_elo_atual: {e}")
        sys.exit(1)
    elo_times = dict(zip(df_elo["selecao"], df_elo["elo"]))
    
    # Carregar jogos futuros da Copa de 2026
    print("Carregando jogos futuros da Copa de 2026...")
    try:
        df_copa = pd.read_sql("SELECT data, time_casa, time_visitante, neutro FROM silver_copa2026 ORDER BY data, time_casa", engine)
    except Exception as e:
        print(f"Erro ao ler tabela silver_copa2026: {e}")
        sys.exit(1)
        
    # 1. Gerar previsões para os 72 jogos
    print(f"Gerando previsões para os {len(df_copa)} jogos da fase de grupos da Copa...")
    previsoes_list = []
    for _, row in df_copa.iterrows():
        t_casa = row["time_casa"]
        t_visit = row["time_visitante"]
        neutro = bool(row["neutro"])
        
        l_c, l_v, p_v, p_e, p_d = prever_jogo(
            t_casa, t_visit, neutro, peso_torneio=3, 
            elo_times=elo_times, model_casa=model_casa, model_visit=model_visit, 
            colunas_atributos=colunas_atributos
        )
        
        previsoes_list.append({
            "time_casa": t_casa,
            "time_visitante": t_visit,
            "gols_esperados_casa": l_c,
            "gols_esperados_visitante": l_v,
            "prob_vitoria": p_v,
            "prob_empate": p_e,
            "prob_derrota": p_d
        })
    df_previsoes = pd.DataFrame(previsoes_list)
    
    # 2. Rodar Experimentos de Ponderação (MAE)
    print("Lendo gold_atributos para rodar os experimentos...")
    try:
        df_gold = pd.read_sql("SELECT * FROM gold_atributos ORDER BY data, id", engine)
    except Exception as e:
        print(f"Erro ao ler gold_atributos: {e}")
        sys.exit(1)
        
    df_gold["data"] = pd.to_datetime(df_gold["data"])
    
    # Split temporal idêntico ao de treino/validação
    df_train_raw = df_gold[df_gold["data"] < "2024-01-01"].copy()
    df_test_raw = df_gold[df_gold["data"] >= "2024-01-01"].copy()
    
    configs_experimento = [
        {"name": "sem_recencia", "meia_vida": None},
        {"name": "meia_vida_3", "meia_vida": 3.0},
        {"name": "meia_vida_5", "meia_vida": 5.0},
        {"name": "meia_vida_10", "meia_vida": 10.0}
    ]
    
    experimentos_list = []
    
    for config in configs_experimento:
        name = config["name"]
        mv = config["meia_vida"]
        print(f"Rodando experimento: {name}...")
        
        # Copiar dados
        df_tr = df_train_raw.copy()
        df_te = df_test_raw.copy()
        
        # Recalcular peso_recencia
        if mv is None:
            df_tr["peso_recencia"] = 1.0
            df_te["peso_recencia"] = 1.0
        else:
            # idade_anos = (DATA_REF - data).days / 365.25
            idade_tr = (DATA_REF - df_tr["data"]).dt.days / 365.25
            idade_te = (DATA_REF - df_te["data"]).dt.days / 365.25
            df_tr["peso_recencia"] = 0.5 ** (idade_tr / mv)
            df_te["peso_recencia"] = 0.5 ** (idade_te / mv)
            
        # Preparar matrizes de features
        def prep_features(dataframe):
            X = dataframe[colunas_atributos].copy()
            X["neutro"] = X["neutro"].astype(int)
            X = sm.add_constant(X, has_constant="add")
            # ordenar colunas
            X = X[["const"] + colunas_atributos]
            return X
            
        X_tr = prep_features(df_tr)
        X_te = prep_features(df_te)
        
        y_tr_casa = df_tr["gols_casa"].astype(float)
        y_tr_visit = df_tr["gols_visitante"].astype(float)
        
        y_te_casa = df_te["gols_casa"].astype(float)
        y_te_visit = df_te["gols_visitante"].astype(float)
        
        # Pesos amostrais
        weights_tr = df_tr["peso_torneio"] * df_tr["peso_recencia"]
        
        # Treinar modelos
        m_casa = sm.GLM(y_tr_casa, X_tr, family=sm.families.Poisson(), var_weights=weights_tr).fit()
        m_visit = sm.GLM(y_tr_visit, X_tr, family=sm.families.Poisson(), var_weights=weights_tr).fit()
        
        # Predições e MAE no teste
        pred_c = m_casa.predict(X_te)
        pred_v = m_visit.predict(X_te)
        
        mae_c = float(np.mean(np.abs(pred_c - y_te_casa)))
        mae_v = float(np.mean(np.abs(pred_v - y_te_visit)))
        
        experimentos_list.append({
            "config": name,
            "mae_casa": mae_c,
            "mae_visitante": mae_v
        })
        
    df_experimentos = pd.DataFrame(experimentos_list)
    
    # Ordenar experimentos pelo MAE da casa
    df_experimentos = df_experimentos.sort_values(by="mae_casa").reset_index(drop=True)
    
    # Imprimir inventário final
    print("\n" + "=" * 60)
    print(" INVENTÁRIO DE PREVISÕES E EXPERIMENTOS ".center(60))
    print("=" * 60)
    print("Resultados dos Experimentos de Recência (Ordenado por MAE Casa):")
    for idx, row in df_experimentos.iterrows():
        print(f"  {row['config']:<15} | MAE Casa: {row['mae_casa']:.4f} | MAE Visitante: {row['mae_visitante']:.4f}")
    print("-" * 60)
    
    # Amostra das previsões (Top 3 maiores probabilidades de vitória de algum time)
    df_previsoes["prob_max"] = df_previsoes[["prob_vitoria", "prob_derrota"]].max(axis=1)
    df_favoritos = df_previsoes.sort_values(by="prob_max", ascending=False).head(3)
    print("Amostra de Previsões com Maiores Favoritismos:")
    for _, row in df_favoritos.iterrows():
        favorito = row["time_casa"] if row["prob_vitoria"] > row["prob_derrota"] else row["time_visitante"]
        azarão = row["time_visitante"] if row["prob_vitoria"] > row["prob_derrota"] else row["time_casa"]
        prob = row["prob_max"] * 100
        print(f"  {favorito} é favorito contra {azarão} ({prob:.1f}%)")
    print("=" * 60 + "\n")
    
    # Gravação no banco
    print("Conectando ao banco de dados para gravação...")
    conn = get_raw_connection()
    try:
        with conn.cursor() as cur:
            # 1. Tabela previsoes
            print("Removendo tabela previsoes anterior...")
            cur.execute("DROP TABLE IF EXISTS previsoes CASCADE;")
            print("Criando tabela previsoes...")
            cur.execute("""
                CREATE TABLE previsoes (
                    id bigint generated always as identity primary key,
                    time_casa text NOT NULL,
                    time_visitante text NOT NULL,
                    gols_esperados_casa double precision NOT NULL,
                    gols_esperados_visitante double precision NOT NULL,
                    prob_vitoria double precision NOT NULL,
                    prob_empate double precision NOT NULL,
                    prob_derrota double precision NOT NULL
                );
                ALTER TABLE previsoes ENABLE ROW LEVEL SECURITY;
            """)
            print("Preparando buffer e executando COPY para previsoes...")
            buf_prev = io.StringIO()
            # Remover coluna de suporte antes de salvar
            df_previsoes_salvar = df_previsoes.drop(columns=["prob_max"])
            df_previsoes_salvar.to_csv(buf_prev, index=False, header=False, na_rep="")
            buf_prev.seek(0)
            cur.copy_expert("""
                COPY previsoes (
                    time_casa, time_visitante, gols_esperados_casa, gols_esperados_visitante, 
                    prob_vitoria, prob_empate, prob_derrota
                ) FROM STDIN WITH CSV NULL ''
            """, buf_prev)
            
            # 2. Tabela experimentos_mae
            print("Removendo tabela experimentos_mae anterior...")
            cur.execute("DROP TABLE IF EXISTS experimentos_mae CASCADE;")
            print("Criando tabela experimentos_mae...")
            cur.execute("""
                CREATE TABLE experimentos_mae (
                    id bigint generated always as identity primary key,
                    config text NOT NULL,
                    mae_casa double precision NOT NULL,
                    mae_visitante double precision NOT NULL
                );
                ALTER TABLE experimentos_mae ENABLE ROW LEVEL SECURITY;
            """)
            print("Preparando buffer e executando COPY para experimentos_mae...")
            buf_exp = io.StringIO()
            df_experimentos.to_csv(buf_exp, index=False, header=False, na_rep="")
            buf_exp.seek(0)
            cur.copy_expert("""
                COPY experimentos_mae (
                    config, mae_casa, mae_visitante
                ) FROM STDIN WITH CSV NULL ''
            """, buf_exp)
            
        conn.commit()
        print("Tabelas de previsoes e experimentos_mae gravadas com sucesso!")
        
    except Exception as e:
        conn.rollback()
        print(f"Erro ao gravar previsões e experimentos no banco: {e}")
        sys.exit(1)
    finally:
        conn.close()

if __name__ == "__main__":
    main()
