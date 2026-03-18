import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "chave_padrao_123")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URI_LOCAL", "sqlite:///agendamento.db"
    )
    SQLALCHEMY_BINDS = {
        "banco_externo": os.getenv(
            "DATABASE_URI_EXTERNO", "sqlite:///banco_copiado_para_testes.db"
        )
    }
