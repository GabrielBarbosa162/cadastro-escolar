import re
from datetime import datetime
from urllib.parse import quote
from flask import render_template, request, redirect, url_for, flash, abort
from flask_login import login_required, current_user
from . import bp
from models import db, Atividade, Aluno

def _pode_gerenciar():
    return current_user.is_authenticated and current_user.papel in ("DIRETORIA", "PROFESSOR")

def _normalize_phone(phone_raw: str) -> str:
    """Mantém apenas dígitos e adiciona DDI 55 se faltar (Brasil)."""
    if not phone_raw:
        return ""
    digits = re.sub(r"\D+", "", phone_raw)
    if digits.startswith("55"):
        return digits
    if len(digits) >= 10:
        return "55" + digits
    return digits  # deixa como está se muito curto

@bp.route("/")
@login_required
def listar():
    q = (request.args.get("q") or "").strip()
    query = Atividade.query
    if q:
        query = query.filter(Atividade.nome.ilike(f"%{q}%"))
    itens = query.order_by(Atividade.data_atividade.desc().nullslast(), Atividade.criado_em.desc()).all()

    # Mapa de telefones da mãe por aluno_id (para montar o link na lista)
    phones = {}
    ids = [it.aluno_id for it in itens if it.aluno_id]
    if ids:
        for al in Aluno.query.filter(Aluno.id.in_(ids)).all():
            phones[al.id] = al.telefone_mae or al.telefone_celular or ""

    def wa_link(it: Atividade):
        phone = _normalize_phone(phones.get(it.aluno_id, ""))
        if not phone:
            return None
        data_txt = it.data_atividade.strftime("%d/%m/%Y") if it.data_atividade else ""
        msg = (
            f"*Atividade:* {it.nome}\n"
            f"*Aluno:* {it.aluno_nome or ''}\n"
            f"*Data:* {data_txt}\n"
            f"*Conteúdo:* {it.conteudo or ''}\n"
            f"*Obs.:* {it.observacao or ''}"
        )
        # >>>>>> Linka DIRETO no WhatsApp Web
        return f"https://web.whatsapp.com/send?phone={phone}&text={quote(msg)}"

    return render_template("atividades_list.html", itens=itens, wa_link=wa_link)

@bp.route("/novo", methods=["GET", "POST"])
@login_required
def novo():
    if not _pode_gerenciar():
        abort(403)
    alunos = Aluno.query.order_by(Aluno.nome.asc()).all()

    if request.method == "POST":
        aluno_id = request.form.get("aluno_id")
        nome = (request.form.get("nome") or "").strip()
        data = request.form.get("data_atividade")
        conteudo = (request.form.get("conteudo") or "").strip()
        observacao = (request.form.get("observacao") or "").strip()

        if not aluno_id:
            flash("Selecione o aluno.", "warning")
            return render_template("atividade_form.html", alunos=alunos)
        if not nome:
            flash("Informe o nome/título da atividade.", "warning")
            return render_template("atividade_form.html", alunos=alunos)

        al = Aluno.query.get(int(aluno_id))
        if not al:
            flash("Aluno inválido.", "warning")
            return render_template("atividade_form.html", alunos=alunos)

        atv = Atividade(
            nome=nome,
            aluno_id=al.id,
            aluno_nome=al.nome,
            data_atividade=datetime.strptime(data, "%Y-%m-%d").date() if data else None,
            conteudo=conteudo or None,
            observacao=observacao or None
        )
        db.session.add(atv)
        db.session.commit()
        flash("Atividade cadastrada.", "success")
        return redirect(url_for("atividades.listar"))

    return render_template("atividade_form.html", alunos=alunos, a=None)

@bp.route("/<int:id>/editar", methods=["GET", "POST"])
@login_required
def editar(id: int):
    if not _pode_gerenciar():
        abort(403)
    a = Atividade.query.get_or_404(id)
    alunos = Aluno.query.order_by(Aluno.nome.asc()).all()

    if request.method == "POST":
        aluno_id = request.form.get("aluno_id")
        nome = (request.form.get("nome") or "").strip()
        data = request.form.get("data_atividade")
        conteudo = (request.form.get("conteudo") or "").strip()
        observacao = (request.form.get("observacao") or "").strip()

        if not aluno_id:
            flash("Selecione o aluno.", "warning")
            return render_template("atividade_form.html", alunos=alunos, a=a)
        if not nome:
            flash("Informe o nome/título da atividade.", "warning")
            return render_template("atividade_form.html", alunos=alunos, a=a)

        al = Aluno.query.get(int(aluno_id))
        if not al:
            flash("Aluno inválido.", "warning")
            return render_template("atividade_form.html", alunos=alunos, a=a)

        a.nome = nome
        a.aluno_id = al.id
        a.aluno_nome = al.nome
        a.data_atividade = datetime.strptime(data, "%Y-%m-%d").date() if data else None
        a.conteudo = conteudo or None
        a.observacao = observacao or None
        db.session.commit()
        flash("Atividade atualizada.", "success")
        return redirect(url_for("atividades.listar"))

    return render_template("atividade_form.html", alunos=alunos, a=a)

@bp.route("/<int:id>/excluir", methods=["POST"])
@login_required
def excluir(id: int):
    if not _pode_gerenciar():
        abort(403)
    atv = Atividade.query.get_or_404(id)
    db.session.delete(atv)
    db.session.commit()
    flash("Atividade excluída.", "success")
    return redirect(url_for("atividades.listar"))
