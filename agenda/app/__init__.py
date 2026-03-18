from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from config import Config

db = SQLAlchemy()
login_manager = LoginManager()


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    db.init_app(app)
    login_manager.init_app(app)

    login_manager.login_view = "main.login"
    login_manager.login_message = "Por favor, faça login para acessar."

    from app.models import Professor

    @login_manager.user_loader
    def load_user(user_id):
        return Professor.query.get(int(user_id))

    # Blueprints
    from app.controllers import main as main_blueprint
    from app.admin import admin_bp

    app.register_blueprint(main_blueprint)
    app.register_blueprint(admin_bp)

    with app.app_context():
        db.create_all()

    return app
