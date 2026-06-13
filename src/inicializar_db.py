import os
import sys
import pandas as pd
from dotenv import load_dotenv

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from db import get_raw_connection, get_engine

def main():
    load_dotenv()
    dir_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    
    csv_grupos = os.path.join(dir_path, "data/grupos_copa2026.csv")
    csv_calendario = os.path.join(dir_path, "data/calendario_copa2026.csv")
    
    if not os.path.exists(csv_grupos) or not os.path.exists(csv_calendario):
        print("Erro: CSVs de configuração de grupo ou calendário não encontrados em data/.")
        sys.exit(1)
        
    df_grupos = pd.read_csv(csv_grupos)
    df_calendario = pd.read_csv(csv_calendario)
    
    print("Conectando ao banco de dados...")
    conn = get_raw_connection()
    try:
        with conn.cursor() as cur:
            # 1. Tabela de grupos
            print("Criando tabela copa_grupos...")
            cur.execute("DROP TABLE IF EXISTS copa_grupos CASCADE;")
            cur.execute("""
                CREATE TABLE copa_grupos (
                    id bigint generated always as identity primary key,
                    grupo text NOT NULL,
                    posicao integer NOT NULL,
                    selecao text NOT NULL
                );
            """)
            
            # Inserir dados de grupos
            for _, row in df_grupos.iterrows():
                cur.execute("""
                    INSERT INTO copa_grupos (grupo, posicao, selecao)
                    VALUES (%s, %s, %s);
                """, (row["group"], int(row["position"]), row["nation"]))
                
            # 2. Tabela de calendário de mata-mata
            print("Criando tabela copa_calendario_mata_mata...")
            cur.execute("DROP TABLE IF EXISTS copa_calendario_mata_mata CASCADE;")
            cur.execute("""
                CREATE TABLE copa_calendario_mata_mata (
                    match_id text primary key,
                    rodada text NOT NULL,
                    match_date date NOT NULL,
                    match_time text,
                    home_slot text NOT NULL,
                    away_slot text NOT NULL,
                    winner_advances_to text NOT NULL,
                    loser_advances_to text
                );
            """)
            
            # Inserir dados de calendário
            for _, row in df_calendario.iterrows():
                # Tratar nulos em loser_advances_to
                loser_adv = row["loser_advances_to"] if pd.notna(row["loser_advances_to"]) else None
                cur.execute("""
                    INSERT INTO copa_calendario_mata_mata (
                        match_id, rodada, match_date, match_time, home_slot, away_slot, winner_advances_to, loser_advances_to
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s);
                """, (
                    row["match_id"], row["round"], row["match_date"], row["match_time"],
                    row["home_slot"], row["away_slot"], row["winner_advances_to"], loser_adv
                ))
                
            # 3. Tabela de resultados reais do mata-mata
            print("Criando tabela copa_mata_mata_resultados...")
            cur.execute("DROP TABLE IF EXISTS copa_mata_mata_resultados CASCADE;")
            cur.execute("""
                CREATE TABLE copa_mata_mata_resultados (
                    match_id text primary key REFERENCES copa_calendario_mata_mata(match_id),
                    home_team text NOT NULL,
                    away_team text NOT NULL,
                    gols_casa integer NOT NULL,
                    gols_visitante integer NOT NULL,
                    vencedor text NOT NULL,
                    penaltis_vencedor text
                );
            """)
            
        conn.commit()
        print("Tabelas de fundação criadas e populadas com sucesso no Supabase!")
        
    except Exception as e:
        conn.rollback()
        print("Erro ao inicializar tabelas no banco:", e)
        sys.exit(1)
    finally:
        conn.close()

if __name__ == "__main__":
    main()
