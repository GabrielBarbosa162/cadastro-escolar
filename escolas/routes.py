from flask import render_template, request, redirect, url_for, flash
from flask_login import login_required
from . import bp
from app import db, Usuario, Aluno, Escola, Serie, Horario, Mensalidade, Atividade, perm_required, usuario_tem_permissao

@bp.route("/")
@login_required
def listar():
    escolas = Escola.query.order_by(Escola.nome.asc()).all()
    return render_template("escolas/listar.html", escolas=escolas)

@bp.route("/nova", methods=["GET", "POST"])
@login_required
@perm_required("ESCOLA_ADICIONAR")
def nova():
    if request.method == "POST":
        nome = request.form.get("nome", "").strip()
        if not nome:
            flash("Informe o nome da escola.", "warning")
        else:
            db.session.add(Escola(nome=nome))
            db.session.commit()
            flash("Escola cadastrada.", "success")
            return redirect(url_for("escolas.listar"))
    return render_template("escolas/nova.html")

@bp.route("/<int:id>/editar", methods=["GET", "POST"])
@login_required
@perm_required("ESCOLA_ADICIONAR")
def editar(id):
    escola = db.session.get(Escola, id)
    if not escola:
        flash("Escola não encontrada.", "warning")
        return redirect(url_for("escolas.listar"))
    if request.method == "POST":
        nome = request.form.get("nome", "").strip()
        if not nome:
            flash("Informe o nome da escola.", "warning")
        else:
            escola.nome = nome
            db.session.commit()
            flash("Escola atualizada.", "success")
            return redirect(url_for("escolas.listar"))
    return render_template("escolas/editar.html", escola=escola)

@bp.route("/<int:id>/excluir", methods=["POST"])
@login_required
@perm_required("ESCOLA_EXCLUIR")
def excluir(id):
    escola = db.session.get(Escola, id)
    if escola:
        db.session.delete(escola)
        db.session.commit()
        flash("Escola excluída.", "success")
    else:
        flash("Escola não encontrada.", "warning")
    return redirect(url_for("escolas.listar"))
