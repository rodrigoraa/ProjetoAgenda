from datetime import datetime, timedelta
import re

from flask import Blueprint, flash, jsonify, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required, login_user, logout_user

from app.models import Agendamento, HorarioAula, Professor, Recurso, Turma, db

main = Blueprint("main", __name__)


def normalizar_matricula(valor):
    texto = (valor or "").strip()
    somente_digitos = re.sub(r"\D", "", texto)
    if len(somente_digitos) == 11:
        return somente_digitos
    return texto.upper()


def eh_equipamento(rec):
    if not rec:
        return False
    tipo = rec.tipo.lower() if rec.tipo else ""
    nome = rec.nome.lower() if rec.nome else ""
    return (
        "equipamento" in tipo or "caixa" in nome or "projetor" in nome or "tv" in nome
    )


def categoria_recurso(rec):
    if not rec:
        return "outro"

    tipo = (rec.tipo or "").strip().lower()
    nome = (rec.nome or "").strip().lower()

    if "projetor" in nome or "data show" in nome or "datashow" in nome:
        return "projetor"
    if "caixa" in nome or "som" in nome or "microfone" in nome:
        return "audio"
    if "tv" in nome or "televis" in nome:
        return "tv"
    if "notebook" in nome:
        return "notebook"
    if "computador" in nome or "pc" in nome:
        return "computador"

    if "laborat" in tipo or "laborat" in nome:
        return "laboratorio"
    # Ambientes que funcionam como "sala" (não contam como dispositivo extra).
    if "biblioteca" in tipo or "biblioteca" in nome:
        return "sala"
    if "quadra" in tipo or "espa" in tipo:
        return "espaco"
    if "sala" in tipo or "sala" in nome:
        return "sala"
    if "equipamento" in tipo:
        return tipo or "equipamento"

    return tipo or nome or "outro"


def obter_turmas_validas_para_recurso(recurso_id, data_obj, horario_id, professor_id=None):
    horario = HorarioAula.query.get(horario_id)
    recurso_desejado = Recurso.query.get(recurso_id)
    professor_id = professor_id or current_user.id

    if not horario or not recurso_desejado:
        return []

    deseja_equipamento = eh_equipamento(recurso_desejado)
    turmas_turno = Turma.query.filter_by(turno=horario.turno).all()
    reserva_prof = Agendamento.query.filter_by(
        data=data_obj, horario_id=horario_id, id_professor=professor_id
    ).first()

    turmas_permitidas = []

    for t in turmas_turno:
        if reserva_prof and reserva_prof.turma_id != t.id:
            continue

        reservas_desta_turma = Agendamento.query.filter_by(
            data=data_obj, horario_id=horario_id, turma_id=t.id
        ).all()

        professor_desta_turma = next(
            (res.id_professor for res in reservas_desta_turma if res.id_professor),
            None,
        )
        if professor_desta_turma and professor_desta_turma != professor_id:
            continue

        if not deseja_equipamento:
            ja_tem_sala = any(
                not eh_equipamento(Recurso.query.get(res.recurso_id))
                for res in reservas_desta_turma
            )
            if ja_tem_sala:
                continue

        ja_tem_este_recurso = Agendamento.query.filter_by(
            data=data_obj, horario_id=horario_id, turma_id=t.id, recurso_id=recurso_id
        ).first()
        if ja_tem_este_recurso:
            continue

        turmas_permitidas.append({"id": t.id, "nome": t.nome, "turno": t.turno})

    return turmas_permitidas


