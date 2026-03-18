from app import create_app, db
from app.models import Professor
from werkzeug.security import generate_password_hash

app = create_app()

with app.app_context():
    # 1. Cria as tabelas do zero (com a nova coluna turno)
    db.create_all()
    print("✅ Tabelas recriadas com sucesso!")

    # 2. Cria o admin se ele não existir
    if not Professor.query.filter_by(nome="Geone dos Santos Bernardo").first():
        novo_admin = Professor(
            nome="admin", senha=generate_password_hash("fera@123"), is_admin=True
        )
        db.session.add(novo_admin)
        db.session.commit()
        print("✅ Usuário 'admin' (senha: admin123) criado com sucesso!")
