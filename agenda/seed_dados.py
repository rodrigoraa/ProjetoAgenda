from datetime import time

from app import create_app, db
from app.models import HorarioAula, Professor, Recurso, Turma
from werkzeug.security import generate_password_hash


app = create_app()


def criar_professores():
    dados = [
        ("Administrador", "00000000000", "admin123", True),
        ("Ana Costa", "11111111111", "11111111111", False),
        ("Carlos Oliveira", "22222222222", "22222222222", False),
        ("Maria Santos", "33333333333", "33333333333", False),
    ]

    for nome, matricula, senha, is_admin in dados:
        professor = Professor.query.filter_by(matricula=matricula).first()
        if professor:
            professor.nome = nome
            professor.senha = generate_password_hash(senha)
            professor.is_admin = is_admin
            continue
        db.session.add(
            Professor(
                nome=nome,
                matricula=matricula,
                senha=generate_password_hash(senha),
                is_admin=is_admin,
            )
        )


def criar_recursos():
    dados = [
        ("Sala 01", "Sala de Aula", "bi-door-open"),
        ("Sala 02", "Sala de Aula", "bi-door-open"),
        ("Laboratorio de Informatica", "Laboratorio", "bi-pc-display"),
        ("Projetor Movel", "Equipamento Movel", "bi-projector"),
        ("Caixa de Som", "Equipamento Movel", "bi-speaker"),
    ]

    for nome, tipo, icone in dados:
        if Recurso.query.filter_by(nome=nome).first():
            continue
        db.session.add(Recurso(nome=nome, tipo=tipo, icone=icone))


def criar_turmas():
    dados = [
        ("1 Ano A", "Matutino"),
        ("2 Ano A", "Matutino"),
        ("1 Ano B", "Vespertino"),
        ("2 Ano B", "Vespertino"),
        ("EJA 1", "Noturno"),
    ]

    for nome, turno in dados:
        if Turma.query.filter_by(nome=nome, turno=turno).first():
            continue
        db.session.add(Turma(nome=nome, turno=turno))


def criar_horarios():
    dados = [
        ("1 Aula", time(7, 0), time(7, 50), "Matutino"),
        ("2 Aula", time(7, 50), time(8, 40), "Matutino"),
        ("3 Aula", time(9, 0), time(9, 50), "Matutino"),
        ("1 Aula", time(13, 0), time(13, 50), "Vespertino"),
        ("2 Aula", time(13, 50), time(14, 40), "Vespertino"),
        ("1 Aula", time(19, 0), time(19, 50), "Noturno"),
        ("2 Aula", time(19, 50), time(20, 40), "Noturno"),
    ]

    for descricao, inicio, fim, turno in dados:
        existe = HorarioAula.query.filter_by(
            descricao=descricao,
            hora_inicio=inicio,
            turno=turno,
        ).first()
        if existe:
            continue
        db.session.add(
            HorarioAula(
                descricao=descricao,
                hora_inicio=inicio,
                hora_fim=fim,
                turno=turno,
            )
        )


if __name__ == "__main__":
    with app.app_context():
        criar_professores()
        criar_recursos()
        criar_turmas()
        criar_horarios()
        db.session.commit()

    print("Dados iniciais criados.")
    print("Admin: CPF 000.000.000-00 | senha admin123")
    print("Professores entram apenas com o CPF cadastrado.")
