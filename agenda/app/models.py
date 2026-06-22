from flask_login import UserMixin
from sqlalchemy import UniqueConstraint
from werkzeug.security import check_password_hash
from app import db


class Professor(UserMixin, db.Model):
    __tablename__ = "professores"
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(150), nullable=False)
    matricula = db.Column(db.String(30), unique=True, nullable=False, index=True)
    senha = db.Column(db.String(255), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)

    def verificar_senha(self, senha_texto_plano):
        return check_password_hash(self.senha, senha_texto_plano)


class Recurso(db.Model):
    __tablename__ = "recursos"
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    tipo = db.Column(db.String(50), nullable=False)
    icone = db.Column(db.String(50), default="bi-box")
    imagem = db.Column(db.String(255), nullable=True)


class Turma(db.Model):
    __tablename__ = "turmas"
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(50), nullable=False)
    turno = db.Column(db.String(20), nullable=False)


class HorarioAula(db.Model):
    __tablename__ = "horarios"
    id = db.Column(db.Integer, primary_key=True)
    descricao = db.Column(db.String(50), nullable=False)
    hora_inicio = db.Column(db.Time, nullable=False)
    hora_fim = db.Column(db.Time, nullable=False)
    turno = db.Column(db.String(20), nullable=False)


class Agendamento(db.Model):
    __tablename__ = "agendamentos"
    __table_args__ = (
        UniqueConstraint(
            "data",
            "recurso_id",
            "horario_id",
            name="uq_agendamento_recurso_horario_data",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    id_professor = db.Column(db.Integer, db.ForeignKey("professores.id"), nullable=False)
    data = db.Column(db.Date, nullable=False)
    recurso_id = db.Column(db.Integer, db.ForeignKey("recursos.id"), nullable=False)
    turma_id = db.Column(db.Integer, db.ForeignKey("turmas.id"), nullable=False)
    horario_id = db.Column(db.Integer, db.ForeignKey("horarios.id"), nullable=False)

    professor = db.relationship("Professor", backref="agendamentos")
    recurso = db.relationship("Recurso", backref="agendamentos")
    turma = db.relationship("Turma", backref="agendamentos")
    horario = db.relationship("HorarioAula", backref="agendamentos")
