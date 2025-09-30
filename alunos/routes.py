from datetime import datetime
import os
from flask import render_template, request, redirect, url_for, flash, abort, current_app
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename

from . import bp
from models import db, Aluno, Escola, Serie, Horario, Mensalidade

# ------------------ Helpers de permissão ------------------
def _can_create():
    return current_user.is_authenticated and (
        current_user.papel in ("DIRETORIA", "PROFESSOR")
        or current_user.papel == "RESPONSAVEL"  # ajuste se não puder
    )

def _can_edit():
    return current_user.is_authenticated and (
        current_user.papel in ("DIRETORIA", "PROFESSOR")
    )

def _can_delete():
    return current_user.is_authenticated and (
        current_user.papel in ("DIRETORIA",)
    )

# ------------------ Listagem ------------------
@bp.route("/")
@login_required
def listar():
    q = (request.args.get("q") or "").strip()
    query = Aluno.query
    if q:
        like = f"%{q}%"
        query = query.filter(Aluno.nome.ilike(like))
    alunos = query.order_by(Aluno.nome.asc()).all()

    # catálogos para filtros/labels (se quiser exibir)
    return render_template("alunos_list.html", alunos=alunos, can_edit=_can_edit(), can_delete=_can_delete())

# ------------------ Novo ------------------
@bp.route("/novo", methods=["GET", "POST"])
@login_required
def novo():
    if not _can_create():
        abort(403)

    escolas = Escola.query.order_by(Escola.nome.asc()).all()
    series = Serie.query.order_by(Serie.nome.asc()).all()
    horarios = Horario.query.order_by(Horario.hora_inicio.asc().nullslast(), Horario.nome.asc().nullslast()).all()
    mensalidades = Mensalidade.query.order_by(Mensalidade.valor.asc()).all()

    if request.method == "POST":
        nome = (request.form.get("nome") or "").strip()
        if not nome:
            flash("Informe o nome completo do aluno.", "warning")
            return render_template("aluno_form.html", escolas=escolas, series=series, horarios=horarios, mensalidades=mensalidades)

        # campos principais
        naturalidade = (request.form.get("naturalidade") or "").strip() or None
        nacionalidade = (request.form.get("nacionalidade") or "").strip() or None
        data_nascimento = request.form.get("data_nascimento") or None
        idade = request.form.get("idade") or None
        anos = (request.form.get("anos") or "").strip() or None
        sexo = (request.form.get("sexo") or "").strip() or None

        nome_pai = (request.form.get("nome_pai") or "").strip() or None
        nome_mae = (request.form.get("nome_mae") or "").strip() or None
        endereco = (request.form.get("endereco") or "").strip() or None
        numero = (request.form.get("numero") or "").strip() or None
        bairro = (request.form.get("bairro") or "").strip() or None
        telefone_celular = (request.form.get("telefone_celular") or "").strip() or None
        telefone_fixo = (request.form.get("telefone_fixo") or "").strip() or None
        telefone_mae = (request.form.get("telefone_mae") or "").strip() or None

        escola_sel = (request.form.get("escola") or "").strip() or None
        serie_sel = (request.form.get("serie") or "").strip() or None
        turma = (request.form.get("turma") or "").strip() or None

        dificuldade = True if request.form.get("dificuldade") == "S" else False
        dificuldade_qual = (request.form.get("dificuldade_qual") or "").strip() or None
        medicamento_controlado = True if request.form.get("medicamento_controlado") == "S" else False
        medicamento_qual = (request.form.get("medicamento_qual") or "").strip() or None

        # horário (texto compatível com telas/relatórios)
        horario_id = request.form.get("horario_id") or None
        horario_resumo = None
        if horario_id:
            h = Horario.query.get(int(horario_id))
            if h:
                horario_resumo = h.nome or f"{(h.hora_inicio or '')} - {(h.hora_fim or '')}"

        inicio_aulas = request.form.get("inicio_aulas") or None

        # ======== Mensalidade (TABELA) - ÚNICO CAMPO =========
        mensalidade_id = request.form.get("mensalidade_id")  # obrigatório
        if not mensalidade_id:
            flash("Selecione a Mensalidade.", "warning")
            return render_template("aluno_form.html", escolas=escolas, series=series, horarios=horarios, mensalidades=mensalidades)
        m = Mensalidade.query.get(int(mensalidade_id))
        if not m:
            flash("Mensalidade inválida.", "warning")
            return render_template("aluno_form.html", escolas=escolas, series=series, horarios=horarios, mensalidades=mensalidades)

        # upload de foto (opcional)
        foto_path = None
        f = request.files.get("foto")
        if f and f.filename:
            fname = secure_filename(f.filename)
            if not fname:
                fname = f"aluno_{datetime.utcnow().timestamp():.0f}.bin"
            save_dir = os.path.join(current_app.root_path, "uploads")
            os.makedirs(save_dir, exist_ok=True)
            dest = os.path.join(save_dir, fname)
            f.save(dest)
            foto_path = f"/uploads/{fname}"

        a = Aluno(
            nome=nome,
            naturalidade=naturalidade,
            nacionalidade=nacionalidade,
            data_nascimento=datetime.strptime(data_nascimento, "%Y-%m-%d").date() if data_nascimento else None,
            idade=int(idade) if (idade and idade.isdigit()) else None,
            anos=anos,
            sexo=sexo,
            nome_pai=nome_pai,
            nome_mae=nome_mae,
            endereco=endereco,
            numero=numero,
            bairro=bairro,
            telefone_celular=telefone_celular,
            telefone_fixo=telefone_fixo,
            telefone_mae=telefone_mae,
            escola=escola_sel,
            serie=serie_sel,
            turma=turma,
            dificuldade=dificuldade,
            dificuldade_qual=dificuldade_qual,
            medicamento_controlado=medicamento_controlado,
            medicamento_qual=medicamento_qual,
            inicio_aulas=datetime.strptime(inicio_aulas, "%Y-%m-%d").date() if inicio_aulas else None,
            # >>>> APENAS tabela Mensalidade:
            faixa_mensalidade=m.faixa,
            mensalidade=m.valor,           # valor preenchido a partir da tabela
            horario_resumo=horario_resumo,
            foto_path=foto_path
        )
        db.session.add(a)
        db.session.commit()
        flash("Aluno cadastrado com sucesso.", "success")
        return redirect(url_for("alunos.listar"))

    return render_template("aluno_form.html", escolas=escolas, series=series, horarios=horarios, mensalidades=mensalidades)

