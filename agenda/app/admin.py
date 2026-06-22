from datetime import datetime, timedelta
import os
import re
from uuid import uuid4

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import and_
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash

from app.models import Agendamento, HorarioAula, Professor, Recurso, Turma, db

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")
EXTENSOES_IMAGEM = {"jpg", "jpeg", "png", "webp"}


def _normalizar_matricula(valor):
    texto = (valor or "").strip()
    somente_digitos = re.sub(r"\D", "", texto)
    if len(somente_digitos) == 11:
        return somente_digitos
    return texto.upper()


def _parse_date(date_str):
    if not date_str:
        return None
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        return None


def _arquivo_de_imagem(nome_arquivo):
    if not nome_arquivo or "." not in nome_arquivo:
        return False
    extensao = nome_arquivo.rsplit(".", 1)[1].lower()
    return extensao in EXTENSOES_IMAGEM


def _pasta_upload_recursos():
    pasta = os.path.join(current_app.static_folder, "uploads", "recursos")
    os.makedirs(pasta, exist_ok=True)
    return pasta


def _salvar_imagem_recurso(arquivo):
    if not arquivo or not arquivo.filename:
        return None
    if not _arquivo_de_imagem(arquivo.filename):
        raise ValueError("Envie uma imagem JPG, PNG ou WEBP.")

    nome_seguro = secure_filename(arquivo.filename)
    extensao = nome_seguro.rsplit(".", 1)[1].lower()
    nome_final = f"{uuid4().hex}.{extensao}"
    arquivo.save(os.path.join(_pasta_upload_recursos(), nome_final))
    return f"uploads/recursos/{nome_final}"


def _remover_imagem_recurso(caminho_relativo):
    if not caminho_relativo:
        return

    static_root = os.path.abspath(current_app.static_folder)
    caminho = os.path.abspath(os.path.join(static_root, caminho_relativo))
    if os.path.commonpath([static_root, caminho]) != static_root or not os.path.isfile(caminho):
        return

    try:
        os.remove(caminho)
    except OSError:
        pass


@admin_bp.before_request
@login_required
def verificar_admin():
    if not current_user.is_admin:
        return redirect(url_for("main.index"))


@admin_bp.route("/")
def dashboard():
    recursos = Recurso.query.order_by(Recurso.nome).all()
    horarios = HorarioAula.query.order_by(
        HorarioAula.turno, HorarioAula.hora_inicio
    ).all()
    turmas = Turma.query.order_by(Turma.turno, Turma.nome).all()
    professores = Professor.query.order_by(Professor.nome).all()
    total_admins = sum(1 for professor in professores if professor.is_admin)

    filtro_inicio = request.args.get("inicio", "")
    filtro_fim = request.args.get("fim", "")
    filtro_professor = request.args.get("professor_id", "")
    filtro_recurso = request.args.get("recurso_id", "")

    data_inicio = _parse_date(filtro_inicio)
    data_fim = _parse_date(filtro_fim)
    professor_id = None
    recurso_id = None

    try:
        if filtro_professor:
            professor_id = int(filtro_professor)
    except (TypeError, ValueError):
        filtro_professor = ""

    try:
        if filtro_recurso:
            recurso_id = int(filtro_recurso)
    except (TypeError, ValueError):
        filtro_recurso = ""

    relatorio_query = (
        db.session.query(Agendamento, Professor, Recurso, Turma, HorarioAula)
        .join(Professor, Professor.id == Agendamento.id_professor)
        .join(Recurso, Recurso.id == Agendamento.recurso_id)
        .join(Turma, Turma.id == Agendamento.turma_id)
        .join(HorarioAula, HorarioAula.id == Agendamento.horario_id)
    )

    if data_inicio:
        relatorio_query = relatorio_query.filter(Agendamento.data >= data_inicio)
    if data_fim:
        relatorio_query = relatorio_query.filter(Agendamento.data <= data_fim)
    if professor_id is not None:
        relatorio_query = relatorio_query.filter(Agendamento.id_professor == professor_id)
    if recurso_id is not None:
        relatorio_query = relatorio_query.filter(Agendamento.recurso_id == recurso_id)

    relatorio_linhas = relatorio_query.order_by(
        Agendamento.data.desc(), HorarioAula.hora_inicio.asc()
    ).all()

    relatorio = [
        {
            "id": agendamento.id,
            "data": agendamento.data,
            "professor": professor.nome,
            "matricula": professor.matricula,
            "recurso": recurso.nome,
            "tipo_recurso": recurso.tipo,
            "turma": turma.nome,
            "turno": turma.turno,
            "horario": horario.descricao,
            "intervalo": (
                f"{horario.hora_inicio.strftime('%H:%M')} - "
                f"{horario.hora_fim.strftime('%H:%M')}"
            ),
        }
        for agendamento, professor, recurso, turma, horario in relatorio_linhas
    ]

    return render_template(
        "admin/dashboard.html",
        recursos=recursos,
        horarios=horarios,
        turmas=turmas,
        professores=professores,
        total_admins=total_admins,
        relatorio=relatorio,
        filtro_inicio=filtro_inicio,
        filtro_fim=filtro_fim,
        filtro_professor=filtro_professor,
        filtro_recurso=filtro_recurso,
    )