def montar_agendamentos_agrupados(agendamentos):
    agrupados = {}
    for agendamento in agendamentos:
        horario = HorarioAula.query.get(agendamento.horario_id)
        turma = Turma.query.get(agendamento.turma_id)
        recurso = Recurso.query.get(agendamento.recurso_id)
        professor = Professor.query.get(agendamento.id_professor)
        if not horario:
            continue

        chave = (
            f"{agendamento.data.isoformat()}_"
            f"{agendamento.horario_id}_{agendamento.turma_id}_{agendamento.id_professor}"
        )
        if chave not in agrupados:
            agrupados[chave] = {
                "reserva_id": agendamento.id,
                "data": agendamento.data,
                "data_iso": agendamento.data.isoformat(),
                "data_formatada": agendamento.data.strftime("%d/%m/%Y"),
                "horario": horario.descricao,
                "horario_id": agendamento.horario_id,
                "intervalo": (
                    f"{horario.hora_inicio.strftime('%H:%M')} - "
                    f"{horario.hora_fim.strftime('%H:%M')}"
                ),
                "professor": professor.nome if professor else "Professor",
                "professor_id": agendamento.id_professor,
                "turma": turma.nome if turma else "Turma",
                "turma_id": agendamento.turma_id,
                "turno": horario.turno,
                "pode_cancelar": current_user.is_admin or agendamento.id_professor == current_user.id,
                "recursos": [],
            }

        if recurso and recurso.nome:
            agrupados[chave]["recursos"].append(recurso.nome)

    resultado = list(agrupados.values())
    for item in resultado:
        item["recursos"] = sorted(set(item["recursos"]))
    resultado.sort(key=lambda item: (item["data"], item["intervalo"], item["professor"], item["turma"]))
    return resultado


