import os
from dotenv import load_dotenv

# Pega o diretório onde este arquivo config.py está
basedir = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(basedir, '.env'))

class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "chave_padrao_123")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Se não houver nada no .env, ele cria um banco local na pasta do projeto
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URI_LOCAL", 
        'sqlite:///' + os.path.join(basedir, 'agendamento.db')
    )
    
    SQLALCHEMY_BINDS = {
        "banco_externo": os.getenv("DATABASE_URI_EXTERNO")
    }