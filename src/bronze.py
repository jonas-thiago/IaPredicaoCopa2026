import os
import sys
import io
import pandas as pd
from dotenv import load_dotenv

# Garantir que o diretório src/ esteja no path para importações flat
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from db import get_raw_connection

def main():
    # Carregar variáveis de ambiente
    load_dotenv()
    
    caminho_csv = os.getenv("CAMINHO_CSV", "data/results.csv")
    print(f"Lendo o CSV a partir de: {caminho_csv}")
    
    if not os.path.exists(caminho_csv):
        print(f"Erro: O arquivo {caminho_csv} não foi encontrado.")
        sys.exit(1)
        
    # Ler o CSV tratando datas
    df = pd.read_csv(caminho_csv, parse_dates=["date"])
    
    # Conversão de tipos
    # Converter home_score e away_score para inteiro nullable ('Int64') para tratar os "NA" corretamente como NULL
    df["home_score"] = pd.to_numeric(df["home_score"].replace("NA", pd.NA), errors="coerce").astype("Int64")
    df["away_score"] = pd.to_numeric(df["away_score"].replace("NA", pd.NA), errors="coerce").astype("Int64")
    df["neutral"] = df["neutral"].astype(bool)
    
    # Dicionário de renomeação de colunas do prd.md
    colunas_map = {
        "date": "data",
        "home_team": "time_casa",
        "away_team": "time_visitante",
        "home_score": "gols_casa",
        "away_score": "gols_visitante",
        "tournament": "torneio",
        "city": "cidade",
        "country": "pais",
        "neutral": "neutro"
    }
    df = df.rename(columns=colunas_map)
    
    # Manter apenas as colunas mapeadas e na ordem correta
    colunas_finais = ["data", "time_casa", "time_visitante", "gols_casa", "gols_visitante", "torneio", "cidade", "pais", "neutro"]
    df = df[colunas_finais]
    
    # Gerar e imprimir o inventário
    print("\n" + "=" * 60)
    print(" INVENTÁRIO DA TABELA BRONZE (bronze_jogos)".center(60))
    print("=" * 60)
    print(f"Total de linhas lidas: {len(df)}")
    print("-" * 60)
    print(f"{'Coluna':<18} | {'Tipo Pandas':<12} | {'Nulos':<6} | {'% Nulos':<8}")
    print("-" * 60)
    for col in df.columns:
        nulos = df[col].isna().sum()
        pct_nulos = (nulos / len(df)) * 100
        tipo = str(df[col].dtype)
        print(f"{col:<18} | {tipo:<12} | {nulos:<6} | {pct_nulos:>6.2f}%")
    print("=" * 60 + "\n")
    
    # Gravação idempotente no banco de dados
    print("Conectando ao banco de dados...")
    conn = get_raw_connection()
    try:
        with conn.cursor() as cur:
            # Drop e Create da tabela
            print("Removendo tabela bronze_jogos anterior (se existir)...")
            cur.execute("DROP TABLE IF EXISTS bronze_jogos CASCADE;")
            
            print("Criando tabela bronze_jogos...")
            cur.execute("""
                CREATE TABLE bronze_jogos (
                    id bigint generated always as identity primary key,
                    data date NOT NULL,
                    time_casa text NOT NULL,
                    time_visitante text NOT NULL,
                    gols_casa integer,
                    gols_visitante integer,
                    torneio text NOT NULL,
                    cidade text NOT NULL,
                    pais text NOT NULL,
                    neutro boolean NOT NULL
                );
                ALTER TABLE bronze_jogos ENABLE ROW LEVEL SECURITY;
            """)
            
            # Carga em massa usando COPY a partir de um buffer em memória
            print("Preparando buffer CSV em memória...")
            output_buffer = io.StringIO()
            # pandas.to_csv grava booleans como True/False, e na_rep como ''
            df.to_csv(output_buffer, index=False, header=False, na_rep="")
            output_buffer.seek(0)
            
            print("Executando COPY para carga em massa...")
            cur.copy_expert("""
                COPY bronze_jogos (
                    data, time_casa, time_visitante, gols_casa, gols_visitante, torneio, cidade, pais, neutro
                ) FROM STDIN WITH CSV NULL ''
            """, output_buffer)
            
        conn.commit()
        print("Carga concluída e transação confirmada com sucesso!")
        
    except Exception as e:
        conn.rollback()
        print(f"Erro durante a carga no banco: {e}")
        sys.exit(1)
    finally:
        conn.close()

if __name__ == "__main__":
    main()
