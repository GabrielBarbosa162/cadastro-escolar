from flask import render_template, request, redirect, url_for, flash, abort
from flask_login import login_required, current_user
from . import bp
from app import db, Serie

def _pode_gerenciar():
    return current_user.is_authenticated and current_user.papel in ("DIRETORIA",)

@bp.route("/")
@login_required
def listar():
    q = (request.args.get("q") or "").strip()
    query = Serie.query
    if q:
        query = query.filter(Serie.nome.ilike(f"%{q}%"))
    itens = query.order_by(Serie.nome.asc()).all()
    return render_template("series_list.html", itens=itens)

@bp.route("/novo", methods=["GET", "POST"])
@login_required
def novo():
    if not _pode_gerenciar():
        abort(403)
    if request.method == "POST":
        nome = (request.form.get("nome") or "").strip()
        if not nome:
            flash("Informe o nome da série.", "warning")
            return render_template("serie_form.html")
        if Serie.query.filter(Serie.nome.ilike(nome)).first():
            flash("Já existe uma série com esse nome.", "warning")
            return render_template("serie_form.html")
        db.session.add(Serie(nome=nome))
        db.session.commit()
        flash("Série cadastrada.", "success")
        return redirect(url_for("series.listar"))
    return render_template("serie_form.html")

@bp.route("/<int:id>/editar", methods=["GET", "POST"])
@login_required
def editar(id: int):
    if not _pode_gerenciar():
        abort(403)
    s = Serie.query.get_or_404(id)
    if request.method == "POST":
        nome = (request.form.get("nome") or "").strip()
        if not nome:
            flash("Informe o nome da série.", "warning")
            return render_template("serie_form.html", s=s)
        existente = Serie.query.filter(Serie.nome.ilike(nome), Serie.id != s.id).first()
        if existente:
            flash("Já existe outra série com esse nome.", "warning")
            return render_template("serie_form.html", s=s)
        s.nome = nome
        db.session.commit()
        flash("Série atualizada.", "success")
        return redirect(url_for("series.listar"))
    return render_template("serie_form.html", s=s)

@bp.route("/<int:id>/excluir", methods=["POST"])
@login_required
def excluir(id: int):
    if not _pode_gerenciar():
        abort(403)
    s = Serie.query.get_or_404(id)
    db.session.delete(s)
    db.session.commit()
    flash("Série excluída.", "success")
    return redirect(url_for("series.listar"))