@main.route("/")
@login_required
def index():
    hoje = datetime.now().date()
    hora_atual = datetime.now().hour
    if hora_atual < 12:
        saudacao = "Bom dia"
    elif hora_atual < 18:
        saudacao = "Boa tarde"
    else:
        saudacao = "Boa noite"

    salas = Recurso.query.all()
    horarios = HorarioAula.query.order_by(HorarioAula.turno, HorarioAula.hora_inicio).all()
    agendamentos_hoje = Agendamento.query.filter_by(data=hoje).all()
    agendamentos_do_dia = montar_agendamentos_agrupados(agendamentos_hoje)
    futuros_agendamentos = montar_agendamentos_agrupados(
        Agendamento.query.filter(Agendamento.data > hoje)
        .order_by(Agendamento.data.asc(), Agendamento.horario_id.asc())
        .limit(80)
        .all()
    )[:10]

    meses_pt = [
        "janeiro",
        "fevereiro",
        "março",
        "abril",
        "maio",
        "junho",
        "julho",
        "agosto",
        "setembro",
        "outubro",
        "novembro",
        "dezembro",
    ]
    dias_semana_pt = [
        "segunda-feira",
        "terça-feira",
        "quarta-feira",
        "quinta-feira",
        "sexta-feira",
        "sábado",
        "domingo",
    ]
    reservas_por_horario = {}
    for agendamento in agendamentos_hoje:
        horario = HorarioAula.query.get(agendamento.horario_id)
        turma = Turma.query.get(agendamento.turma_id)
        professor = Professor.query.get(agendamento.id_professor)
        recurso = Recurso.query.get(agendamento.recurso_id)

        if not horario:
            continue

        reservas_por_horario.setdefault(horario.id, {})
        chave = f"{agendamento.turma_id}_{agendamento.id_professor}"
        if chave not in reservas_por_horario[horario.id]:
            reservas_por_horario[horario.id][chave] = {
                "reserva_id": agendamento.id,
                "professor": professor.nome if professor else "Professor",
                "turma": turma.nome if turma else "Turma",
                "recursos": [],
                "pode_cancelar": current_user.is_admin or agendamento.id_professor == current_user.id,
            }

        if recurso and recurso.nome:
            reservas_por_horario[horario.id][chave]["recursos"].append(recurso.nome)

    turnos_ordenados = ["Matutino", "Vespertino", "Noturno"]
    grade_hoje = []
    for turno in turnos_ordenados:
        aulas_turno = []
        for horario in horarios:
            if horario.turno != turno:
                continue
            aulas_turno.append(
                {
                    "id": horario.id,
                    "descricao": horario.descricao,
                    "intervalo": (
                        f"{horario.hora_inicio.strftime('%H:%M')} - "
                        f"{horario.hora_fim.strftime('%H:%M')}"
                    ),
                    "reservas": list(reservas_por_horario.get(horario.id, {}).values()),
                }
            )

        if aulas_turno:
            grade_hoje.append({"turno": turno, "aulas": aulas_turno})

    inicio_insights = hoje - timedelta(days=29)
    agendamentos_periodo = Agendamento.query.filter(
        Agendamento.data >= inicio_insights,
        Agendamento.data <= hoje,
    ).all()
    total_reservas_periodo = len(agendamentos_periodo)
    total_slots_periodo = max(len(salas) * len(horarios) * 30, 1)
    taxa_ocupacao = round((total_reservas_periodo / total_slots_periodo) * 100, 1)
    professores_ativos = len({ag.id_professor for ag in agendamentos_periodo})

    def ordenar_ranking(contagem):
        return [
            {"nome": nome, "total": total}
            for nome, total in sorted(contagem.items(), key=lambda item: (-item[1], item[0]))
        ]

    por_periodo = {}
    por_professor = {}
    por_recurso = {}
    por_turma = {}

    for agendamento in agendamentos_periodo:
        horario = HorarioAula.query.get(agendamento.horario_id)
        professor = Professor.query.get(agendamento.id_professor)
        recurso = Recurso.query.get(agendamento.recurso_id)
        turma = Turma.query.get(agendamento.turma_id)

        turno = horario.turno if horario else "Sem período"
        nome_professor = professor.nome if professor else "Professor"
        nome_recurso = recurso.nome if recurso else "Recurso"
        nome_turma = turma.nome if turma else "Turma"

        por_periodo[turno] = por_periodo.get(turno, 0) + 1
        por_professor[nome_professor] = por_professor.get(nome_professor, 0) + 1
        por_recurso[nome_recurso] = por_recurso.get(nome_recurso, 0) + 1
        por_turma[nome_turma] = por_turma.get(nome_turma, 0) + 1

    insights = {
        "dias": 30,
        "total_reservas": total_reservas_periodo,
        "taxa_ocupacao": taxa_ocupacao,
        "professores_ativos": professores_ativos,
        "turmas": Turma.query.count(),
        "por_periodo": ordenar_ranking(por_periodo),
        "por_professor": ordenar_ranking(por_professor)[:8],
        "por_recurso": ordenar_ranking(por_recurso)[:8],
        "por_turma": ordenar_ranking(por_turma)[:8],
        "maior_total": max(
            list(por_periodo.values())
            + list(por_professor.values())
            + list(por_recurso.values())
            + list(por_turma.values())
            + [1]
        ),
    }

    return render_template(
        "professor.html",
        nome=current_user.nome,
        saudacao=saudacao,
        recursos=salas,
        professores=Professor.query.order_by(Professor.nome).all(),
        grade_hoje=grade_hoje,
        meus_agendamentos=agendamentos_do_dia,
        futuros_agendamentos=futuros_agendamentos,
        data_hoje=hoje.strftime("%d/%m/%Y"),
        data_hoje_iso=hoje.isoformat(),
        dia_hoje=hoje.day,
        data_hoje_extenso=f"{hoje.day} de {meses_pt[hoje.month - 1]}",
        dia_semana_hoje=dias_semana_pt[hoje.weekday()],
        mes_ano_hoje=f"{meses_pt[hoje.month - 1].capitalize()} de {hoje.year}",
        insights=insights,
    )


@main.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.index"))

    if request.method == "POST":
        matricula = normalizar_matricula(request.form.get("matricula"))
        professor = Professor.query.filter_by(matricula=matricula).first()

        if not matricula:
            flash("Informe sua matrícula para continuar.", "danger")
            return render_template(
                "login.html",
                matricula_input=matricula,
            )

        if professor:
            if professor.is_admin:
                senha = request.form.get("senha") or ""
                if not senha:
                    flash("Informe a senha do administrador para continuar.", "warning")
                    return render_template(
                        "login.html",
                        matricula_input=matricula,
                    )
                if professor.verificar_senha(senha):
                    session.clear()
                    session.permanent = True
                    login_user(professor, remember=True)
                    flash(f"Bem-vindo, Admin {professor.nome}!", "success")
                    return redirect(url_for("admin.dashboard"))

                flash("Senha incorreta para administrador.", "danger")
                return render_template(
                    "login.html",
                    matricula_input=matricula,
                )

            session.clear()
            session.permanent = True
            login_user(professor, remember=True)
            flash(f"Bem-vindo, Prof. {professor.nome}!", "success")
            return redirect(url_for("main.index"))

        flash("Matrícula não encontrada. Consulte a administração.", "danger")

    return render_template("login.html")


