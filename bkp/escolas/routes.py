from flask import render_template, request, redirect, url_for, flash
from flask_login import login_required
from app import db, Escola
from . import bp

@bp.route("/")
@login_required
def listar():
    escolas = Escola.query.order_by(Escola.nome.asc()).all()
    return render_template("escolas_listar.html", escolas=escolas)

@bp.route("/nova", methods=["GET", "POST"])
@login_required
def nova():
    if request.method == "POST":
        nome = request.form.get("nome")
        escola = Escola(nome=nome)
        db.session.add(escola)
        db.session.commit()
        flash("Escola cadastrada!", "success")
        return redirect(url_for("escolas.listar"))
    return render_template("escolas_form.html")
