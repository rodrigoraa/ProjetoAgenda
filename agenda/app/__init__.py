from flask import Flask, flash, jsonify, redirect, request, url_for
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.exc import IntegrityError
from flask_login import LoginManager
from sqlalchemy import inspect, text
from werkzeug.security import generate_password_hash
from werkzeug.middleware.proxy_fix import ProxyFix
from config import get_config

db = SQLAlchemy()
login_manager = LoginManager()


def _garantir_coluna_matricula():
    inspector = inspect(db.engine)
    if "professores" not in inspector.get_table_names():
        return

    colunas = {coluna["name"] for coluna in inspector.get_columns("professores")}
    if "matricula" in colunas:
        return

    with db.engine.begin() as conexao:
        conexao.execute(
            text("ALTER TABLE professores ADD COLUMN matricula VARCHAR(30)")
        )
        conexao.execute(text("UPDATE professores SET matricula = nome"))
        conexao.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS ix_professores_matricula "
                "ON professores (matricula)"
            )
        )


def _garantir_coluna_imagem_recurso():
    inspector = inspect(db.engine)
    if "recursos" not in inspector.get_table_names():
        return

    colunas = {coluna["name"] for coluna in inspector.get_columns("recursos")}
    if "imagem" in colunas:
        return

    with db.engine.begin() as conexao:
        conexao.execute(text("ALTER TABLE recursos ADD COLUMN imagem VARCHAR(255)"))


def _garantir_admin_padrao(app):
    if not app.config.get("DEFAULT_ADMIN_ENABLED"):
        return

    from app.models import Professor

    matricula = (app.config.get("DEFAULT_ADMIN_MATRICULA") or "").strip().upper()
    senha = app.config.get("DEFAULT_ADMIN_SENHA") or ""
    nome = (app.config.get("DEFAULT_ADMIN_NOME") or "Administrador").strip()

    if not matricula or not senha:
        return

    admin_existente = Professor.query.filter_by(matricula=matricula).first()
    if admin_existente:
        if not admin_existente.is_admin:
            admin_existente.is_admin = True
            db.session.commit()
        return

    try:
        db.session.add(
            Professor(
                nome=nome,
                matricula=matricula,
                senha=generate_password_hash(senha),
                is_admin=True,
            )
        )
        db.session.commit()
    except IntegrityError:
        # Mais de um worker pode subir ao mesmo tempo em produção.
        # Se outro processo criou o admin primeiro, apenas seguimos.
        db.session.rollback()
        admin_existente = Professor.query.filter_by(matricula=matricula).first()
        if admin_existente and not admin_existente.is_admin:
            admin_existente.is_admin = True
            db.session.commit()


def create_app(config_object=None):
    app = Flask(__name__)
    app.config.from_object(config_object or get_config())

    if app.config.get("TRUST_PROXY_HEADERS"):
        app.wsgi_app = ProxyFix(
            app.wsgi_app,
            x_for=app.config.get("PROXY_FIX_X_FOR", 1),
            x_proto=app.config.get("PROXY_FIX_X_PROTO", 1),
            x_host=app.config.get("PROXY_FIX_X_HOST", 1),
            x_port=app.config.get("PROXY_FIX_X_PORT", 1),
        )

    db.init_app(app)
    login_manager.init_app(app)

    login_manager.login_view = "main.login"
    login_manager.login_message = "Por favor, faça login para acessar."

    from app.models import Professor
    from app.security import CSRFValidationError, get_csrf_token, validate_csrf

    @login_manager.user_loader
    def load_user(user_id):
        try:
            return Professor.query.get(int(user_id))
        except (TypeError, ValueError):
            return None

    @app.before_request
    def proteger_requisicoes_mutaveis():
        if app.config.get("FORCE_HTTPS") and not request.is_secure:
            destino = request.url.replace("http://", "https://", 1)
            return redirect(destino, code=308)
        validate_csrf()

    @app.errorhandler(CSRFValidationError)
    def tratar_csrf_invalido(_erro):
        if (
            request.path.startswith("/api/")
            or request.headers.get("X-Requested-With") == "XMLHttpRequest"
            or request.is_json
        ):
            return (
                jsonify(
                    {
                        "sucesso": False,
                        "erro": "Sua sessão de segurança expirou. Recarregue a página.",
                        "codigo": "csrf_invalido",
                    }
                ),
                400,
            )

        flash(
            "Sua sessão de segurança expirou. O formulário foi renovado; tente novamente.",
            "warning",
        )
        destino = "main.login"
        if request.path.startswith("/admin/"):
            destino = "admin.dashboard"
        elif request.endpoint != "main.login":
            destino = "main.index"
        return redirect(url_for(destino), code=303)

    @app.context_processor
    def inject_security_helpers():
        insights_padrao = {
            "dias": 30,
            "total_reservas": 0,
            "taxa_ocupacao": 0,
            "professores_ativos": 0,
            "turmas": 0,
            "por_periodo": [],
            "por_professor": [],
            "por_recurso": [],
            "por_turma": [],
            "maior_total": 1,
        }
        return {"csrf_token": get_csrf_token, "insights": insights_padrao}

    @app.after_request
    def aplicar_headers_de_seguranca(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault(
            "Permissions-Policy",
            "camera=(), microphone=(), geolocation=()",
        )
        if request.is_secure:
            response.headers.setdefault(
                "Content-Security-Policy",
                "upgrade-insecure-requests; block-all-mixed-content",
            )
            response.headers.setdefault(
                "Strict-Transport-Security",
                f"max-age={app.config.get('HSTS_MAX_AGE', 31536000)}",
            )
        if request.endpoint in {"main.login", "main.logout"}:
            response.headers["Cache-Control"] = "no-store, max-age=0"
            response.headers["Pragma"] = "no-cache"
        return response

    from app.controllers import main as main_blueprint
    from app.admin import admin_bp

    app.register_blueprint(main_blueprint)
    app.register_blueprint(admin_bp)

    with app.app_context():
        db.create_all()
        _garantir_coluna_matricula()
        _garantir_coluna_imagem_recurso()
        _garantir_admin_padrao(app)

    return app