@admin_bp.route("/professor/add", methods=["POST"])
def add_professor():
    nome = (request.form.get("nome") or "").strip()
    matricula = _normalizar_matricula(request.form.get("matricula"))
    senha = (request.form.get("senha") or "").strip()
    perfil = request.form.get("perfil", "professor")

    if not nome or not matricula:
        flash("Nome e CPF são obrigatórios.", "warning")
        return redirect(url_for("admin.dashboard"))

    if Professor.query.filter_by(matricula=matricula).first():
        flash("Já existe um usuário com esse CPF.", "warning")
        return redirect(url_for("admin.dashboard"))

    senha_final = senha or matricula

    try:
        novo_professor = Professor(
            nome=nome,
            matricula=matricula,
            senha=generate_password_hash(senha_final),
            is_admin=(perfil == "admin"),
        )
        db.session.add(novo_professor)
        db.session.commit()
        flash(
            f"Usuário {nome} cadastrado com sucesso. CPF: {matricula}.",
            "success",
        )
    except Exception:
        db.session.rollback()
        flash("Não foi possível cadastrar o usuário.", "danger")

    return redirect(url_for("admin.dashboard"))


@admin_bp.route("/professor/update/<int:id>", methods=["POST"])
def update_professor(id):
    professor = Professor.query.get_or_404(id)
    nome = (request.form.get("nome") or "").strip()
    matricula = _normalizar_matricula(request.form.get("matricula"))
    perfil = request.form.get("perfil", "professor")

    if not nome or not matricula:
        flash("Nome e CPF são obrigatórios para atualizar.", "warning")
        return redirect(url_for("admin.dashboard"))

    duplicado = Professor.query.filter(
        and_(Professor.matricula == matricula, Professor.id != professor.id)
    ).first()
    if duplicado:
        flash("Outra conta já utiliza esse CPF.", "warning")
        return redirect(url_for("admin.dashboard"))

    if professor.id == current_user.id and perfil != "admin":
        flash("Você não pode remover o próprio perfil administrativo.", "warning")
        return redirect(url_for("admin.dashboard"))

    try:
        professor.nome = nome
        professor.matricula = matricula
        professor.is_admin = perfil == "admin"
        db.session.commit()
        flash(f"Cadastro de {nome} atualizado com sucesso.", "success")
    except Exception:
        db.session.rollback()
        flash("Não foi possível atualizar o usuário.", "danger")

    return redirect(url_for("admin.dashboard"))


@admin_bp.route("/professor/delete/<int:id>", methods=["POST"])
def delete_professor(id):
    professor = Professor.query.get_or_404(id)

    if professor.id == current_user.id:
        flash("Não é permitido excluir a própria conta em uso.", "warning")
        return redirect(url_for("admin.dashboard"))

    try:
        Agendamento.query.filter_by(id_professor=id).delete()
        db.session.delete(professor)
        db.session.commit()
        flash(f"Usuário {professor.nome} removido com sucesso.", "success")
    except Exception:
        db.session.rollback()
        flash("Não foi possível remover o usuário.", "danger")

    return redirect(url_for("admin.dashboard"))


@admin_bp.route("/redefinir_senha", methods=["POST"])
def redefinir_senha_professor():
    professor_id = request.form.get("professor_id")
    nova_senha = (request.form.get("nova_senha") or "").strip()

    professor = Professor.query.get(professor_id)

    if professor and nova_senha:
        try:
            professor.senha = generate_password_hash(nova_senha)
            db.session.commit()
            flash(
                f"A senha do usuário {professor.nome} foi redefinida com sucesso.",
                "success",
            )
        except Exception:
            db.session.rollback()
            flash("Erro ao redefinir a senha no banco de dados.", "danger")
    else:
        flash("Dados inválidos ou usuário não encontrado.", "warning")

    return redirect(url_for("admin.dashboard"))


@admin_bp.route("/recurso/add", methods=["POST"])
def add_recurso():
    nome = (request.form.get("nome") or "").strip()
    tipo = request.form.get("tipo")
    icone = request.form.get("icone", "bi-box")
    if nome:
        try:
            imagem = _salvar_imagem_recurso(request.files.get("imagem"))
            novo = Recurso(nome=nome, tipo=tipo, icone=icone, imagem=imagem)
            db.session.add(novo)
            db.session.commit()
            flash("Recurso adicionado com sucesso!", "success")
        except ValueError as erro:
            flash(str(erro), "warning")
        except Exception:
            db.session.rollback()
            flash("Não foi possível adicionar o recurso.", "danger")
    return redirect(url_for("admin.dashboard"))


