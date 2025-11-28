from flask import render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from . import bp

# IMPORTA DO app.py — NÃO use models.py
from app import db, Usuario, Aluno, Escola, Serie, Horario, Mensalidade, Atividade, perm_required, usuario_tem_permissao


@bp.route("/")
@login_required
def listar():
    alunos = (Aluno.query
              .order_by(Aluno.nome.asc())
              .all())
    return render_template("alunos/listar.html", alunos=alunos)

@bp.route("/novo", methods=["GET", "POST"])
@login_required
@perm_required("ALUNO_CRIAR")
def novo():
    escolas = Escola.query.order_by(Escola.nome.asc()).all()
    series = Serie.query.order_by(Serie.nome.asc()).all()
    horarios = Horario.query.order_by(Horario.hora_inicio.asc()).all()
    mensalidades = Mensalidade.query.order_by(Mensalidade.nome.asc()).all()

    if request.method == "POST":
        nome = request.form.get("nome", "").strip()
        escola_id = request.form.get("escola_id")
        serie_id = request.form.get("serie_id")
        horario_id = request.form.get("horario_id")
        mensalidade_id = request.form.get("mensalidade_id")
        telefone_mae = request.form.get("telefone_mae", "").strip()

        if not nome:
            flash("Informe o nome do aluno.", "warning")
            return render_template("alunos/novo.html",
                                   escolas=escolas, series=series, horarios=horarios, mensalidades=mensalidades)

        a = Aluno(
            nome=nome,
            escola_id=int(escola_id) if escola_id else None,
            serie_id=int(serie_id) if serie_id else None,
            horario_id=int(horario_id) if horario_id else None,
            mensalidade_id=int(mensalidade_id) if mensalidade_id else None,
            telefone_mae=telefone_mae or None
        )
        db.session.add(a)
        db.session.commit()
        flash("Aluno cadastrado.", "success")
        return redirect(url_for("alunos.listar"))

    return render_template("alunos/novo.html",
                           escolas=escolas, series=series, horarios=horarios, mensalidades=mensalidades)

@bp.route("/<int:id>/editar", methods=["GET", "POST"])
@login_required
@perm_required("ALUNO_EDITAR")
def editar(id):
    aluno = db.session.get(Aluno, id)
    if not aluno:
        flash("Aluno não encontrado.", "warning")
        return redirect(url_for("alunos.listar"))

    escolas = Escola.query.order_by(Escola.nome.asc()).all()
    series = Serie.query.order_by(Serie.nome.asc()).all()
    horarios = Horario.query.order_by(Horario.hora_inicio.asc()).all()
    mensalidades = Mensalidade.query.order_by(Mensalidade.nome.asc()).all()

    if request.method == "POST":
        aluno.nome = request.form.get("nome", "").strip() or aluno.nome
        escola_id = request.form.get("escola_id")
        serie_id = request.form.get("serie_id")
        horario_id = request.form.get("horario_id")
        mensalidade_id = request.form.get("mensalidade_id")
        aluno.telefone_mae = request.form.get("telefone_mae", "").strip() or None

        aluno.escola_id = int(escola_id) if escola_id else None
        aluno.serie_id = int(serie_id) if serie_id else None
        aluno.horario_id = int(horario_id) if horario_id else None
        aluno.mensalidade_id = int(mensalidade_id) if mensalidade_id else None

        db.session.commit()
        flash("Aluno atualizado.", "success")
        return redirect(url_for("alunos.listar"))

    return render_template("alunos/editar.html",
                           aluno=aluno,
                           escolas=escolas, series=series, horarios=horarios, mensalidades=mensalidades)

@bp.route("/<int:id>/excluir", methods=["POST"])
@login_required
@perm_required("ALUNO_EXCLUIR")
def excluir(id):
    aluno = db.session.get(Aluno, id)
    if not aluno:
        flash("Aluno não encontrado.", "warning")
    else:
        db.session.delete(aluno)
        db.session.commit()
        flash("Aluno excluído.", "success")
    return redirect(url_for("alunos.listar"))
