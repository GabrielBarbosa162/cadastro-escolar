from flask import render_template, request, redirect, url_for, flash
from flask_login import login_required
from . import bp
from app import db, Horario, perm_required

@bp.route("/")
@login_required
def listar():
    # Ordena pelos campos existentes; não use "nome" nem "label" se não existem na tabela
    horarios = Horario.query.order_by(Horario.hora_inicio.asc(), Horario.hora_fim.asc()).all()
    return render_template("horarios/listar.html", horarios=horarios)

@bp.route("/novo", methods=["GET", "POST"])
@login_required
@perm_required("HORARIO_ADICIONAR")
def novo():
    if not _pode_gerenciar():
        abort(403)
    if request.method == "POST":
        hi = (request.form.get("hora_inicio") or "").strip()
        hf = (request.form.get("hora_fim") or "").strip()

        if not hora_inicio or not hora_fim:
            flash("Preencha hora início e hora fim.", "warning")
            return redirect(url_for("horarios.novo"))

        # Validação simples: fim > início (string HH:MM funciona para comparação lexicográfica)
        if hora_fim <= hora_inicio:
            flash("A hora fim deve ser maior que a hora início.", "warning")
            return redirect(url_for("horarios.novo"))

        h = Horario(hora_inicio=hora_inicio, hora_fim=hora_fim)
        db.session.add(h)
        db.session.commit()
        flash("Horário cadastrado com sucesso!", "success")
        return redirect(url_for("horarios.listar"))

    return render_template("horarios/form.html")

@bp.route("/<int:id>/editar", methods=["GET", "POST"])
@login_required
@perm_required("HORARIO_ADICIONAR")
def editar(id):
    h = db.session.get(Horario, id)
    if not h:
        flash("Horário não encontrado.", "warning")
        return redirect(url_for("horarios.listar"))

    if request.method == "POST":
        hora_inicio = (request.form.get("hora_inicio") or "").strip()
        hora_fim = (request.form.get("hora_fim") or "").strip()

        if not hora_inicio or not hora_fim:
            flash("Preencha hora início e hora fim.", "warning")
            return redirect(url_for("horarios.editar", id=id))

        if hora_fim <= hora_inicio:
            flash("A hora fim deve ser maior que a hora início.", "warning")
            return redirect(url_for("horarios.editar", id=id))

        h.hora_inicio = hora_inicio
        h.hora_fim = hora_fim
        db.session.commit()
        flash("Horário atualizado!", "success")
        return redirect(url_for("horarios.listar"))

    return render_template("horarios/form.html", horario=h)

@bp.route("/<int:id>/excluir", methods=["POST"])
@login_required
@perm_required("HORARIO_EXCLUIR")
def excluir(id):
    h = db.session.get(Horario, id)
    if not h:
        flash("Horário não encontrado.", "warning")
        return redirect(url_for("horarios.listar"))

    db.session.delete(h)
    db.session.commit()
    flash("Horário excluído.", "info")
    return redirect(url_for("horarios.listar"))