@main.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    session.clear()
    return redirect(url_for("main.login"))


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

        chave = f"{ag.horario_id}_{ag.turma_id}"

        if chave not in agrupados:
            agrupados[chave] = {
                "reserva_id": ag.id,
                "horario": horario.descricao,
                "horario_id": ag.horario_id,
                "intervalo": (
                    f"{horario.hora_inicio.strftime('%H:%M')} - "
                    f"{horario.hora_fim.strftime('%H:%M')}"
                ),
                "professor": prof.nome if prof else "Desconhecido",
                "professor_id": ag.id_professor,
                "turma": turma.nome if turma else "Sem turma",
                "turma_id": ag.turma_id,
                "turno": horario.turno,
                "recursos": [recurso.nome] if recurso else [],
                "pode_cancelar": current_user.is_admin or ag.id_professor == current_user.id,
            }
        elif recurso:
            agrupados[chave]["recursos"].append(recurso.nome)

    res = list(agrupados.values())
    res.sort(key=lambda x: x["intervalo"])
    return jsonify(res)


@main.route("/api/agendamentos/futuros")
@login_required
def agendamentos_futuros():
    hoje = datetime.now().date()
    agendamentos = (
        Agendamento.query.filter(Agendamento.data > hoje)
        .order_by(Agendamento.data.asc(), Agendamento.horario_id.asc())
        .limit(80)
        .all()
    )
    return jsonify(montar_agendamentos_agrupados(agendamentos)[:10])


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
            pode_cancelar = current_user.is_admin or reserva.id_professor == current_user.id

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


@main.route("/api/recursos_extras_disponiveis/<data_str>/<int:horario_id>/<int:sala_id>")
@login_required
def recursos_extras_disponiveis_no_horario(data_str, horario_id, sala_id):
    """
    Para alocação em uma aula específica: mantém a sala/lab selecionada e
    lista apenas recursos "extras" (ex: projetor, audio, tv), excluindo sala/laboratório.
    """
    try:
        data_obj = datetime.strptime(data_str, "%Y-%m-%d").date()
    except ValueError:
        return jsonify([])

    recursos = Recurso.query.order_by(Recurso.nome).all()
    disponiveis = []

    for recurso in recursos:
        if recurso.id != sala_id and categoria_recurso(recurso) in ("sala", "laboratorio"):
            continue

        reserva = Agendamento.query.filter_by(
            recurso_id=recurso.id, data=data_obj, horario_id=horario_id
        ).first()
        if reserva and recurso.id != sala_id:
            continue

        disponiveis.append(
            {
                "id": recurso.id,
                "nome": recurso.nome,
                "icone": recurso.icone or "bi-door-open",
            }
        )

    return jsonify(disponiveis)


@main.route("/api/turmas_validas/<int:recurso_id>/<data_str>/<int:horario_id>")
@login_required
def turmas_validas(recurso_id, data_str, horario_id):
    try:
        data_obj = datetime.strptime(data_str, "%Y-%m-%d").date()
    except ValueError:
        return jsonify([])

    professor_id = current_user.id
    if current_user.is_admin and request.args.get("professor_id"):
        try:
            professor_id = int(request.args.get("professor_id"))
        except (TypeError, ValueError):
            return jsonify([])

    return jsonify(
        obter_turmas_validas_para_recurso(recurso_id, data_obj, horario_id, professor_id)
    )


