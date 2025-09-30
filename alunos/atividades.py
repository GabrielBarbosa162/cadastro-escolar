from flask import Blueprint, render_template, request, redirect, url_for, flash, abort
from flask_login import login_required, current_user
from app import db
from app.models import Atividade  # e, se precisar, Turma

bp = Blueprint('atividades', __name__, url_prefix='/atividades')

def _pode_criar_atividades():
    papel = getattr(current_user, 'papel', None) or getattr(current_user, 'role', None)
    return papel in ('DIRETORIA', 'PROFESSOR')

@bp.route('/')
@login_required
def listar():
    atividades = Atividade.query.order_by(Atividade.id.desc()).all()
    return render_template('stub.html', title='Atividades', header='Atividades', context='atividades', atividades=atividades)

@bp.route('/novo', methods=['GET', 'POST'])
@login_required
def novo():
    if not _pode_criar_atividades():
        abort(403)
    if request.method == 'POST':
        titulo = request.form.get('titulo', '').strip()
        if not titulo:
            flash('Informe o título da atividade.', 'warning')
            return render_template('stub.html', title='Nova Atividade', header='Nova Atividade', context='atividades', form=request.form)
        a = Atividade(titulo=titulo, criado_por_id=getattr(current_user, 'id', None))
        db.session.add(a)
        db.session.commit()
        flash('Atividade cadastrada!', 'success')
        return redirect(url_for('atividades.listar'))
    form = {'titulo': ''}
    return render_template('stub.html', title='Nova Atividade', header='Nova Atividade', context='atividades', form=form, submit_label='Salvar')
