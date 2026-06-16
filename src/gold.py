import os
import sys
import io
import pandas as pd
from dotenv import load_dotenv

# Garantir que o diretório src/ esteja no path para importações flat
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from db import get_engine, get_raw_connection

def main():
    load_dotenv()
    
    print("Conectando ao banco de dados para consulta e junção das tabelas Silver...")
    engine = get_engine()
    
    query = """
        SELECT 
            s.id AS jogo_id,
            s.data,
            s.time_casa,
            s.time_visitante,
            e.elo_casa,
            e.elo_visitante,
            s.neutro,
            s.peso_torneio,
            s.peso_recencia,
            s.gols_casa,
            s.gols_visitante
        FROM silver_ponderado s
        JOIN silver_elo_pre_jogo e ON e.jogo_id = s.id
        WHERE NOT s.eh_amistoso
        ORDER BY s.data ASC, s.id ASC
    """
    
    try:
        df = pd.read_sql(query, engine)
    except Exception as e:
        print(f"Erro ao executar a junção SQL: {e}")
        sys.exit(1)
        
    print(f"Total de registros lidos (não-amistosos): {len(df)}")
    
    # 1. Calcular dif_elo
    df["dif_elo"] = df["elo_casa"] - df["elo_visitante"]
    
    # Ajustar tipos
    df["jogo_id"] = df["jogo_id"].astype("int64")
    df["data"] = pd.to_datetime(df["data"])
    df["neutro"] = df["neutro"].astype(bool)
    df["peso_torneio"] = df["peso_torneio"].astype(int)
    df["gols_casa"] = df["gols_casa"].astype(int)
    df["gols_visitante"] = df["gols_visitante"].astype(int)
    
    # 2. Assegurar que não há nulos nas colunas de atributos de treino
    atributos_treino = [
        "elo_casa", "elo_visitante", "dif_elo", "neutro", 
        "peso_torneio", "peso_recencia", "gols_casa", "gols_visitante"
    ]
    for col in atributos_treino:
        assert df[col].notna().all(), f"Erro crítico: Valores nulos encontrados na coluna de atributo '{col}'!"
        
    print("Asserções de integridade contra nulos concluídas com sucesso (0 nulos detectados).")
    
    # Formatar data de volta para string para a gravação limpa no COPY
    df["data"] = df["data"].dt.strftime("%Y-%m-%d")
    
    # Colunas finais ordenadas do dataset Gold
    colunas_finais = [
        "jogo_id", "data", "time_casa", "time_visitante", 
        "elo_casa", "elo_visitante", "dif_elo", "neutro", 
        "peso_torneio", "peso_recencia", "gols_casa", "gols_visitante"
    ]
    df_gold = df[colunas_finais].copy()
    
    # Imprimir inventário gold
    print("\n" + "=" * 60)
    print(" INVENTÁRIO DA TABELA GOLD_ATRIBUTOS ".center(60))
    print("=" * 60)
    print(f"Total de jogos de treino (oficiais): {len(df_gold)}")
    print("-" * 60)
    print("Estatísticas gerais de ELO:")
    print(f"  Média ELO Casa:      {df_gold['elo_casa'].mean():.2f}")
    print(f"  Média ELO Visitante: {df_gold['elo_visitante'].mean():.2f}")
    print(f"  Média dif_elo:       {df_gold['dif_elo'].mean():.2f}")
    print(f"  Máxima dif_elo:      {df_gold['dif_elo'].max():.2f}")
    print(f"  Mínima dif_elo:      {df_gold['dif_elo'].min():.2f}")
    print("-" * 60)
    print("Distribuição por Peso de Torneio:")
    for nivel in [1, 2, 3]:
        qtd = (df_gold["peso_torneio"] == nivel).sum()
        pct = (qtd / len(df_gold)) * 100
        print(f"  Nível {nivel}: {qtd:<6} ({pct:.2f}%)")
    print("-" * 60)
    print(f"Jogos em campo neutro: {(df_gold['neutro'] == True).sum()} ({(df_gold['neutro'] == True).sum() / len(df_gold) * 100:.2f}%)")
    print("=" * 60 + "\n")
    
    # Gravação idempotente
    print("Conectando ao banco de dados para gravação...")
    conn = get_raw_connection()
    try:
        with conn.cursor() as cur:
            print("Removendo tabela gold_atributos anterior (se existir)...")
            cur.execute("DROP TABLE IF EXISTS gold_atributos CASCADE;")
            
            print("Criando tabela gold_atributos...")
            cur.execute("""
                CREATE TABLE gold_atributos (
                    id bigint generated always as identity primary key,
                    jogo_id bigint NOT NULL,
                    data date NOT NULL,
                    time_casa text NOT NULL,
                    time_visitante text NOT NULL,
                    elo_casa double precision NOT NULL,
                    elo_visitante double precision NOT NULL,
                    dif_elo double precision NOT NULL,
                    neutro boolean NOT NULL,
                    peso_torneio integer NOT NULL,
                    peso_recencia double precision NOT NULL,
                    gols_casa integer NOT NULL,
                    gols_visitante integer NOT NULL
                );
                ALTER TABLE gold_atributos ENABLE ROW LEVEL SECURITY;
            """)
            
            print("Preparando buffer e executando COPY para gold_atributos...")
            output_buffer = io.StringIO()
            df_gold.to_csv(output_buffer, index=False, header=False, na_rep="")
            output_buffer.seek(0)
            
            cur.copy_expert("""
                COPY gold_atributos (
                    jogo_id, data, time_casa, time_visitante, elo_casa, elo_visitante, 
                    dif_elo, neutro, peso_torneio, peso_recencia, gols_casa, gols_visitante
                ) FROM STDIN WITH CSV NULL ''
            """, output_buffer)
            
        conn.commit()
        print("Tabela gold_atributos carregada com sucesso!")
        
    except Exception as e:
        conn.rollback()
        print(f"Erro ao gravar tabela gold_atributos: {e}")
        sys.exit(1)
    finally:
        conn.close()

if __name__ == "__main__":
    main()