@admin_bp.route("/recurso/imagem/<int:id>", methods=["POST"])
def update_imagem_recurso(id):
    recurso = Recurso.query.get_or_404(id)
    remover = request.form.get("remover_imagem") == "1"

    try:
        if remover:
            _remover_imagem_recurso(recurso.imagem)
            recurso.imagem = None
            db.session.commit()
            flash(f"Foto de {recurso.nome} removida.", "success")
            return redirect(url_for("admin.dashboard"))

        imagem = _salvar_imagem_recurso(request.files.get("imagem"))
        if not imagem:
            flash("Selecione uma imagem antes de salvar.", "warning")
            return redirect(url_for("admin.dashboard"))

        _remover_imagem_recurso(recurso.imagem)
        recurso.imagem = imagem
        db.session.commit()
        flash(f"Foto de {recurso.nome} atualizada.", "success")
    except ValueError as erro:
        flash(str(erro), "warning")
    except Exception:
        db.session.rollback()
        flash("Não foi possível atualizar a foto do recurso.", "danger")

    return redirect(url_for("admin.dashboard"))


@admin_bp.route("/recurso/delete/<int:id>", methods=["POST"])
def delete_recurso(id):
    recurso = Recurso.query.get_or_404(id)
    imagem = recurso.imagem
    Agendamento.query.filter_by(recurso_id=id).delete()
    db.session.delete(recurso)
    db.session.commit()
    _remover_imagem_recurso(imagem)
    if request.headers.get("X-Requested-With") == "XMLHttpRequest" or request.args.get(
        "ajax"
    ):
        return "", 204
    return redirect(url_for("admin.dashboard"))


@admin_bp.route("/gerar_grade", methods=["POST"])
def gerar_grade():
    try:
        inicio_str = request.form.get("hora_inicio")
        duracao = int(request.form.get("duracao"))
        qtd_aulas = int(request.form.get("qtd_aulas"))
        turno_selecionado = request.form.get("turno")
        intervalo_inicio_str = request.form.get("intervalo_inicio")
        intervalo_duracao = int(request.form.get("intervalo_duracao") or 0)

        formato = "%H:%M"
        corrente = datetime.strptime(inicio_str, formato)

        tempo_intervalo = None
        if intervalo_inicio_str:
            tempo_intervalo = datetime.strptime(intervalo_inicio_str, formato).time()

        for i in range(1, qtd_aulas + 1):
            if (
                tempo_intervalo
                and corrente.time() >= tempo_intervalo
                and intervalo_duracao > 0
            ):
                corrente = corrente + timedelta(minutes=intervalo_duracao)
                intervalo_duracao = 0

            h_inicio = corrente.time()
            proximo = corrente + timedelta(minutes=duracao)
            h_fim = proximo.time()

            novo_horario = HorarioAula(
                descricao=f"{i}º Aula",
                hora_inicio=h_inicio,
                hora_fim=h_fim,
                turno=turno_selecionado,
            )
            db.session.add(novo_horario)
            corrente = proximo

        db.session.commit()
        flash(f"Grade {turno_selecionado} gerada com sucesso.", "success")
    except Exception:
        db.session.rollback()
        flash("Erro ao gerar grade. Verifique os campos de horário.", "danger")
    return redirect(url_for("admin.dashboard"))


@admin_bp.route("/horario/delete/<int:id>", methods=["POST"])
def delete_horario(id):
    horario = HorarioAula.query.get_or_404(id)
    Agendamento.query.filter_by(horario_id=id).delete()
    db.session.delete(horario)
    db.session.commit()
    return "", 204


@admin_bp.route("/turma/gerar_sequencia", methods=["POST"])
def gerar_sequencia():
    prefixo = request.form.get("prefixo", "Ano")
    inicio = int(request.form.get("inicio", 1))
    fim = int(request.form.get("fim", 1))
    sufixo = request.form.get("sufixo", "")
    turno = request.form.get("turno")

    for i in range(inicio, fim + 1):
        nome_final = f"{i}º {prefixo} {sufixo}".strip()
        nova = Turma(nome=nome_final, turno=turno)
        db.session.add(nova)

    db.session.commit()
    flash(f"Sequência de turmas para o turno {turno} gerada!", "success")
    return redirect(url_for("admin.dashboard"))


@admin_bp.route("/turma/delete/<int:id>", methods=["POST"])
def delete_turma(id):
    turma = Turma.query.get_or_404(id)
    Agendamento.query.filter_by(turma_id=id).delete()
    db.session.delete(turma)
    db.session.commit()

    if request.headers.get("X-Requested-With") == "XMLHttpRequest" or request.args.get(
        "ajax"
    ):
        return "", 204

    return redirect(url_for("admin.dashboard"))


@admin_bp.route("/turma/limpar_todas", methods=["POST"])
def limpar_turmas():
    try:
        Agendamento.query.delete()
        Turma.query.delete()
        db.session.commit()
        flash("Todas as turmas foram removidas.", "success")
    except Exception:
        db.session.rollback()
        flash("Erro ao limpar turmas.", "danger")
    return redirect(url_for("admin.dashboard"))
