from flask import render_template, request, redirect, url_for, flash
from flask_login import login_required
from . import bp
from app import db, Usuario, Aluno, Escola, Serie, Horario, Mensalidade, Atividade, perm_required, usuario_tem_permissao

@bp.route("/")
@login_required
def listar():
    series = Serie.query.order_by(Serie.nome.asc()).all()
    return render_template("series/listar.html", series=series)

@bp.route("/nova", methods=["GET", "POST"])
@login_required
@perm_required("SERIE_ADICIONAR")
def nova():
    if request.method == "POST":
        nome = request.form.get("nome", "").strip()
        if not nome:
            flash("Informe o nome da série.", "warning")
        else:
            db.session.add(Serie(nome=nome))
            db.session.commit()
            flash("Série cadastrada.", "success")
            return redirect(url_for("series.listar"))
    return render_template("series/nova.html")

@bp.route("/<int:id>/editar", methods=["GET", "POST"])
@login_required
@perm_required("SERIE_ADICIONAR")
def editar(id):
    serie = db.session.get(Serie, id)
    if not serie:
        flash("Série não encontrada.", "warning")
        return redirect(url_for("series.listar"))
    if request.method == "POST":
        nome = request.form.get("nome", "").strip()
        if not nome:
            flash("Informe o nome da série.", "warning")
        else:
            serie.nome = nome
            db.session.commit()
            flash("Série atualizada.", "success")
            return redirect(url_for("series.listar"))
    return render_template("series/editar.html", serie=serie)

@bp.route("/<int:id>/excluir", methods=["POST"])
@login_required
@perm_required("SERIE_EXCLUIR")
def excluir(id):
    serie = db.session.get(Serie, id)
    if serie:
        db.session.delete(serie)
        db.session.commit()
        flash("Série excluída.", "success")
    else:
        flash("Série não encontrada.", "warning")
    return redirect(url_for("series.listar"))
