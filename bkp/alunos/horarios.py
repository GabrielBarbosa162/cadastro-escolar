from flask import Blueprint, render_template, request, redirect, url_for, flash, abort
from flask_login import login_required, current_user
from app import db
from app.models import Horario  # ajuste conforme seu modelo

bp = Blueprint('horarios', __name__, url_prefix='/horarios')

def _pode_criar_horarios():
    papel = getattr(current_user, 'papel', None) or getattr(current_user, 'role', None)
    return papel in ('DIRETORIA',)

@bp.route('/')
@login_required
def listar():
    # Exemplo de estrutura esperada pelo template (dict por turma)
    # Se você já tem um .all(), adapte para montar o dict abaixo
    horarios_dict = {}
    qs = Horario.query.order_by(Horario.turma, Horario.dia, Horario.inicio).all()
    for h in qs:
        turma = getattr(h, 'turma', 'Turma')
        horarios_dict.setdefault(turma, []).append({
            'dia': getattr(h, 'dia', ''),
            'inicio': getattr(h, 'inicio', ''),
            'fim': getattr(h, 'fim', ''),
            'disciplina': getattr(h, 'disciplina', ''),
            'professor': getattr(h, 'professor', ''),
        })
    return render_template('stub.html', title='Quadro de Horários', header='Quadro de Horários', context='horarios', horarios=horarios_dict)

@bp.route('/novo', methods=['GET', 'POST'])
@login_required
def novo():
    if not _pode_criar_horarios():
        abort(403)
    if request.method == 'POST':
        turma = request.form.get('turma', '').strip()
        if not turma:
            flash('Informe a turma.', 'warning')
            return render_template('stub.html', title='Novo Horário', header='Novo Horário', context='horarios', form=request.form)
        h = Horario(
            turma=turma,
            dia=request.form.get('dia', ''),
            inicio=request.form.get('inicio', ''),
            fim=request.form.get('fim', ''),
            disciplina=request.form.get('disciplina', ''),
            professor=request.form.get('professor', ''),
        )
        db.session.add(h)
        db.session.commit()
        flash('Horário cadastrado!', 'success')
        return redirect(url_for('horarios.listar'))
    form = {'turma': '', 'dia': '', 'inicio': '', 'fim': '', 'disciplina': '', 'professor': ''}
    return render_template('stub.html', title='Novo Horário', header='Novo Horário', context='horarios', form=form, submit_label='Salvar')
