import os
import sys
import io
import pandas as pd
from dotenv import load_dotenv

# Garantir que o diretório src/ esteja no path para importações flat
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from db import get_engine, get_raw_connection

# Dicionário de mapeamento para normalizar nomes de seleções (mantendo-os em inglês)
# Inicialmente vazio, pois os dados do Kaggle já são bem consistentes, mas pronto para extensões
DICIONARIO_SELECOES = {
    # Exemplo: "Côte d'Ivoire": "Ivory Coast" (já vem como Ivory Coast no results.csv)
}

def limpar_nome(nome):
    if pd.isna(nome):
        return nome
    nome_limpo = str(nome).strip()
    return DICIONARIO_SELECOES.get(nome_limpo, nome_limpo)

def criar_tabela_silver(cur, nome_tabela):
    print(f"Recriando tabela {nome_tabela}...")
    cur.execute(f"DROP TABLE IF EXISTS {nome_tabela} CASCADE;")
    cur.execute(f"""
        CREATE TABLE {nome_tabela} (
            id bigint generated always as identity primary key,
            data date NOT NULL,
            time_casa text NOT NULL,
            time_visitante text NOT NULL,
            gols_casa integer,
            gols_visitante integer,
            torneio text NOT NULL,
            cidade text NOT NULL,
            pais text NOT NULL,
            neutro boolean NOT NULL,
            eh_amistoso boolean NOT NULL
        );
        ALTER TABLE {nome_tabela} ENABLE ROW LEVEL SECURITY;
    """)

def carregar_tabela_silver(cur, nome_tabela, df):
    print(f"Preparando buffer CSV em memória para {nome_tabela}...")
    output_buffer = io.StringIO()
    df.to_csv(output_buffer, index=False, header=False, na_rep="")
    output_buffer.seek(0)
    
    print(f"Executando COPY para {nome_tabela}...")
    cur.copy_expert(f"""
        COPY {nome_tabela} (
            data, time_casa, time_visitante, gols_casa, gols_visitante, torneio, cidade, pais, neutro, eh_amistoso
        ) FROM STDIN WITH CSV NULL ''
    """, output_buffer)

def main():
    load_dotenv()
    
    print("Conectando ao banco de dados para leitura da camada Bronze...")
    engine = get_engine()
    
    # Ler bronze_jogos
    try:
        df_bronze = pd.read_sql("SELECT data, time_casa, time_visitante, gols_casa, gols_visitante, torneio, cidade, pais, neutro FROM bronze_jogos", engine)
    except Exception as e:
        print(f"Erro ao ler tabela bronze_jogos: {e}")
        sys.exit(1)
        
    print(f"Total de registros lidos da bronze: {len(df_bronze)}")
    
    # Tratamento de tipos que podem ter vindo desconfigurados da leitura SQL
    df_bronze["data"] = pd.to_datetime(df_bronze["data"])
    df_bronze["gols_casa"] = df_bronze["gols_casa"].astype("Int64")
    df_bronze["gols_visitante"] = df_bronze["gols_visitante"].astype("Int64")
    df_bronze["neutro"] = df_bronze["neutro"].astype(bool)
    
    # 1. Padronizar nomes de seleções (strip + dicionário)
    df_bronze["time_casa"] = df_bronze["time_casa"].apply(limpar_nome)
    df_bronze["time_visitante"] = df_bronze["time_visitante"].apply(limpar_nome)
    
    # 2. Remover duplicatas exatas considerando as colunas de negócio
    linhas_antes = len(df_bronze)
    df_bronze = df_bronze.drop_duplicates(subset=["data", "time_casa", "time_visitante"])
    linhas_deletadas = linhas_antes - len(df_bronze)
    if linhas_deletadas > 0:
        print(f"Duplicatas exatas removidas: {linhas_deletadas}")
        
    # 3. Derivar eh_amistoso
    df_bronze["eh_amistoso"] = df_bronze["torneio"] == "Friendly"
    
    # 4. Split Anti-leakage
    # silver_copa2026: apenas os jogos sem placar (gols nulos)
    df_copa = df_bronze[df_bronze["gols_casa"].isna()].copy()
    
    # silver_jogos: jogos com placar e data >= 2006-01-01
    df_jogos = df_bronze[df_bronze["gols_casa"].notna() & (df_bronze["data"] >= "2006-01-01")].copy()
    
    # Converter datas de volta para strings formatadas para gravação limpa no CSV/COPY
    df_copa["data"] = df_copa["data"].dt.strftime("%Y-%m-%d")
    df_jogos["data"] = df_jogos["data"].dt.strftime("%Y-%m-%d")
    
    # Garantir colunas na ordem exata do schema
    colunas_finais = ["data", "time_casa", "time_visitante", "gols_casa", "gols_visitante", "torneio", "cidade", "pais", "neutro", "eh_amistoso"]
    df_copa = df_copa[colunas_finais]
    df_jogos = df_jogos[colunas_finais]
    
    # Imprimir inventário silver
    print("\n" + "=" * 60)
    print(" INVENTÁRIO DAS TABELAS SILVER ".center(60))
    print("=" * 60)
    print(f"Total de registros limpos (bronze sem duplicatas): {len(df_bronze)}")
    print(f"Registros na silver_jogos (>= 2006 e com placar):  {len(df_jogos)}")
    print(f"Registros na silver_copa2026 (sem placar):          {len(df_copa)}")
    print("-" * 60)
    
    amistosos_jogos = df_jogos["eh_amistoso"].sum()
    pct_amistosos = (amistosos_jogos / len(df_jogos)) * 100 if len(df_jogos) > 0 else 0.0
    print(f"Amistosos em silver_jogos: {amistosos_jogos} ({pct_amistosos:.2f}%)")
    print("=" * 60 + "\n")
    
    # Gravação idempotente
    print("Conectando ao banco de dados para gravação...")
    conn = get_raw_connection()
    try:
        with conn.cursor() as cur:
            # Criar e carregar silver_jogos
            criar_tabela_silver(cur, "silver_jogos")
            carregar_tabela_silver(cur, "silver_jogos", df_jogos)
            
            # Criar e carregar silver_copa2026
            criar_tabela_silver(cur, "silver_copa2026")
            carregar_tabela_silver(cur, "silver_copa2026", df_copa)
            
        conn.commit()
        print("Tabelas silver_jogos e silver_copa2026 carregadas com sucesso!")
    except Exception as e:
        conn.rollback()
        print(f"Erro ao gravar tabelas silver: {e}")
        sys.exit(1)
    finally:
        conn.close()

if __name__ == "__main__":
    main()