@main.route("/api/turmas_validas_multiplos", methods=["POST"])
@login_required
def turmas_validas_multiplos():
    dados = request.get_json() or {}
    recurso_ids = dados.get("recurso_ids") or []
    data_str = dados.get("data")
    horario_id = dados.get("horario_id")
    professor_id = dados.get("professor_id") if current_user.is_admin else current_user.id

    try:
        data_obj = datetime.strptime(data_str, "%Y-%m-%d").date()
        horario_id = int(horario_id)
        recurso_ids = [int(recurso_id) for recurso_id in recurso_ids if str(recurso_id).strip()]
        professor_id = int(professor_id)
    except (TypeError, ValueError):
        return jsonify([])

    if not recurso_ids:
        return jsonify([])

    turmas_por_recurso = [
        obter_turmas_validas_para_recurso(recurso_id, data_obj, horario_id, professor_id)
        for recurso_id in recurso_ids
    ]
    ids_comuns = set(item["id"] for item in turmas_por_recurso[0])

    for turmas in turmas_por_recurso[1:]:
        ids_comuns &= {item["id"] for item in turmas}

    return jsonify([item for item in turmas_por_recurso[0] if item["id"] in ids_comuns])


@main.route("/api/reservar", methods=["POST"])
@login_required
def fazer_reserva():
    dados = request.get_json() or {}
    recurso_ids = dados.get("recurso_ids") or []
    recurso_id = dados.get("recurso_id")
    data_str = dados.get("data")
    horario_id = dados.get("horario_id")
    professor_id = dados.get("professor_id") if current_user.is_admin else current_user.id

    if recurso_id is not None and not recurso_ids:
        recurso_ids = [recurso_id]

    try:
        turma_id = int(dados.get("turma_id"))
        horario_id = int(horario_id)
        professor_id = int(professor_id)
        recurso_ids = [int(item) for item in recurso_ids if str(item).strip()]
        data_obj = datetime.strptime(data_str, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return jsonify({"sucesso": False, "erro": "Dados enviados são inválidos."})

    if data_obj < datetime.now().date():
        return jsonify({"sucesso": False, "erro": "Não é possível reservar datas passadas."})

    if not recurso_ids:
        return jsonify({"sucesso": False, "erro": "Selecione ao menos um recurso."})

    turma = Turma.query.get(turma_id)
    horario = HorarioAula.query.get(horario_id)
    professor_responsavel = Professor.query.get(professor_id)
    recursos_desejados = Recurso.query.filter(Recurso.id.in_(recurso_ids)).all()

    if (
        not turma
        or not horario
        or not professor_responsavel
        or len(recursos_desejados) != len(set(recurso_ids))
    ):
        return jsonify({"sucesso": False, "erro": "Dados enviados são inválidos."})

    reservas_prof = Agendamento.query.filter_by(
        data=data_obj, horario_id=horario_id, id_professor=professor_id
    ).all()

    for res in reservas_prof:
        if res.turma_id != turma_id:
            return jsonify(
                {
                    "sucesso": False,
                    "erro": "Não pode estar em duas turmas diferentes ao mesmo tempo.",
                }
            )

    reservas_turma = Agendamento.query.filter_by(
        data=data_obj, horario_id=horario_id, turma_id=turma_id
    ).all()

    for res in reservas_turma:
        if res.id_professor != professor_id:
            return jsonify(
                {
                    "sucesso": False,
                    "erro": (
                        "Esta turma já possui reserva com outro professor neste horário. "
                        "Não é permitido dividir a mesma aula entre professores diferentes."
                    ),
                }
            )

    recursos_desejados_unicos = []
    ids_vistos = set()
    for recurso in recursos_desejados:
        if recurso.id not in ids_vistos:
            recursos_desejados_unicos.append(recurso)
            ids_vistos.add(recurso.id)

    categorias_novas = {}
    for recurso in recursos_desejados_unicos:
        categoria = categoria_recurso(recurso)
        if categoria in categorias_novas:
            return jsonify(
                {
                    "sucesso": False,
                    "erro": (
                        f"Selecione apenas um recurso do tipo '{categoria}'. "
                        "Você pode combinar tipos diferentes na mesma aula."
                    ),
                }
            )
        categorias_novas[categoria] = recurso

    # Regra: por aula, permitir sala/laboratório + até 2 recursos extras (projetor, audio, tv, etc).
    extras_selecionados = [
        rec
        for rec in recursos_desejados_unicos
        if categoria_recurso(rec) not in ("sala", "laboratorio")
    ]
    if len(extras_selecionados) > 2:
        return jsonify(
            {
                "sucesso": False,
                "erro": "Selecione no máximo 2 recursos extras (além da sala/laboratório).",
            }
        )

    for res in reservas_turma:
        rec_existente = Recurso.query.get(res.recurso_id)
        if rec_existente and categoria_recurso(rec_existente) in categorias_novas:
            return jsonify(
                {
                    "sucesso": False,
                    "erro": (
                        f"A turma já possui um recurso do tipo '{categoria_recurso(rec_existente)}' "
                        f"neste horário: '{rec_existente.nome}'."
                    ),
                }
            )
        if res.recurso_id in ids_vistos:
            return jsonify(
                {
                    "sucesso": False,
                    "erro": "Um dos recursos selecionados já está reservado para esta turma.",
                }
            )

    for recurso_desejado in recursos_desejados_unicos:
        existe_recurso = Agendamento.query.filter_by(
            recurso_id=recurso_desejado.id, data=data_obj, horario_id=horario_id
        ).first()

        if existe_recurso:
            return jsonify(
                {
                    "sucesso": False,
                    "erro": (
                        f"Lamentamos! O recurso '{recurso_desejado.nome}' acabou de ser "
                        "reservado por outro professor."
                    ),
                }
            )

    try:
        for recurso_desejado in recursos_desejados_unicos:
            nova_reserva = Agendamento(
                id_professor=professor_id,
                recurso_id=recurso_desejado.id,
                turma_id=turma_id,
                horario_id=horario_id,
                data=data_obj,
            )
            db.session.add(nova_reserva)
        db.session.commit()
        return jsonify({"sucesso": True})
    except Exception:
        db.session.rollback()
        return jsonify(
            {"sucesso": False, "erro": "Erro interno do servidor ao gravar a reserva."}
        )


@main.route("/api/reservar/<int:id>", methods=["DELETE"])
@login_required
def cancelar_reserva(id):
    reserva = Agendamento.query.get_or_404(id)

    if not current_user.is_admin and reserva.id_professor != current_user.id:
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


@main.route("/api/reservar_grupo", methods=["DELETE"])
@login_required
def cancelar_reserva_grupo():
    dados = request.get_json() or {}
    data_str = dados.get("data")
    horario_id = dados.get("horario_id")
    turma_id = dados.get("turma_id")
    professor_id = dados.get("professor_id")

    try:
        data_obj = datetime.strptime(data_str, "%Y-%m-%d").date()
        horario_id = int(horario_id)
        turma_id = int(turma_id)
    except (TypeError, ValueError):
        return jsonify({"sucesso": False, "erro": "Dados inválidos."}), 400

    filtro = {
        "data": data_obj,
        "horario_id": horario_id,
        "turma_id": turma_id,
    }
    if current_user.is_admin and professor_id:
        try:
            filtro["id_professor"] = int(professor_id)
        except (TypeError, ValueError):
            return jsonify({"sucesso": False, "erro": "Dados inválidos."}), 400
    else:
        filtro["id_professor"] = current_user.id

    reservas = Agendamento.query.filter_by(**filtro).all()

    if not reservas:
        return jsonify({"sucesso": False, "erro": "Nenhuma reserva encontrada."}), 404

    try:
        for res in reservas:
            db.session.delete(res)
        db.session.commit()
        return jsonify({"sucesso": True})
    except Exception:
        db.session.rollback()
        return (
            jsonify({"sucesso": False, "erro": "Erro interno ao cancelar a reserva."}),
            500,
        )
