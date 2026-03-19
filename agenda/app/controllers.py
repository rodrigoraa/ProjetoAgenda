from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_user, logout_user, login_required, current_user
from app.models import db, Professor, Recurso, Agendamento, HorarioAula, Turma
from datetime import datetime
from sqlalchemy import func

main = Blueprint("main", __name__)


# ==========================================================
# FUNÇÃO GLOBAL PARA IDENTIFICAR EQUIPAMENTOS
# ==========================================================
def eh_equipamento(rec):
    if not rec:
        return False
    tipo = rec.tipo.lower() if rec.tipo else ""
    nome = rec.nome.lower() if rec.nome else ""
    # Considera equipamento se o tipo for "equipamento" ou se o nome contiver palavras-chave
    return (
        "equipamento" in tipo or "caixa" in nome or "projetor" in nome or "tv" in nome
    )


# ==========================================================
# ROTAS DE PÁGINAS E AUTENTICAÇÃO
# ==========================================================
@main.route("/")
@login_required
def index():
    salas = Recurso.query.all()
    turmas = Turma.query.all()
    return render_template(
        "professor.html", nome=current_user.nome, recursos=salas, turmas=turmas
    )


@main.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.index"))

    if request.method == "POST":
        professor = Professor.query.filter_by(nome=request.form.get("nome")).first()
        if professor and professor.verificar_senha(request.form.get("senha")):
            login_user(professor, remember=True)
            return redirect(url_for("main.index"))
        flash("Erro no login. Verifique as suas credenciais.")

    return render_template("login.html")


@main.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("main.login"))


# ==========================================================
# ROTAS DA API (Para o FullCalendar e o Modal)
# ==========================================================


@main.route("/api/eventos")
@login_required
def buscar_eventos_calendario():
    # Agrupa por data e conta quantos agendamentos existem em cada uma
    resultados = (
        db.session.query(Agendamento.data, func.count(Agendamento.id).label("total"))
        .group_by(Agendamento.data)
        .all()
    )

    eventos = []
    for data, total in resultados:
        eventos.append(
            {
                "title": f"📌 {total} Reserva(s)",
                "start": data.isoformat(),
                "allDay": True,
                "color": (
                    "#3b82f6" if total < 5 else "#ef4444"
                ),  # Fica vermelho se houver muitas reservas
            }
        )
    return jsonify(eventos)


@main.route("/api/agendamentos/dia/<data_str>")
@login_required
def agendamentos_do_dia(data_str):
    try:
        data_obj = datetime.strptime(data_str, "%Y-%m-%d").date()
    except ValueError:
        return jsonify([])

    agendamentos = Agendamento.query.filter_by(data=data_obj).all()
    agrupados = {}

    for ag in agendamentos:
        horario = HorarioAula.query.get(ag.horario_id)
        turma = Turma.query.get(ag.turma_id)
        prof = Professor.query.get(ag.id_professor)
        recurso = Recurso.query.get(ag.recurso_id)

        if not horario:
            continue

        # Cria uma chave única para agrupar reservas da mesma turma e mesmo horário
        chave = f"{ag.horario_id}_{ag.turma_id}"

        if chave not in agrupados:
            agrupados[chave] = {
                "reserva_id": ag.id,
                "horario": horario.descricao,
                "intervalo": f"{horario.hora_inicio.strftime('%H:%M')} - {horario.hora_fim.strftime('%H:%M')}",
                "professor": prof.nome if prof else "Desconhecido",
                "turma": turma.nome if turma else "Sem turma",
                "turno": turma.turno if turma else "",
                "recursos": [recurso.nome] if recurso else [],
                "pode_cancelar": ag.id_professor == current_user.id,
            }
        else:
            if recurso:
                agrupados[chave]["recursos"].append(recurso.nome)

    res = list(agrupados.values())
    res.sort(key=lambda x: x["intervalo"])
    return jsonify(res)


@main.route("/api/horarios/<int:recurso_id>/<data_str>")
@login_required
def horarios_disponiveis(recurso_id, data_str):
    try:
        data_obj = datetime.strptime(data_str, "%Y-%m-%d").date()
    except ValueError:
        return jsonify({"erro": "Data inválida"}), 400

    horarios = HorarioAula.query.order_by(HorarioAula.hora_inicio).all()
    resultado = []

    for h in horarios:
        reserva = Agendamento.query.filter_by(
            recurso_id=recurso_id, data=data_obj, horario_id=h.id
        ).first()

        ocupado_por = None
        reserva_id = None
        pode_cancelar = False

        if reserva:
            prof = Professor.query.get(reserva.id_professor)
            ocupado_por = prof.nome if prof else "Ocupado"
            reserva_id = reserva.id
            pode_cancelar = reserva.id_professor == current_user.id

        resultado.append(
            {
                "id": h.id,
                "descricao": h.descricao,
                "inicio": h.hora_inicio.strftime("%H:%M"),
                "fim": h.hora_fim.strftime("%H:%M"),
                "turno": h.turno,
                "ocupado_por": ocupado_por,
                "reserva_id": reserva_id,
                "pode_cancelar": pode_cancelar,
            }
        )
    return jsonify(resultado)


