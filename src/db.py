import os
import sys
from dotenv import load_dotenv
from sqlalchemy import create_engine
import psycopg2

# Add the parent directory and src directory to sys.path to support flat imports when running scripts directly
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Load environment variables from .env
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

def get_engine():
    """
    Retorna o engine do SQLAlchemy para ler/escrever tabelas (ex: com pandas).
    """
    if not DATABASE_URL:
        raise ValueError("A variável de ambiente DATABASE_URL não está configurada.")
    return create_engine(DATABASE_URL)

def get_raw_connection():
    """
    Retorna uma conexão bruta (raw connection) do psycopg2 para operações de carga em massa (COPY).
    Trata URLs de conexão com caracteres especiais na senha.
    """
    if not DATABASE_URL:
        raise ValueError("A variável de ambiente DATABASE_URL não está configurada.")
    
    url = DATABASE_URL
    try:
        # Remover prefixo do esquema
        if url.startswith("postgresql://"):
            url = url[len("postgresql://"):]
        elif url.startswith("postgres://"):
            url = url[len("postgres://"):]
            
        # Separar autenticação do host/banco
        auth, host_port_db = url.rsplit("@", 1)
        user, password = auth.split(":", 1)
        host_port, db = host_port_db.split("/", 1)
        
        # Remover query parameters se existirem
        if "?" in db:
            db, _ = db.split("?", 1)
            
        # Separar host e porta
        if ":" in host_port:
            host, port = host_port.rsplit(":", 1)
        else:
            host, port = host_port, "5432"
            
        return psycopg2.connect(
            user=user,
            password=password,
            host=host,
            port=int(port),
            database=db
        )
    except Exception as e:
        # Fallback para o método original caso o parse manual falhe
        print(f"Aviso: O parse manual da DATABASE_URL falhou ({e}). Tentando conexão direta...")
        return psycopg2.connect(DATABASE_URL)

