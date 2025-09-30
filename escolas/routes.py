from flask import render_template, request, redirect, url_for, flash, abort
from flask_login import login_required, current_user
from . import bp
from models import db, Escola

def _pode_gerenciar():
    return current_user.is_authenticated and current_user.papel in ("DIRETORIA",)

@bp.route("/")
@login_required
def listar():
    q = (request.args.get("q") or "").strip()
    query = Escola.query
    if q:
        query = query.filter(Escola.nome.ilike(f"%{q}%"))
    itens = query.order_by(Escola.nome.asc()).all()
    return render_template("escolas_list.html", itens=itens)

@bp.route("/novo", methods=["GET", "POST"])
@login_required
def novo():
    if not _pode_gerenciar():
        abort(403)
    if request.method == "POST":
        nome = (request.form.get("nome") or "").strip()
        if not nome:
            flash("Informe o nome da escola.", "warning")
            return render_template("escola_form.html")
        if Escola.query.filter(Escola.nome.ilike(nome)).first():
            flash("Já existe uma escola com esse nome.", "warning")
            return render_template("escola_form.html")
        db.session.add(Escola(nome=nome))
        db.session.commit()
        flash("Escola cadastrada.", "success")
        return redirect(url_for("escolas.listar"))
    return render_template("escola_form.html")

@bp.route("/<int:id>/editar", methods=["GET", "POST"])
@login_required
def editar(id: int):
    if not _pode_gerenciar():
        abort(403)
    e = Escola.query.get_or_404(id)
    if request.method == "POST":
        nome = (request.form.get("nome") or "").strip()
        if not nome:
            flash("Informe o nome da escola.", "warning")
            return render_template("escola_form.html", e=e)
        existente = Escola.query.filter(Escola.nome.ilike(nome), Escola.id != e.id).first()
        if existente:
            flash("Já existe outra escola com esse nome.", "warning")
            return render_template("escola_form.html", e=e)
        e.nome = nome
        db.session.commit()
        flash("Escola atualizada.", "success")
        return redirect(url_for("escolas.listar"))
    return render_template("escola_form.html", e=e)

@bp.route("/<int:id>/excluir", methods=["POST"])
@login_required
def excluir(id: int):
    if not _pode_gerenciar():
        abort(403)
    e = Escola.query.get_or_404(id)
    db.session.delete(e)
    db.session.commit()
    flash("Escola excluída.", "success")
    return redirect(url_for("escolas.listar"))
