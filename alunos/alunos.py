from flask import Blueprint, render_template, request, redirect, url_for, flash, abort
from flask_login import login_required, current_user
from app import db
from app.models import Aluno  # ajuste se seu caminho de modelos for outro

bp = Blueprint('alunos', __name__, url_prefix='/alunos')

def _pode_criar_alunos():
    papel = getattr(current_user, 'papel', None) or getattr(current_user, 'role', None)
    return papel in ('DIRETORIA', 'PROFESSOR')

@bp.route('/')
@login_required
def listar():
    alunos = Aluno.query.order_by(Aluno.nome).all()
    return render_template(
        'stub.html',
        title='Alunos',
        header='Alunos',
        context='alunos',   # <<< IMPORTANTE para o botão
        alunos=alunos,
        # Se quiser forçar o botão independentemente do papel, descomente:
        # can_create=True
    )

@bp.route('/novo', methods=['GET', 'POST'])
@login_required
def novo():
    if not _pode_criar_alunos():
        abort(403)
    if request.method == 'POST':
        nome = request.form.get('nome', '').strip()
        if not nome:
            flash('Informe o nome do aluno.', 'warning')
            return render_template('stub.html', title='Novo Aluno', header='Novo Aluno', context='alunos', form=request.form)
        a = Aluno(nome=nome)
        db.session.add(a)
        db.session.commit()
        flash('Aluno cadastrado com sucesso!', 'success')
        return redirect(url_for('alunos.listar'))
    # GET
    form = {'nome': ''}
    return render_template('stub.html', title='Novo Aluno', header='Novo Aluno', context='alunos', form=form, submit_label='Salvar')

@bp.route('/<int:id>/editar', methods=['GET', 'POST'])
@login_required
def editar(id):
    a = Aluno.query.get_or_404(id)
    if not _pode_criar_alunos():
        abort(403)
    if request.method == 'POST':
        a.nome = request.form.get('nome', a.nome)
        db.session.commit()
        flash('Aluno atualizado!', 'success')
        return redirect(url_for('alunos.listar'))
    form = {'nome': a.nome}
    return render_template('stub.html', title='Editar Aluno', header='Editar Aluno', context='alunos', form=form, submit_label='Salvar')

@bp.route('/<int:id>/excluir', methods=['POST'])
@login_required
def excluir(id):
    if not _pode_criar_alunos():
        abort(403)
    a = Aluno.query.get_or_404(id)
    db.session.delete(a)
    db.session.commit()
    flash('Aluno excluído!', 'success')
    return redirect(url_for('alunos.listar'))

@bp.route('/<int:id>')
@login_required
def detalhe(id):
    a = Aluno.query.get_or_404(id)
    # usa painel genérico
    cards = [
        {'label': 'ID', 'value': a.id},
        {'label': 'Nome', 'value': a.nome},
    ]
    return render_template('stub.html', title='Detalhe do Aluno', header=a.nome, context='alunos', cards=cards)
