import os
import sys
import io
import pandas as pd
from collections import defaultdict
from dotenv import load_dotenv

# Garantir que o diretório src/ esteja no path para importações flat
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from db import get_engine, get_raw_connection

def main():
    load_dotenv()
    
    print("Conectando ao banco de dados para leitura de silver_ponderado...")
    engine = get_engine()
    
    # 1. Ler silver_ponderado ordenando por data e id (para garantir cronologia determinística)
    try:
        df = pd.read_sql("""
            SELECT id, data, time_casa, time_visitante, gols_casa, gols_visitante, neutro, peso_torneio 
            FROM silver_ponderado 
            ORDER BY data ASC, id ASC
        """, engine)
    except Exception as e:
        print(f"Erro ao ler tabela silver_ponderado: {e}")
        sys.exit(1)
        
    print(f"Total de registros lidos: {len(df)}")
    
    # Conversões explícitas de tipo
    df["id"] = df["id"].astype("int64")
    df["data"] = pd.to_datetime(df["data"])
    df["gols_casa"] = df["gols_casa"].astype(int)
    df["gols_visitante"] = df["gols_visitante"].astype(int)
    df["neutro"] = df["neutro"].astype(bool)
    df["peso_torneio"] = df["peso_torneio"].astype(int)
    
    # Dicionário ELO para manter forças das equipes
    elo_times = defaultdict(lambda: 1500.0)
    
    # Lista para armazenar registros de elo_pre_jogo
    elo_pre_list = []
    
    # Mapeamento do K-factor
    k_factors = {1: 20.0, 2: 40.0, 3: 60.0}
    
    # Loop sequencial cronológico
    for _, row in df.iterrows():
        jogo_id = row["id"]
        data_jogo = row["data"].strftime("%Y-%m-%d")
        t_casa = row["time_casa"]
        t_visit = row["time_visitante"]
        g_casa = row["gols_casa"]
        g_visit = row["gols_visitante"]
        neutro = row["neutro"]
        p_torneio = row["peso_torneio"]
        
        # Recuperar ELO pré-jogo
        elo_casa_pre = elo_times[t_casa]
        elo_visit_pre = elo_times[t_visit]
        
        # Guardar para a tabela silver_elo_pre_jogo
        elo_pre_list.append({
            "jogo_id": jogo_id,
            "data": data_jogo,
            "time_casa": t_casa,
            "time_visitante": t_visit,
            "elo_casa": elo_casa_pre,
            "elo_visitante": elo_visit_pre
        })
        
        # HFA (mando de campo) = 100 se neutro = False, 0 se neutro = True
        hfa = 100.0 if not neutro else 0.0
        
        # Calcular expectativas
        e_casa = 1.0 / (1.0 + 10.0 ** ((elo_visit_pre - elo_casa_pre - hfa) / 400.0))
        e_visit = 1.0 - e_casa
        
        # Resultado real para o time da casa
        if g_casa > g_visit:
            s_casa = 1.0
        elif g_casa == g_visit:
            s_casa = 0.5
        else:
            s_casa = 0.0
            
        s_visit = 1.0 - s_casa
        
        # K-factor correspondente
        k = k_factors.get(p_torneio, 20.0)
        
        # Atualização do ELO
        elo_times[t_casa] += k * (s_casa - e_casa)
        elo_times[t_visit] += k * (s_visit - e_visit)
        
    # Converter lista de ELOs pré-jogo para DataFrame
    df_pre = pd.DataFrame(elo_pre_list)
    
    # Preparar DataFrame de ELOs finais atuais
    df_atual = pd.DataFrame([
        {"selecao": time, "elo": elo_valor}
        for time, elo_valor in elo_times.items()
    ])
    df_atual = df_atual.sort_values(by="elo", ascending=False).reset_index(drop=True)
    
    # Imprimir inventário ELO
    print("\n" + "=" * 60)
    print(" INVENTÁRIO DE FORÇA ELO ".center(60))
    print("=" * 60)
    print(f"Total de jogos processados: {len(df_pre)}")
    print(f"Total de seleções mapeadas: {len(df_atual)}")
    print("-" * 60)
    print("Top 10 Seleções pelo ELO Atual:")
    for idx, row in df_atual.head(10).iterrows():
        print(f"  {idx+1:>2}. {row['selecao']:<25} : {row['elo']:.2f}")
    print("=" * 60 + "\n")
    
    # Gravação no banco de dados de forma idempotente
    print("Conectando ao banco de dados para gravação...")
    conn = get_raw_connection()
    try:
        with conn.cursor() as cur:
            # 1. Recriar e carregar tabela silver_elo_pre_jogo
            print("Removendo tabela silver_elo_pre_jogo anterior...")
            cur.execute("DROP TABLE IF EXISTS silver_elo_pre_jogo CASCADE;")
            
            print("Criando tabela silver_elo_pre_jogo...")
            cur.execute("""
                CREATE TABLE silver_elo_pre_jogo (
                    id bigint generated always as identity primary key,
                    jogo_id bigint NOT NULL,
                    data date NOT NULL,
                    time_casa text NOT NULL,
                    time_visitante text NOT NULL,
                    elo_casa double precision NOT NULL,
                    elo_visitante double precision NOT NULL
                );
                ALTER TABLE silver_elo_pre_jogo ENABLE ROW LEVEL SECURITY;
            """)
            
            print("Preparando buffer e executando COPY para silver_elo_pre_jogo...")
            pre_buffer = io.StringIO()
            df_pre.to_csv(pre_buffer, index=False, header=False, na_rep="")
            pre_buffer.seek(0)
            cur.copy_expert("""
                COPY silver_elo_pre_jogo (
                    jogo_id, data, time_casa, time_visitante, elo_casa, elo_visitante
                ) FROM STDIN WITH CSV NULL ''
            """, pre_buffer)
            
            # 2. Recriar e carregar tabela silver_elo_atual
            print("Removendo tabela silver_elo_atual anterior...")
            cur.execute("DROP TABLE IF EXISTS silver_elo_atual CASCADE;")
            
            print("Criando tabela silver_elo_atual...")
            cur.execute("""
                CREATE TABLE silver_elo_atual (
                    id bigint generated always as identity primary key,
                    selecao text NOT NULL UNIQUE,
                    elo double precision NOT NULL
                );
                ALTER TABLE silver_elo_atual ENABLE ROW LEVEL SECURITY;
            """)
            
            print("Preparando buffer e executando COPY para silver_elo_atual...")
            atual_buffer = io.StringIO()
            df_atual.to_csv(atual_buffer, index=False, header=False, na_rep="")
            atual_buffer.seek(0)
            cur.copy_expert("""
                COPY silver_elo_atual (
                    selecao, elo
                ) FROM STDIN WITH CSV NULL ''
            """, atual_buffer)
            
        conn.commit()
        print("Tabelas de ELO gravadas com sucesso!")
        
    except Exception as e:
        conn.rollback()
        print(f"Erro ao gravar tabelas de ELO: {e}")
        sys.exit(1)
    finally:
        conn.close()

if __name__ == "__main__":
    main()
