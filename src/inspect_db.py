import os
import sys
from dotenv import load_dotenv

# Garantir que o diretório src/ esteja no path para importações flat
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from db import get_raw_connection

load_dotenv()

def main():
    try:
        conn = get_raw_connection()
        with conn.cursor() as cur:
            cur.execute("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public'
                ORDER BY table_name;
            """)
            tables = cur.fetchall()
            print("Tables in public schema:")
            for t in tables:
                cur.execute(f"SELECT COUNT(*) FROM {t[0]};")
                count = cur.fetchone()[0]
                print(f" - {t[0]} ({count} rows)")
    except Exception as e:
        print("Error:", e)
    finally:
        try:
            conn.close()
        except NameError:
            pass

if __name__ == "__main__":
    main()