# ------------------ Editar ------------------
@bp.route("/<int:id>/editar", methods=["GET", "POST"])
@login_required
def editar(id: int):
    if not _can_edit():
        abort(403)
    a = Aluno.query.get_or_404(id)

    escolas = Escola.query.order_by(Escola.nome.asc()).all()
    series = Serie.query.order_by(Serie.nome.asc()).all()
    horarios = Horario.query.order_by(Horario.hora_inicio.asc().nullslast(), Horario.nome.asc().nullslast()).all()
    mensalidades = Mensalidade.query.order_by(Mensalidade.valor.asc()).all()

    if request.method == "POST":
        nome = (request.form.get("nome") or "").strip()
        if not nome:
            flash("Informe o nome completo do aluno.", "warning")
            return render_template("aluno_form.html", a=a, escolas=escolas, series=series, horarios=horarios, mensalidades=mensalidades)

        a.nome = nome
        a.naturalidade = (request.form.get("naturalidade") or "").strip() or None
        a.nacionalidade = (request.form.get("nacionalidade") or "").strip() or None
        dn = request.form.get("data_nascimento") or None
        a.data_nascimento = datetime.strptime(dn, "%Y-%m-%d").date() if dn else None
        idade = request.form.get("idade") or None
        a.idade = int(idade) if (idade and idade.isdigit()) else None
        a.anos = (request.form.get("anos") or "").strip() or None
        a.sexo = (request.form.get("sexo") or "").strip() or None

        a.nome_pai = (request.form.get("nome_pai") or "").strip() or None
        a.nome_mae = (request.form.get("nome_mae") or "").strip() or None
        a.endereco = (request.form.get("endereco") or "").strip() or None
        a.numero = (request.form.get("numero") or "").strip() or None
        a.bairro = (request.form.get("bairro") or "").strip() or None
        a.telefone_celular = (request.form.get("telefone_celular") or "").strip() or None
        a.telefone_fixo = (request.form.get("telefone_fixo") or "").strip() or None
        a.telefone_mae = (request.form.get("telefone_mae") or "").strip() or None

        a.escola = (request.form.get("escola") or "").strip() or None
        a.serie = (request.form.get("serie") or "").strip() or None
        a.turma = (request.form.get("turma") or "").strip() or None

        a.dificuldade = True if request.form.get("dificuldade") == "S" else False
        a.dificuldade_qual = (request.form.get("dificuldade_qual") or "").strip() or None
        a.medicamento_controlado = True if request.form.get("medicamento_controlado") == "S" else False
        a.medicamento_qual = (request.form.get("medicamento_qual") or "").strip() or None

        hi = request.form.get("horario_id") or None
        a.horario_resumo = None
        if hi:
            h = Horario.query.get(int(hi))
            if h:
                a.horario_resumo = h.nome or f"{(h.hora_inicio or '')} - {(h.hora_fim or '')}"

        ia = request.form.get("inicio_aulas") or None
        a.inicio_aulas = datetime.strptime(ia, "%Y-%m-%d").date() if ia else None

        # ======== Mensalidade (TABELA) - ÚNICO CAMPO =========
        mensalidade_id = request.form.get("mensalidade_id")
        if not mensalidade_id:
            flash("Selecione a Mensalidade.", "warning")
            return render_template("aluno_form.html", a=a, escolas=escolas, series=series, horarios=horarios, mensalidades=mensalidades)
        m = Mensalidade.query.get(int(mensalidade_id))
        if not m:
            flash("Mensalidade inválida.", "warning")
            return render_template("aluno_form.html", a=a, escolas=escolas, series=series, horarios=horarios, mensalidades=mensalidades)
        a.faixa_mensalidade = m.faixa
        a.mensalidade = m.valor  # preenchido internamente a partir da tabela

        # foto (opcional, sobrescreve se houver upload)
        f = request.files.get("foto")
        if f and f.filename:
            fname = secure_filename(f.filename)
            if not fname:
                fname = f"aluno_{datetime.utcnow().timestamp():.0f}.bin"
            save_dir = os.path.join(current_app.root_path, "uploads")
            os.makedirs(save_dir, exist_ok=True)
            dest = os.path.join(save_dir, fname)
            f.save(dest)
            a.foto_path = f"/uploads/{fname}"

        db.session.commit()
        flash("Cadastro atualizado.", "success")
        return redirect(url_for("alunos.listar"))

    # tenta inferir a mensalidade selecionada pela faixa/valor gravados
    mensalidade_id_sel = None
    if a.faixa_mensalidade:
        sel = Mensalidade.query.filter_by(faixa=a.faixa_mensalidade).first()
        if sel:
            mensalidade_id_sel = sel.id
    elif a.mensalidade:
        sel = Mensalidade.query.filter(Mensalidade.valor == a.mensalidade).first()
        if sel:
            mensalidade_id_sel = sel.id

    return render_template(
        "aluno_form.html", a=a, escolas=escolas, series=series, horarios=horarios,
        mensalidades=mensalidades, mensalidade_id_sel=mensalidade_id_sel
    )

# ------------------ Excluir ------------------
@bp.route("/<int:id>/excluir", methods=["POST"])
@login_required
def excluir(id: int):
    if not _can_delete():
        abort(403)
    a = Aluno.query.get_or_404(id)
    db.session.delete(a)
    db.session.commit()
    flash("Aluno excluído.", "success")
    return redirect(url_for("alunos.listar"))
