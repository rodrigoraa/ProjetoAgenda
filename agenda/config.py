import os
from datetime import timedelta

from dotenv import load_dotenv

basedir = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(basedir, ".env"))


def _env_bool(nome, padrao=False):
    valor = os.getenv(nome)
    if valor is None:
        return padrao
    return valor.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(nome, padrao):
    valor = os.getenv(nome)
    if valor is None:
        return padrao
    return int(valor)


def _env_list(nome):
    valor = os.getenv(nome, "")
    itens = [item.strip() for item in valor.split(",") if item.strip()]
    return itens or None


def _normalizar_samesite(valor):
    opcoes = {"lax": "Lax", "strict": "Strict", "none": "None"}
    normalizado = opcoes.get((valor or "").strip().lower())
    if not normalizado:
        raise RuntimeError(
            "SESSION_COOKIE_SAMESITE deve ser Lax, Strict ou None."
        )
    return normalizado


class Config:
    APP_NAME = os.getenv("APP_NAME", "Agenda Escolar")
    ENV = os.getenv("ENV", os.getenv("FLASK_ENV", "development"))
    DEBUG = os.getenv("DEBUG", "False").lower() == "true"
    TESTING = False
    IS_PRODUCTION = ENV.lower() == "production"

    SECRET_KEY = os.getenv("SECRET_KEY")
    if not SECRET_KEY and ENV == "production":
        raise RuntimeError("Defina SECRET_KEY no ambiente antes de iniciar a aplicacao.")
    SECRET_KEY = SECRET_KEY or "dev-only-change-me"

    SESSION_COOKIE_NAME = "session_eesjv"
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = _normalizar_samesite(
        os.getenv("SESSION_COOKIE_SAMESITE", "Lax")
    )
    # Em produção, cookies de autenticação nunca podem ser enviados por HTTP,
    # mesmo que uma variável antiga ainda esteja configurada como False.
    SESSION_COOKIE_SECURE = (
        True if IS_PRODUCTION else _env_bool("SESSION_COOKIE_SECURE", False)
    )
    SESSION_COOKIE_PATH = "/"
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SAMESITE = SESSION_COOKIE_SAMESITE
    REMEMBER_COOKIE_SECURE = SESSION_COOKIE_SECURE
    REMEMBER_COOKIE_PATH = "/"
    REMEMBER_COOKIE_DURATION = timedelta(days=int(os.getenv("REMEMBER_COOKIE_DAYS", "30")))
    PERMANENT_SESSION_LIFETIME = timedelta(days=int(os.getenv("SESSION_DAYS", "30")))

    if SESSION_COOKIE_SAMESITE == "None" and not SESSION_COOKIE_SECURE:
        raise RuntimeError(
            "Cookies SameSite=None exigem SESSION_COOKIE_SECURE=True."
        )

    # Em produção, o TLS normalmente termina no proxy reverso. ProxyFix faz o
    # Flask respeitar apenas a quantidade declarada de proxies confiáveis.
    TRUST_PROXY_HEADERS = _env_bool("TRUST_PROXY_HEADERS", IS_PRODUCTION)
    PROXY_FIX_X_FOR = _env_int("PROXY_FIX_X_FOR", 1)
    PROXY_FIX_X_PROTO = _env_int("PROXY_FIX_X_PROTO", 1)
    PROXY_FIX_X_HOST = _env_int("PROXY_FIX_X_HOST", 1)
    PROXY_FIX_X_PORT = _env_int("PROXY_FIX_X_PORT", 1)
    FORCE_HTTPS = _env_bool("FORCE_HTTPS", IS_PRODUCTION)
    PREFERRED_URL_SCHEME = "https" if FORCE_HTTPS else "http"
    TRUSTED_HOSTS = _env_list("TRUSTED_HOSTS")
    HSTS_MAX_AGE = _env_int("HSTS_MAX_AGE", 31536000)

    SQLALCHEMY_TRACK_MODIFICATIONS = False
    DEFAULT_ADMIN_ENABLED = os.getenv("DEFAULT_ADMIN_ENABLED", "False").lower() == "true"
    DEFAULT_ADMIN_NOME = os.getenv("DEFAULT_ADMIN_NOME", "Administrador")
    DEFAULT_ADMIN_MATRICULA = os.getenv("DEFAULT_ADMIN_MATRICULA", "ADMIN001").strip().upper()
    DEFAULT_ADMIN_SENHA = os.getenv("DEFAULT_ADMIN_SENHA", "")

    # A aplicacao usa o banco local deste proprio projeto.
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URI_LOCAL",
        "sqlite:///" + os.path.join(basedir, "agendamento.db"),
    )


class DevelopmentConfig(Config):
    ENV = "development"
    DEBUG = True
    FORCE_HTTPS = False
    TRUST_PROXY_HEADERS = False


class TestingConfig(Config):
    TESTING = True
    WTF_CSRF_ENABLED = False
    FORCE_HTTPS = False
    TRUST_PROXY_HEADERS = False
    SESSION_COOKIE_SECURE = False
    REMEMBER_COOKIE_SECURE = False
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"


def get_config():
    env = os.getenv("ENV", os.getenv("FLASK_ENV", "development")).lower()
    if env == "development":
        return DevelopmentConfig
    if env == "testing":
        return TestingConfig
    return Config
