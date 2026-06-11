import os
import sys
import io
import pandas as pd
from dotenv import load_dotenv

# Garantir que o diretório src/ esteja no path para importações flat
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from db import get_engine, get_raw_connection

# Parâmetros canônicos
DATA_REF = pd.to_datetime("2026-06-11")
MEIA_VIDA_ANOS = 5.0

NIVEL3 = {'FIFA World Cup', 'Confederations Cup', 'CONMEBOL–UEFA Cup of Champions'}
CONTINENTAIS = {'UEFA Euro', 'Copa América', 'African Cup of Nations', 'AFC Asian Cup', 'Gold Cup', 'Oceania Nations Cup'}

def classificar_torneio(torneio):
    if torneio in NIVEL3:
        return 3
    torneio_lower = torneio.lower()
    if "qualification" in torneio_lower or "nations league" in torneio_lower or torneio in CONTINENTAIS:
        return 2
    return 1

def main():
    load_dotenv()
    
    print("Conectando ao banco de dados para leitura da camada Silver...")
    engine = get_engine()
    
    # Ler silver_jogos
    try:
        df = pd.read_sql("SELECT data, time_casa, time_visitante, gols_casa, gols_visitante, torneio, cidade, pais, neutro, eh_amistoso FROM silver_jogos", engine)
    except Exception as e:
        print(f"Erro ao ler tabela silver_jogos: {e}")
        sys.exit(1)
        
    print(f"Total de registros lidos: {len(df)}")
    
    # Conversões explícitas de tipos após leitura
    df["data"] = pd.to_datetime(df["data"])
    df["gols_casa"] = df["gols_casa"].astype("int64")
    df["gols_visitante"] = df["gols_visitante"].astype("int64")
    df["neutro"] = df["neutro"].astype(bool)
    df["eh_amistoso"] = df["eh_amistoso"].astype(bool)
    
    # 1. Calcular peso_torneio
    df["peso_torneio"] = df["torneio"].apply(classificar_torneio)
    
    # 2. Calcular peso_recencia
    # idade_anos = (DATA_REF - data_jogo).days / 365.25
    df["idade_anos"] = (DATA_REF - df["data"]).dt.days / 365.25
    df["peso_recencia"] = 0.5 ** (df["idade_anos"] / MEIA_VIDA_ANOS)
    
    # Formatar data de volta para string
    df["data"] = df["data"].dt.strftime("%Y-%m-%d")
    
    # Selecionar e ordenar colunas finais
    colunas_finais = [
        "data", "time_casa", "time_visitante", "gols_casa", "gols_visitante", 
        "torneio", "cidade", "pais", "neutro", "eh_amistoso", "peso_torneio", "peso_recencia"
    ]
    df_ponderado = df[colunas_finais].copy()
    
    # Imprimir inventário dos pesos
    print("\n" + "=" * 60)
    print(" INVENTÁRIO DA TABELA SILVER_PONDERADO ".center(60))
    print("=" * 60)
    print(f"Total de linhas processadas: {len(df_ponderado)}")
    print("-" * 60)
    print("Distribuição de peso_torneio:")
    for nivel in [1, 2, 3]:
        qtd = (df_ponderado["peso_torneio"] == nivel).sum()
        pct = (qtd / len(df_ponderado)) * 100
        print(f"  Nível {nivel}: {qtd:<6} ({pct:.2f}%)")
        
    print("-" * 60)
    print("Estatísticas de peso_recencia:")
    min_rec = df_ponderado["peso_recencia"].min()
    max_rec = df_ponderado["peso_recencia"].max()
    avg_rec = df_ponderado["peso_recencia"].mean()
    print(f"  Mínimo: {min_rec:.6f}")
    print(f"  Máximo: {max_rec:.6f}")
    print(f"  Média:  {avg_rec:.6f}")
    print("=" * 60 + "\n")
    
    # Gravação idempotente no banco de dados
    print("Conectando ao banco de dados para gravação...")
    conn = get_raw_connection()
    try:
        with conn.cursor() as cur:
            print("Removendo tabela silver_ponderado anterior (se existir)...")
            cur.execute("DROP TABLE IF EXISTS silver_ponderado CASCADE;")
            
            print("Criando tabela silver_ponderado...")
            cur.execute("""
                CREATE TABLE silver_ponderado (
                    id bigint generated always as identity primary key,
                    data date NOT NULL,
                    time_casa text NOT NULL,
                    time_visitante text NOT NULL,
                    gols_casa integer NOT NULL,
                    gols_visitante integer NOT NULL,
                    torneio text NOT NULL,
                    cidade text NOT NULL,
                    pais text NOT NULL,
                    neutro boolean NOT NULL,
                    eh_amistoso boolean NOT NULL,
                    peso_torneio integer NOT NULL,
                    peso_recencia double precision NOT NULL
                );
            """)
            
            print("Preparando buffer CSV em memória...")
            output_buffer = io.StringIO()
            df_ponderado.to_csv(output_buffer, index=False, header=False, na_rep="")
            output_buffer.seek(0)
            
            print("Executando COPY para carga em massa...")
            cur.copy_expert("""
                COPY silver_ponderado (
                    data, time_casa, time_visitante, gols_casa, gols_visitante, 
                    torneio, cidade, pais, neutro, eh_amistoso, peso_torneio, peso_recencia
                ) FROM STDIN WITH CSV NULL ''
            """, output_buffer)
            
        conn.commit()
        print("Tabela silver_ponderado carregada com sucesso!")
        
    except Exception as e:
        conn.rollback()
        print(f"Erro ao gravar tabela silver_ponderado: {e}")
        sys.exit(1)
    finally:
        conn.close()

if __name__ == "__main__":
    main()
