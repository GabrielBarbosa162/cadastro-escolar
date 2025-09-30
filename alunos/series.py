from flask import Blueprint, render_template, request, redirect, url_for, flash, abort
from flask_login import login_required, current_user
from app import db
from app.models import Serie

bp = Blueprint('series', __name__, url_prefix='/series')

def _pode_criar_series():
    papel = getattr(current_user, 'papel', None) or getattr(current_user, 'role', None)
    return papel in ('DIRETORIA',)

@bp.route('/')
@login_required
def listar():
    series = Serie.query.order_by(Serie.nome).all()
    return render_template('stub.html', title='Séries', header='Séries', context='series', series=series)

@bp.route('/novo', methods=['GET', 'POST'])
@login_required
def novo():
    if not _pode_criar_series():
        abort(403)
    if request.method == 'POST':
        nome = request.form.get('nome', '').strip()
        if not nome:
            flash('Informe o nome da série.', 'warning')
            return render_template('stub.html', title='Nova Série', header='Nova Série', context='series', form=request.form)
        s = Serie(nome=nome)
        db.session.add(s)
        db.session.commit()
        flash('Série cadastrada!', 'success')
        return redirect(url_for('series.listar'))
    form = {'nome': ''}
    return render_template('stub.html', title='Nova Série', header='Nova Série', context='series', form=form, submit_label='Salvar')
