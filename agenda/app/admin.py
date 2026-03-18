from datetime import datetime, timedelta
from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    url_for,
    flash,
)
from flask_login import login_required, current_user
from app.models import db, Recurso, HorarioAula, Turma

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


# Proteção global para garantir que apenas admins acessem estas rotas
@admin_bp.before_request
@login_required
def verificar_admin():
    if not current_user.is_admin:
        return redirect(url_for("main.index"))


@admin_bp.route("/")
def dashboard():
    recursos = Recurso.query.all()
    # Ordena horários por turno e depois por hora de início
    horarios = HorarioAula.query.order_by(
        HorarioAula.turno, HorarioAula.hora_inicio
    ).all()
    turmas = Turma.query.all()
    return render_template(
        "admin/dashboard.html", recursos=recursos, horarios=horarios, turmas=turmas
    )


# --- GERENCIAMENTO DE RECURSOS (SALAS/EQUIPAMENTOS) ---


@admin_bp.route("/recurso/add", methods=["POST"])
def add_recurso():
    nome = request.form.get("nome")
    tipo = request.form.get("tipo")
    if nome:
        novo = Recurso(nome=nome, tipo=tipo)
        db.session.add(novo)
        db.session.commit()
        flash("Recurso adicionado com sucesso!")
    return redirect(url_for("admin.dashboard"))


@admin_bp.route("/recurso/delete/<int:id>")
def delete_recurso(id):
    recurso = Recurso.query.get_or_404(id)
    db.session.delete(recurso)
    db.session.commit()
    # Retorno compatível com AJAX ou clique direto
    if request.headers.get("X-Requested-With") == "XMLHttpRequest" or request.args.get(
        "ajax"
    ):
        return "", 204
    return redirect(url_for("admin.dashboard"))


# --- GERENCIAMENTO DE HORÁRIOS ---


@admin_bp.route("/gerar_grade", methods=["POST"])
def gerar_grade():
    try:
        inicio_str = request.form.get("hora_inicio")
        duracao = int(request.form.get("duracao"))
        qtd_aulas = int(request.form.get("qtd_aulas"))
        turno_selecionado = request.form.get("turno")

        # INTERVALO (O que eu tinha esquecido)
        intervalo_inicio_str = request.form.get("intervalo_inicio")
        intervalo_duracao = int(request.form.get("intervalo_duracao") or 0)

        formato = "%H:%M"
        corrente = datetime.strptime(inicio_str, formato)

        # Converte o horário do intervalo para objeto datetime para comparação
        tempo_intervalo = None
        if intervalo_inicio_str:
            tempo_intervalo = datetime.strptime(intervalo_inicio_str, formato).time()

        for i in range(1, qtd_aulas + 1):
            # Verifica se o horário atual atingiu ou passou o início do intervalo
            if (
                tempo_intervalo
                and corrente.time() >= tempo_intervalo
                and intervalo_duracao > 0
            ):
                corrente = corrente + timedelta(minutes=intervalo_duracao)
                intervalo_duracao = 0  # Garante que o intervalo só seja aplicado uma vez

            h_inicio = corrente.time()
            proximo = corrente + timedelta(minutes=duracao)
            h_fim = proximo.time()

            novo_horario = HorarioAula(
                descricao=f"{i}º Tempo",
                hora_inicio=h_inicio,
                hora_fim=h_fim,
                turno=turno_selecionado,
            )
            db.session.add(novo_horario)
            corrente = proximo

        db.session.commit()
        flash(f"Grade {turno_selecionado} gerada com intervalo!")
    except Exception as e:
        db.session.rollback()
        flash("Erro ao gerar grade. Verifique os campos de horário.", "danger")
    return redirect(url_for("admin.dashboard"))


@admin_bp.route("/horario/delete/<int:id>")
def delete_horario(id):
    h = HorarioAula.query.get_or_404(id)
    db.session.delete(h)
    db.session.commit()
    return "", 204  # Retorno silencioso para o JavaScript remover o elemento


# --- GERENCIAMENTO DE TURMAS ---


@admin_bp.route("/turma/gerar_sequencia", methods=["POST"])
def gerar_sequencia():
    prefixo = request.form.get("prefixo", "Ano")
    inicio = int(request.form.get("inicio", 1))
    fim = int(request.form.get("fim", 1))
    sufixo = request.form.get("sufixo", "")
    turno = request.form.get("turno")

    for i in range(inicio, fim + 1):
        # Gera: "1º Ano Fundamental"
        nome_final = f"{i}º {prefixo} {sufixo}".strip()
        nova = Turma(nome=nome_final, turno=turno)
        db.session.add(nova)

    db.session.commit()
    flash(f"Sequência de turmas para o turno {turno} gerada!")
    return redirect(url_for("admin.dashboard"))


@admin_bp.route("/turma/delete/<int:id>")
def delete_turma(id):
    turma = Turma.query.get_or_404(id)
    db.session.delete(turma)
    db.session.commit()

    # Se a requisição for AJAX (XHR), retorna apenas sucesso
    if request.headers.get("X-Requested-With") == "XMLHttpRequest" or request.args.get(
        "ajax"
    ):
        return "", 204

    return redirect(url_for("admin.dashboard"))


@admin_bp.route("/turma/limpar_todas", methods=["POST"])
def limpar_turmas():
    try:
        Turma.query.delete()
        db.session.commit()
        flash("Todas as turmas foram removidas.")
    except Exception as e:
        db.session.rollback()
        flash("Erro ao limpar turmas.", "danger")
    return redirect(url_for("admin.dashboard"))
