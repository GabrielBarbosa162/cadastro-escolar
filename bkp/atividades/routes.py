from datetime import datetime
from flask import render_template, request, redirect, url_for, flash
from flask_login import login_required
from . import bp
from app import db, Usuario, Aluno, Escola, Serie, Horario, Mensalidade, Atividade, perm_required, usuario_tem_permissao


@bp.route("/")
@login_required
def listar():
    itens = (Atividade.query
             .order_by(Atividade.data.desc().nullslast(), Atividade.criado_em.desc())
             .all())
    return render_template("atividades/listar.html", atividades=itens)

@bp.route("/nova", methods=["GET", "POST"])
@login_required
@perm_required("ATIVIDADE_ADICIONAR")
def nova():
    alunos = Aluno.query.order_by(Aluno.nome.asc()).all()
    if request.method == "POST":
        aluno_id = request.form.get("aluno_id")
        data_txt = request.form.get("data")  # yyyy-mm-dd
        conteudo = request.form.get("conteudo", "").strip() or None
        observacao = request.form.get("observacao", "").strip() or None

        d = None
        if data_txt:
            try:
                d = datetime.strptime(data_txt, "%Y-%m-%d").date()
            except Exception:
                pass

        a = Atividade(
            aluno_id=int(aluno_id) if aluno_id else None,
            data=d,
            conteudo=conteudo,
            observacao=observacao
        )
        db.session.add(a)
        db.session.commit()
        flash("Atividade lançada.", "success")
        return redirect(url_for("atividades.listar"))

    return render_template("atividades/nova.html", alunos=alunos)

@bp.route("/<int:id>/editar", methods=["GET", "POST"])
@login_required
@perm_required("ATIVIDADE_ADICIONAR")
def editar(id):
    item = db.session.get(Atividade, id)
    if not item:
        flash("Atividade não encontrada.", "warning")
        return redirect(url_for("atividades.listar"))
    alunos = Aluno.query.order_by(Aluno.nome.asc()).all()
    if request.method == "POST":
        aluno_id = request.form.get("aluno_id")
        data_txt = request.form.get("data")
        item.aluno_id = int(aluno_id) if aluno_id else None
        if data_txt:
            try:
                item.data = datetime.strptime(data_txt, "%Y-%m-%d").date()
            except Exception:
                item.data = None
        else:
            item.data = None
        item.conteudo = request.form.get("conteudo", "").strip() or None
        item.observacao = request.form.get("observacao", "").strip() or None
        db.session.commit()
        flash("Atividade atualizada.", "success")
        return redirect(url_for("atividades.listar"))
    return render_template("atividades/editar.html", item=item, alunos=alunos)

@bp.route("/<int:id>/excluir", methods=["POST"])
@login_required
@perm_required("ATIVIDADE_EXCLUIR")
def excluir(id):
    item = db.session.get(Atividade, id)
    if item:
        db.session.delete(item)
        db.session.commit()
        flash("Atividade excluída.", "success")
    else:
        flash("Atividade não encontrada.", "warning")
    return redirect(url_for("atividades.listar"))
