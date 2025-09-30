from flask import Blueprint, render_template, request, redirect, url_for, flash, abort
from flask_login import login_required, current_user
from app import db
from app.models import Escola

bp = Blueprint('escolas', __name__, url_prefix='/escolas')

def _pode_criar_escolas():
    papel = getattr(current_user, 'papel', None) or getattr(current_user, 'role', None)
    return papel in ('DIRETORIA',)

@bp.route('/')
@login_required
def listar():
    escolas = Escola.query.order_by(Escola.nome).all()
    return render_template('stub.html', title='Escolas', header='Escolas', context='escolas', escolas=escolas)

@bp.route('/novo', methods=['GET', 'POST'])
@login_required
def novo():
    if not _pode_criar_escolas():
        abort(403)
    if request.method == 'POST':
        nome = request.form.get('nome', '').strip()
        if not nome:
            flash('Informe o nome da escola.', 'warning')
            return render_template('stub.html', title='Nova Escola', header='Nova Escola', context='escolas', form=request.form)
        e = Escola(nome=nome)
        db.session.add(e)
        db.session.commit()
        flash('Escola cadastrada!', 'success')
        return redirect(url_for('escolas.listar'))
    form = {'nome': ''}
    return render_template('stub.html', title='Nova Escola', header='Nova Escola', context='escolas', form=form, submit_label='Salvar')
