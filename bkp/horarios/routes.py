from datetime import datetime
from flask import render_template, request, redirect, url_for, flash, abort
from flask_login import login_required, current_user
from . import bp
from app import db, Horario, Aluno

def _pode_gerenciar():
    return current_user.is_authenticated and current_user.papel in ("DIRETORIA", "PROFESSOR")

def _parse_time_str(s: str):
    if not s:
        return None
    try:
        t = datetime.strptime(s.strip(), "%H:%M").time()
        return t.hour * 60 + t.minute
    except Exception:
        return None

def _display(hi: str, hf: str) -> str:
    hi = (hi or "").strip()
    hf = (hf or "").strip()
    return f"{hi} - {hf}" if (hi and hf) else (hi or hf or "")

@bp.route("/")
@login_required
def listar():
    horarios = Horario.query.order_by(Horario.hora_inicio.asc().nullslast(), Horario.nome.asc().nullslast()).all()

    alunos_por_horario = {}
    if horarios:
        nomes = [h.nome for h in horarios if h.nome]
        if nomes:
            alunos = Aluno.query.filter(Aluno.horario_resumo.in_(nomes)).order_by(Aluno.nome.asc()).all()
            mapa_nome_to_ids = {}
            for h in horarios:
                if h.nome:
                    mapa_nome_to_ids.setdefault(h.nome, []).append(h.id)
            for a in alunos:
                ids = mapa_nome_to_ids.get(a.horario_resumo, [])
                for hid in ids:
                    alunos_por_horario.setdefault(hid, []).append(a)

    return render_template("horarios_list.html", horarios=horarios, alunos_por_horario=alunos_por_horario)

@bp.route("/novo", methods=["GET", "POST"])
@login_required
def novo():
    if not _pode_gerenciar():
        abort(403)
    if request.method == "POST":
        hi = (request.form.get("hora_inicio") or "").strip()
        hf = (request.form.get("hora_fim") or "").strip()

        if not hi or not hf:
            flash("Informe a hora de início e a hora de fim.", "warning")
            return render_template("horario_form.html")

        m_ini = _parse_time_str(hi)
        m_fim = _parse_time_str(hf)
        if m_ini is None or m_fim is None:
            flash("Formato inválido. Use HH:MM (ex.: 07:30).", "warning")
            return render_template("horario_form.html", hi=hi, hf=hf)
        if m_fim <= m_ini:
            flash("A hora fim deve ser MAIOR que a hora início.", "warning")
            return render_template("horario_form.html", hi=hi, hf=hf)

        nome_display = _display(hi, hf)
        exists = Horario.query.filter(Horario.nome.ilike(nome_display)).first()
        if exists:
            flash("Já existe um horário com esse intervalo.", "warning")
            return render_template("horario_form.html", hi=hi, hf=hf)

        h = Horario(
            hora_inicio=hi, hora_fim=hf,
            inicio=hi, fim=hf,                 # <<< LEGADO: evita NOT NULL
            nome=nome_display, hora_texto=nome_display
        )
        db.session.add(h)
        db.session.commit()
        flash("Horário cadastrado.", "success")
        return redirect(url_for("horarios.listar"))
    return render_template("horario_form.html")

@bp.route("/<int:id>/editar", methods=["GET", "POST"])
@login_required
def editar(id: int):
    if not _pode_gerenciar():
        abort(403)
    h = Horario.query.get_or_404(id)
    if request.method == "POST":
        hi = (request.form.get("hora_inicio") or "").strip()
        hf = (request.form.get("hora_fim") or "").strip()

        if not hi or not hf:
            flash("Informe a hora de início e a hora de fim.", "warning")
            return render_template("horario_form.html", h=h, hi=hi, hf=hf)

        m_ini = _parse_time_str(hi)
        m_fim = _parse_time_str(hf)
        if m_ini is None or m_fim is None:
            flash("Formato inválido. Use HH:MM (ex.: 07:30).", "warning")
            return render_template("horario_form.html", h=h, hi=hi, hf=hf)
        if m_fim <= m_ini:
            flash("A hora fim deve ser MAIOR que a hora início.", "warning")
            return render_template("horario_form.html", h=h, hi=hi, hf=hf)

        nome_display = _display(hi, hf)
        exists = Horario.query.filter(Horario.nome.ilike(nome_display), Horario.id != h.id).first()
        if exists:
            flash("Já existe um horário com esse intervalo.", "warning")
            return render_template("horario_form.html", h=h, hi=hi, hf=hf)

        h.hora_inicio = hi
        h.hora_fim = hf
        h.inicio = hi      # <<< LEGADO
        h.fim = hf         # <<< LEGADO
        h.nome = nome_display
        h.hora_texto = nome_display
        db.session.commit()
        flash("Horário atualizado.", "success")
        return redirect(url_for("horarios.listar"))

    return render_template("horario_form.html", h=h, hi=h.hora_inicio or h.inicio or "", hf=h.hora_fim or h.fim or "")

@bp.route("/<int:id>/excluir", methods=["POST"])
@login_required
def excluir(id: int):
    if not _pode_gerenciar():
        abort(403)
    h = Horario.query.get_or_404(id)
    db.session.delete(h)
    db.session.commit()
    flash("Horário excluído.", "success")
    return redirect(url_for("horarios.listar"))
