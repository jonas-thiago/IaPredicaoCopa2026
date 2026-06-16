import os
import sys
import pickle
import pandas as pd
import numpy as np
import statsmodels.api as sm
from dotenv import load_dotenv

# Garantir que o diretório src/ esteja no path para importações flat
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from db import get_engine, get_raw_connection
from poisson import calcular_probabilidades_resultado, obter_resultado_real

def main():
    load_dotenv()
    
    print("Conectando ao banco de dados para leitura de gold_atributos...")
    engine = get_engine()
    
    try:
        df = pd.read_sql("SELECT * FROM gold_atributos ORDER BY data ASC, id ASC", engine)
    except Exception as e:
        print(f"Erro ao ler tabela gold_atributos: {e}")
        sys.exit(1)
        
    print(f"Total de registros lidos: {len(df)}")
    
    # Garantir parsing de data
    df["data"] = pd.to_datetime(df["data"])
    
    # 1. Split Temporal
    df_train = df[df["data"] < "2024-01-01"].copy()
    df_test = df[df["data"] >= "2024-01-01"].copy()
    
    print(f"Dados de treino (< 2024): {len(df_train)} jogos")
    print(f"Dados de teste  (>= 2024): {len(df_test)} jogos")
    
    # 2. Definição das colunas de atributos de treino
    colunas_atributos = ["elo_casa", "elo_visitante", "dif_elo", "neutro", "peso_torneio", "peso_recencia"]
    
    # Função auxiliar para preparar as matrizes de features (com constante e tratamento de boolean)
    def preparar_features(dataframe):
        X = dataframe[colunas_atributos].copy()
        X["neutro"] = X["neutro"].astype(int)
        X = sm.add_constant(X, has_constant="add")
        return X
        
    X_train = preparar_features(df_train)
    y_train_casa = df_train["gols_casa"].astype(float)
    y_train_visit = df_train["gols_visitante"].astype(float)
    
    # Pesos amostrais: peso_torneio * peso_recencia
    weights_train = df_train["peso_torneio"] * df_train["peso_recencia"]
    
    # 3. Treinamento dos modelos de Poisson
    print("Treinando modelo de gols para time da CASA...")
    model_casa = sm.GLM(
        y_train_casa, 
        X_train, 
        family=sm.families.Poisson(), 
        var_weights=weights_train
    ).fit()
    
    print("Treinando modelo de gols para time VISITANTE...")
    model_visit = sm.GLM(
        y_train_visit, 
        X_train, 
        family=sm.families.Poisson(), 
        var_weights=weights_train
    ).fit()
    
    # 4. Validação no conjunto de teste
    print("Validando modelos no conjunto de teste...")
    X_test = preparar_features(df_test)
    y_test_casa = df_test["gols_casa"].astype(float)
    y_test_visit = df_test["gols_visitante"].astype(float)
    
    # Predições de gols esperados (lambdas)
    lambda_casa = model_casa.predict(X_test)
    lambda_visit = model_visit.predict(X_test)
    
    # Calcular MAE
    mae_casa = np.mean(np.abs(lambda_casa - y_test_casa))
    mae_visitante = np.mean(np.abs(lambda_visit - y_test_visit))
    
    # Calcular Acurácia de Resultado
    resultados_corretos = 0
    labels = ["V", "E", "D"]
    
    for idx in range(len(df_test)):
        l_c = lambda_casa.iloc[idx]
        l_v = lambda_visit.iloc[idx]
        
        # Calcular probabilidades V/E/D
        p_v, p_e, p_d = calcular_probabilidades_resultado(l_c, l_v)
        outcome_pred = labels[np.argmax([p_v, p_e, p_d])]
        
        # Resultado real
        g_c = y_test_casa.iloc[idx]
        g_v = y_test_visit.iloc[idx]
        outcome_real = obter_resultado_real(g_c, g_v)
        
        if outcome_pred == outcome_real:
            resultados_corretos += 1
            
    acuracia = resultados_corretos / len(df_test)
    
    # Imprimir inventário e métricas
    print("\n" + "=" * 60)
    print(" MÉTRICAS DE VALIDAÇÃO DO MODELO POISSON ".center(60))
    print("=" * 60)
    print(f"MAE Casa:       {mae_casa:.4f}")
    print(f"MAE Visitante:  {mae_visitante:.4f}")
    print(f"Acurácia:       {acuracia:.4f} ({acuracia*100:.2f}%)")
    print("=" * 60 + "\n")
    
    # 5. Salvar artefatos (.pkl)
    os.makedirs("models", exist_ok=True)
    
    print("Salvando modelos e atributos em models/...")
    with open("models/modelo_poisson_casa.pkl", "wb") as f:
        pickle.dump(model_casa, f)
    with open("models/modelo_poisson_visitante.pkl", "wb") as f:
        pickle.dump(model_visit, f)
    with open("models/colunas_atributos.pkl", "wb") as f:
        pickle.dump(colunas_atributos, f)
        
    print("Artefatos salvos com sucesso!")
    
    # 6. Gravação das métricas no banco
    print("Gravando métricas no banco de dados...")
    conn = get_raw_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("DROP TABLE IF EXISTS metricas_validacao CASCADE;")
            cur.execute("""
                CREATE TABLE metricas_validacao (
                    id bigint generated always as identity primary key,
                    mae_casa double precision NOT NULL,
                    mae_visitante double precision NOT NULL,
                    acuracia double precision NOT NULL
                );
                ALTER TABLE metricas_validacao ENABLE ROW LEVEL SECURITY;
            """)
            cur.execute("""
                INSERT INTO metricas_validacao (mae_casa, mae_visitante, acuracia)
                VALUES (%s, %s, %s);
            """, (float(mae_casa), float(mae_visitante), float(acuracia)))
        conn.commit()
        print("Tabela metricas_validacao carregada com sucesso!")
    except Exception as e:
        conn.rollback()
        print(f"Erro ao gravar métricas de validação: {e}")
        sys.exit(1)
    finally:
        conn.close()

if __name__ == "__main__":
    main()
