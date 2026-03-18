from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_user, logout_user, login_required, current_user
from app.models import db, Professor, Recurso, Agendamento, HorarioAula, Turma
from datetime import datetime

main = Blueprint("main", __name__)


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
            login_user(professor)
            return redirect(url_for("main.index"))
        flash("Erro no login. Verifique as suas credenciais.")
    return render_template("login.html")


@main.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("main.login"))


@main.route("/api/horarios/<int:recurso_id>/<data>")
@login_required
def buscar_horarios(recurso_id, data):
    try:
        data_obj = datetime.strptime(data, "%Y-%m-%d").date()
    except ValueError:
        return jsonify({"erro": "Formato de data inválido"}), 400

    todos = HorarioAula.query.order_by(HorarioAula.hora_inicio).all()
    ocupados = Agendamento.query.filter_by(recurso_id=recurso_id, data=data_obj).all()

    res = []
    for h in todos:
        prof_nome = None
        pode_cancelar = False
        reserva_id = None
        
        for oc in ocupados:
            if oc.horario_id == h.id:
                p = Professor.query.get(oc.id_professor)
                prof_nome = p.nome if p else "Ocupado"
                reserva_id = oc.id
                # Verifica se o professor atual é o dono ou admin
                if oc.id_professor == current_user.id or current_user.is_admin:
                    pode_cancelar = True

        res.append(
            {
                "id": h.id,
                "descricao": h.descricao,
                "inicio": h.hora_inicio.strftime("%H:%M"),
                "fim": h.hora_fim.strftime("%H:%M"),
                "turno": h.turno,  # <-- CRUCIAL: Envia o turno para o JS
                "ocupado_por": prof_nome,
                "pode_cancelar": pode_cancelar,
                "reserva_id": reserva_id
            }
        )
    return jsonify(res)


@main.route("/api/reservar", methods=["POST"])
@login_required
def fazer_reserva():
    dados = request.get_json()
    recurso_id = dados.get("recurso_id")
    data_str = dados.get("data")
    horario_id = dados.get("horario_id")
    turma_id = dados.get("turma_id")

    # --- 1. NOVA VALIDAÇÃO DE TURNO ---
    turma = Turma.query.get(turma_id)
    horario = HorarioAula.query.get(horario_id)
    
    if not turma or not horario:
        return jsonify({"sucesso": False, "erro": "Turma ou horário inválido."})
        
    if turma.turno != horario.turno:
        return jsonify({
            "sucesso": False, 
            "erro": f"Conflito de turnos! A turma selecionada é do turno {turma.turno}, mas o horário escolhido pertence ao turno {horario.turno}."
        })

    # --- 2. Verifica se alguém não reservou um segundo antes (Concorrência) ---
    existe = Agendamento.query.filter_by(
        recurso_id=recurso_id, data=data_str, horario_id=horario_id
    ).first()
    
    if existe:
        return jsonify({"sucesso": False, "erro": "Putz! Outro professor acabou de reservar este horário."})

    # --- 3. Salva a nova reserva ---
    try:
        data_obj = datetime.strptime(data_str, "%Y-%m-%d").date()
        nova_reserva = Agendamento(
            id_professor=current_user.id,
            recurso_id=recurso_id,
            turma_id=turma_id,
            horario_id=horario_id,
            data=data_obj,
            # Se você tiver um campo de status na reserva, adicione aqui. Caso contrário, ignore.
        )
        db.session.add(nova_reserva)
        db.session.commit()
        return jsonify({"sucesso": True})
    except Exception as e:
        db.session.rollback()
        return jsonify({"sucesso": False, "erro": f"Erro interno ao salvar: {str(e)}"})
        
@main.route("/api/reservar/<int:id>", methods=["DELETE"])
@login_required
def cancelar_reserva(id):
    reserva = Agendamento.query.get_or_404(id)
    
    # Validação de Segurança no Servidor: Barrar quem não é dono E não é admin
    if reserva.id_professor != current_user.id and not current_user.is_admin:
        return jsonify({"sucesso": False, "erro": "Você não tem permissão para cancelar esta reserva."})
        
    try:
        db.session.delete(reserva)
        db.session.commit()
        return jsonify({"sucesso": True})
    except Exception as e:
        db.session.rollback()
        return jsonify({"sucesso": False, "erro": "Erro ao cancelar a reserva."})
    
@main.route("/api/agendamentos/dia/<data>")
@login_required
def buscar_todos_agendamentos_dia(data):
    try:
        data_obj = datetime.strptime(data, "%Y-%m-%d").date()
        agendamentos = Agendamento.query.filter_by(data=data_obj).all()
        
        # Dicionário para agrupar: a chave será uma combinação única de horário + professor + turma
        agrupados = {}
        
        for ag in agendamentos:
            prof = Professor.query.get(ag.id_professor)
            recurso = Recurso.query.get(ag.recurso_id)
            horario = HorarioAula.query.get(ag.horario_id)
            turma = Turma.query.get(ag.turma_id)
            
            # Criamos uma chave única para identificar se é o mesmo "evento" de aula
            # (Mesmo professor, no mesmo horário, para a mesma turma)
            chave = f"{ag.horario_id}_{ag.id_professor}_{ag.turma_id}"
            
            if chave not in agrupados:
                agrupados[chave] = {
                    "professor": prof.nome if prof else "Desconhecido",
                    "recursos": [recurso.nome] if recurso else ["Excluído"], # Agora é uma lista!
                    "horario": horario.descricao if horario else "--",
                    "intervalo": f"{horario.hora_inicio.strftime('%H:%M')} - {horario.hora_fim.strftime('%H:%M')}",
                    "turma": turma.nome if turma else "Sem turma",
                    "turno": turma.turno if turma else ""
                }
            else:
                # Se a chave já existe, apenas adicionamos o novo recurso à lista
                if recurso:
                    agrupados[chave]["recursos"].append(recurso.nome)
        
        # Transformamos o dicionário de volta em uma lista para o JSON
        res = list(agrupados.values())
        
        # Ordenar por hora de início
        res.sort(key=lambda x: x['intervalo'])
        return jsonify(res)
    except Exception as e:
        return jsonify({"erro": str(e)}), 500
    
@main.route("/api/eventos")
@login_required
def buscar_eventos_calendario():
    from sqlalchemy import func
    # Agrupa por data e conta quantos agendamentos existem em cada uma
    resultados = db.session.query(
        Agendamento.data, 
        func.count(Agendamento.id).label('total')
    ).group_by(Agendamento.data).all()
    
    eventos = []
    for data, total in resultados:
        eventos.append({
            "title": f"📌 {total} Aula(s)",
            "start": data.isoformat(),
            "allDay": True,
            "color": "#3b82f6" if total < 5 else "#ef4444", # Muda para vermelho se estiver muito lotado
            "display": "block" # Garante que apareça como uma barra elegante
        })
    return jsonify(eventos)