# ==========================================================
# NOVA ROTA: INTELIGÊNCIA DE FILTRAGEM DE TURMAS
# ==========================================================
@main.route("/api/turmas_validas/<int:recurso_id>/<data_str>/<int:horario_id>")
@login_required
def turmas_validas(recurso_id, data_str, horario_id):
    try:
        data_obj = datetime.strptime(data_str, "%Y-%m-%d").date()
    except ValueError:
        return jsonify([])

    horario = HorarioAula.query.get(horario_id)
    recurso_desejado = Recurso.query.get(recurso_id)

    if not horario or not recurso_desejado:
        return jsonify([])

    deseja_equipamento = eh_equipamento(recurso_desejado)
    turmas_turno = Turma.query.filter_by(turno=horario.turno).all()

    # Verifica se o professor já tem uma aula noutra turma neste horário
    reserva_prof = Agendamento.query.filter_by(
        data=data_obj, horario_id=horario_id, id_professor=current_user.id
    ).first()

    turmas_permitidas = []

    for t in turmas_turno:
        # Regra 1: Se o professor já está a dar aula a OUTRA turma, não pode escolher esta
        if reserva_prof and reserva_prof.turma_id != t.id:
            continue

        # Regra 2: Se deseja uma SALA, a turma não pode já ter outra SALA neste horário
        if not deseja_equipamento:
            reservas_desta_turma = Agendamento.query.filter_by(
                data=data_obj, horario_id=horario_id, turma_id=t.id
            ).all()

            ja_tem_sala = any(
                not eh_equipamento(Recurso.query.get(res.recurso_id))
                for res in reservas_desta_turma
            )
            if ja_tem_sala:
                continue

        # Regra 3: A turma já reservou exatamente ESTE recurso? (Impede duplicados na mesma turma)
        ja_tem_este_recurso = Agendamento.query.filter_by(
            data=data_obj, horario_id=horario_id, turma_id=t.id, recurso_id=recurso_id
        ).first()
        if ja_tem_este_recurso:
            continue

        # Se passou em todas as regras, a turma é válida!
        turmas_permitidas.append({"id": t.id, "nome": t.nome, "turno": t.turno})

    return jsonify(turmas_permitidas)


# ==========================================================
# ROTA DE RESERVA E CANCELAMENTO
# ==========================================================
@main.route("/api/reservar", methods=["POST"])
@login_required
def fazer_reserva():
    dados = request.get_json()
    recurso_id = dados.get("recurso_id")
    data_str = dados.get("data")
    horario_id = dados.get("horario_id")
    turma_id = int(dados.get("turma_id"))

    try:
        data_obj = datetime.strptime(data_str, "%Y-%m-%d").date()
    except ValueError:
        return jsonify({"sucesso": False, "erro": "Formato de data inválido."})

    turma = Turma.query.get(turma_id)
    horario = HorarioAula.query.get(horario_id)
    recurso_desejado = Recurso.query.get(recurso_id)

    if not turma or not horario or not recurso_desejado:
        return jsonify({"sucesso": False, "erro": "Dados enviados são inválidos."})

    # Verificação de segurança 1: Alguém já apanhou este recurso neste milissegundo?
    existe_recurso = Agendamento.query.filter_by(
        recurso_id=recurso_id, data=data_obj, horario_id=horario_id
    ).first()

    if existe_recurso:
        return jsonify(
            {
                "sucesso": False,
                "erro": f"Lamentamos! O recurso '{recurso_desejado.nome}' acabou de ser reservado por outro professor.",
            }
        )

    # Verificação de segurança 2: O professor está a tentar clonar-se?
    reservas_prof = Agendamento.query.filter_by(
        data=data_obj, horario_id=horario_id, id_professor=current_user.id
    ).all()

    for res in reservas_prof:
        if res.turma_id != turma_id:
            return jsonify(
                {
                    "sucesso": False,
                    "erro": "Não pode estar em duas turmas diferentes ao mesmo tempo.",
                }
            )

    # Verificação de segurança 3: A turma já tem uma sala?
    deseja_equipamento = eh_equipamento(recurso_desejado)
    reservas_turma = Agendamento.query.filter_by(
        data=data_obj, horario_id=horario_id, turma_id=turma_id
    ).all()

    for res in reservas_turma:
        rec_existente = Recurso.query.get(res.recurso_id)
        if not deseja_equipamento and not eh_equipamento(rec_existente):
            return jsonify(
                {
                    "sucesso": False,
                    "erro": f"A turma já se encontra no(a) '{rec_existente.nome}'. Não é possível ocupar duas salas simultaneamente.",
                }
            )

    # Tudo válido! Gravar na base de dados.
    try:
        nova_reserva = Agendamento(
            id_professor=current_user.id,
            recurso_id=recurso_id,
            turma_id=turma_id,
            horario_id=horario_id,
            data=data_obj,
        )
        db.session.add(nova_reserva)
        db.session.commit()
        return jsonify({"sucesso": True})
    except Exception as e:
        db.session.rollback()
        return jsonify(
            {"sucesso": False, "erro": "Erro interno do servidor ao gravar a reserva."}
        )


@main.route("/api/reservar/<int:id>", methods=["DELETE"])
@login_required
def cancelar_reserva(id):
    reserva = Agendamento.query.get_or_404(id)

    if reserva.id_professor != current_user.id:
        return (
            jsonify(
                {
                    "sucesso": False,
                    "erro": "Não tem permissão para cancelar esta reserva.",
                }
            ),
            403,
        )

    try:
        db.session.delete(reserva)
        db.session.commit()
        return jsonify({"sucesso": True})
    except Exception as e:
        db.session.rollback()
        return jsonify({"sucesso": False, "erro": str(e)}), 500
