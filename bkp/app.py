# app.py
import os
from datetime import datetime, date
from flask import Flask, render_template, redirect, url_for, request, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import (
    LoginManager,
    UserMixin,
    login_user,
    login_required,
    current_user,
    logout_user,
)
from sqlalchemy import text as sa_text

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DB_PATH = os.path.join(BASE_DIR, "alunos.db")

app = Flask(__name__)
app.config["SECRET_KEY"] = "dev-secret"
app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{DB_PATH}"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = "login"


# ---------------------------
# HELPER PARA HORA (corrigir strftime em string)
# ---------------------------
class HoraStrWrapper:
    def __init__(self, text):
        self.text = text or ""

    def strftime(self, fmt):
        # O template chama .strftime('%H:%M'), mas como já está HH:MM,
        # apenas devolvemos a string.
        return self.text


# ---------------------------
# MODELOS
# ---------------------------
class Usuario(db.Model, UserMixin):
    __tablename__ = "usuario"
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    senha_hash = db.Column(db.String(255), nullable=False)
    papel = db.Column(
        db.String(30), nullable=False, default="ALUNO"
    )  # DIRETORIA/PROFESSOR/RESPONSAVEL/ALUNO
    ativo = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    # Vínculo opcional com um aluno (para RESPONSAVEL/ALUNO)
    aluno_id = db.Column(db.Integer, db.ForeignKey("aluno.id"), nullable=True)
    aluno = db.relationship("Aluno", lazy="joined")

    def papel_upper(self):
        return (self.papel or "").upper()

    def is_diretoria(self):
        return self.papel_upper() == "DIRETORIA"

    def is_professor(self):
        return self.papel_upper() == "PROFESSOR"

    def is_responsavel(self):
        return self.papel_upper() == "RESPONSAVEL"

    def is_aluno(self):
        return self.papel_upper() == "ALUNO"


class Escola(db.Model):
    __tablename__ = "escola"
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(120), nullable=False, unique=True)


class Serie(db.Model):
    __tablename__ = "serie"
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(120), nullable=False, unique=True)


class Horario(db.Model):
    __tablename__ = "horario"
    id = db.Column(db.Integer, primary_key=True)
    hora_inicio = db.Column(db.String(5), nullable=False)  # HH:MM
    hora_fim = db.Column(db.String(5), nullable=False)  # HH:MM


class Aluno(db.Model):
    __tablename__ = "aluno"
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(180), nullable=False)

    escola_id = db.Column(db.Integer, db.ForeignKey("escola.id"))
    serie_id = db.Column(db.Integer, db.ForeignKey("serie.id"))
    horario_id = db.Column(db.Integer, db.ForeignKey("horario.id"))

    telefone_cel = db.Column(db.String(30))
    telefone_fixo = db.Column(db.String(30))
    foto_path = db.Column(db.String(300))
    observacoes = db.Column(db.Text)

    # Campos completos do cadastro
    naturalidade = db.Column(db.String(120))
    nacionalidade = db.Column(db.String(120))
    data_nascimento = db.Column(db.Date)
    idade = db.Column(db.Integer)
    sexo = db.Column(db.String(1))  # M/F
    nome_pai = db.Column(db.String(180))
    nome_mae = db.Column(db.String(180))
    endereco = db.Column(db.String(200))
    numero = db.Column(db.String(20))
    bairro = db.Column(db.String(120))

    tem_dificuldade = db.Column(db.Boolean)
    qual_dificuldade = db.Column(db.String(255))
    toma_medicamento = db.Column(db.Boolean)
    qual_medicamento = db.Column(db.String(255))
    inicio_aulas = db.Column(db.Date)
    mensalidade_opcao = db.Column(db.String(60))  # texto do plano

    # relações convenientes
    escola = db.relationship("Escola", lazy="joined")
    serie = db.relationship("Serie", lazy="joined")
    horario = db.relationship("Horario", lazy="joined")


class Atividade(db.Model):
    __tablename__ = "atividade"
    id = db.Column(db.Integer, primary_key=True)
    aluno_id = db.Column(db.Integer, db.ForeignKey("aluno.id"), nullable=False)

    data = db.Column(db.Date, nullable=False, default=date.today)
    professor = db.Column(db.String(180), nullable=False)
    conteudo = db.Column(db.Text, nullable=False)
    observacao = db.Column(db.Text)

    aluno = db.relationship("Aluno", lazy="joined")


# ---------------------------
# LOGIN
# ---------------------------
@login_manager.user_loader
def load_user(uid):
    # usar API nova para evitar warning
    return db.session.get(Usuario, int(uid))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        senha = request.form.get("senha", "")
        user = Usuario.query.filter_by(email=email).first()
        if user and user.senha_hash == senha and user.ativo:
            login_user(user)
            return redirect(url_for("index"))
        flash("Credenciais inválidas ou usuário inativo.", "danger")
    return render_template("auth/login.html")


@app.route("/esqueci", methods=["GET", "POST"])
def esqueci():
    flash("Recuperação de senha ainda não configurada.", "warning")
    return redirect(url_for("login"))


@app.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))


# ---------------------------
# UTIS
# ---------------------------
def _add_col_if_missing(table: str, column: str, ddl: str):
    """Adiciona coluna no SQLite se não existir."""
    info = db.session.execute(sa_text(f"PRAGMA table_info({table})")).mappings().all()
    cols = {c["name"] for c in info}
    if column not in cols:
        db.session.execute(sa_text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}"))
        db.session.commit()


def ensure_schema():
    """Migração leve para colunas que faltam (evita crashes do SELECT)."""
    # ATIVIDADE
    try:
        _add_col_if_missing("atividade", "data", "DATE")
        _add_col_if_missing("atividade", "professor", "TEXT")
        _add_col_if_missing("atividade", "conteudo", "TEXT")
        _add_col_if_missing("atividade", "observacao", "TEXT")
    except Exception:
        db.session.rollback()

    # HORARIO
    try:
        _add_col_if_missing("horario", "hora_inicio", "TEXT")
        _add_col_if_missing("horario", "hora_fim", "TEXT")
    except Exception:
        db.session.rollback()

    # ESCOLA (garantir nome)
    try:
        _add_col_if_missing("escola", "nome", "TEXT")
    except Exception:
        db.session.rollback()

    # USUARIO - vinculo com aluno
    try:
        _add_col_if_missing("usuario", "aluno_id", "INTEGER")
    except Exception:
        db.session.rollback()


def _is_hhmm(val: str) -> bool:
    if not val or len(val) != 5 or val[2] != ":":
        return False
    hh, mm = val.split(":")
    return hh.isdigit() and mm.isdigit() and 0 <= int(hh) <= 23 and 0 <= int(mm) <= 59


# ----------- PERMISSÕES (can) -----------
def can(permission: str) -> bool:
    """
    Helper simples para os templates.
    Vamos usar permissões mais gerais, baseadas no papel do usuário.
    """
    if not current_user.is_authenticated:
        return False

    role = current_user.papel_upper()

    # DIRETORIA pode tudo
    if role == "DIRETORIA":
        return True

    if permission == "ver_usuarios":
        return False

    if permission == "gerenciar_usuarios":
        return False

    if permission == "gerenciar_estrutura":  # escolas/séries/horários
        return role == "DIRETORIA"

    if permission == "alunos_crud":
        return role == "DIRETORIA"

    if permission == "atividades_criar":
        return role in ("DIRETORIA", "PROFESSOR")

    if permission == "atividades_editar":
        return role == "DIRETORIA"

    # leitura geral:
    if permission == "ver_tudo":
        return role in ("DIRETORIA", "PROFESSOR")

    if permission == "ver_restrito_aluno":
        return role in ("RESPONSAVEL", "ALUNO")

    return False


@app.context_processor
def inject_can():
    return dict(can=can)


# ---------------------------
# INDEX (painel sem contadores)
# ---------------------------
@app.route("/")
@login_required
def index():
    return render_template("index.html")


# ---------------------------
# USUÁRIOS (lista só DIRETORIA)
# ---------------------------
@app.route("/usuarios/", methods=["GET"])
@login_required
def usuarios_list():
    if not current_user.is_diretoria():
        flash("Acesso restrito à DIRETORIA.", "warning")
        return redirect(url_for("index"))

    items = Usuario.query.order_by(Usuario.email.asc()).all()
    alunos = Aluno.query.order_by(Aluno.nome.asc()).all()
    return render_template("usuarios/listar.html", items=items, alunos=alunos)


@app.route("/usuarios/novo", methods=["POST"])
@login_required
def usuarios_novo():
    if not current_user.is_diretoria():
        flash("Acesso restrito à DIRETORIA.", "warning")
        return redirect(url_for("index"))

    email = request.form.get("email", "").strip().lower()
    senha = request.form.get("senha", "")
    senha2 = request.form.get("senha2", "")
    papel = (request.form.get("papel", "ALUNO") or "ALUNO").upper()
    aluno_id = request.form.get("aluno_id")  # pode ser vazio

    if not email or "@" not in email:
        flash("E-mail inválido.", "danger")
        return redirect(url_for("usuarios_list"))
    if len(senha) < 8 or not any(c.isdigit() for c in senha):
        flash("Senha deve ter 8+ caracteres e ao menos 1 dígito.", "danger")
        return redirect(url_for("usuarios_list"))
    if senha != senha2:
        flash("Confirmação de senha não confere.", "danger")
        return redirect(url_for("usuarios_list"))
    if Usuario.query.filter_by(email=email).first():
        flash("E-mail já cadastrado.", "danger")
        return redirect(url_for("usuarios_list"))

    # Para RESPONSAVEL e ALUNO, aluno_id é obrigatório
    if papel in ("RESPONSAVEL", "ALUNO") and not aluno_id:
        flash("Selecione o aluno vinculado para esse perfil.", "danger")
        return redirect(url_for("usuarios_list"))

    aluno_id_int = int(aluno_id) if aluno_id else None

    u = Usuario(
        email=email,
        senha_hash=senha,
        papel=papel,
        ativo=True,
        aluno_id=aluno_id_int,
    )
    db.session.add(u)
    db.session.commit()
    flash("Usuário criado.", "success")
    return redirect(url_for("usuarios_list"))


@app.route("/usuarios/<int:id>/editar", methods=["POST"])
@login_required
def usuarios_editar(id):
    if not current_user.is_diretoria():
        flash("Acesso restrito à DIRETORIA.", "warning")
        return redirect(url_for("index"))

    u = Usuario.query.get_or_404(id)
    papel = (request.form.get("papel", u.papel) or u.papel).upper()
    ativo = True if request.form.get("ativo") == "on" else False
    new_pass = request.form.get("nova_senha", "").strip()
    aluno_id = request.form.get("aluno_id")

    if new_pass:
        if len(new_pass) < 8 or not any(c.isdigit() for c in new_pass):
            flash("Nova senha inválida (8+ e 1 dígito).", "danger")
            return redirect(url_for("usuarios_list"))
        u.senha_hash = new_pass

    # Para RESPONSAVEL e ALUNO, exigir aluno vinculado
    if papel in ("RESPONSAVEL", "ALUNO") and not aluno_id:
        flash("Selecione o aluno vinculado para esse perfil.", "danger")
        return redirect(url_for("usuarios_list"))

    u.papel = papel
    u.ativo = ativo
    u.aluno_id = int(aluno_id) if aluno_id else None

    db.session.commit()
    flash("Usuário atualizado.", "success")
    return redirect(url_for("usuarios_list"))


@app.route("/usuarios/<int:id>/excluir", methods=["POST"])
@login_required
def usuarios_excluir(id):
    if not current_user.is_diretoria():
        flash("Acesso restrito à DIRETORIA.", "warning")
        return redirect(url_for("index"))
    if current_user.id == id:
        flash("Você não pode excluir a si mesmo.", "warning")
        return redirect(url_for("usuarios_list"))
    u = Usuario.query.get_or_404(id)
    db.session.delete(u)
    db.session.commit()
    flash("Usuário removido.", "success")
    return redirect(url_for("usuarios_list"))


# ---------------------------
# ESCOLAS
# ---------------------------
@app.route("/escolas/")
@login_required
def escolas_list():
    # Responsável e Aluno não podem acessar
    if current_user.is_responsavel() or current_user.is_aluno():
        flash("Acesso não autorizado.", "warning")
        return redirect(url_for("index"))

    items = Escola.query.order_by(Escola.nome.asc()).all()
    return render_template("escolas/listar.html", items=items)


@app.route("/escolas/novo", methods=["GET", "POST"])
@login_required
def escolas_nova():
    if not current_user.is_diretoria():
        flash("Acesso não autorizado.", "warning")
        return redirect(url_for("index"))

    if request.method == "POST":
        nome = request.form.get("nome", "").strip()
        if not nome:
            flash("Informe o nome da escola.", "danger")
            return redirect(url_for("escolas_nova"))
        if Escola.query.filter_by(nome=nome).first():
            flash("Já existe escola com esse nome.", "warning")
            return redirect(url_for("escolas_list"))
        e = Escola(nome=nome)
        db.session.add(e)
        db.session.commit()
        flash("Escola cadastrada.", "success")
        return redirect(url_for("escolas_list"))
    return render_template("escolas/form.html")


@app.route("/escolas/<int:id>/editar", methods=["POST"])
@login_required
def escolas_editar(id):
    if not current_user.is_diretoria():
        flash("Acesso não autorizado.", "warning")
        return redirect(url_for("index"))

    e = Escola.query.get_or_404(id)
    nome = request.form.get("nome", "").strip()
    if not nome:
        flash("Informe o nome.", "danger")
        return redirect(url_for("escolas_list"))
    if Escola.query.filter(Escola.id != id, Escola.nome == nome).first():
        flash("Já existe escola com esse nome.", "warning")
        return redirect(url_for("escolas_list"))
    e.nome = nome
    db.session.commit()
    flash("Escola atualizada.", "success")
    return redirect(url_for("escolas_list"))


@app.route("/escolas/<int:id>/excluir", methods=["POST"])
@login_required
def escolas_excluir(id):
    if not current_user.is_diretoria():
        flash("Acesso não autorizado.", "warning")
        return redirect(url_for("index"))

    e = Escola.query.get_or_404(id)
    db.session.delete(e)
    db.session.commit()
    flash("Escola excluída.", "success")
    return redirect(url_for("escolas_list"))


# ---------------------------
# SÉRIES
# ---------------------------
@app.route("/series/")
@login_required
def series_list():
    if current_user.is_responsavel() or current_user.is_aluno():
        flash("Acesso não autorizado.", "warning")
        return redirect(url_for("index"))

    series = Serie.query.order_by(Serie.nome.asc()).all()
    return render_template("series/listar.html", series=series)


@app.route("/series/novo", methods=["GET", "POST"])
@login_required
def series_nova():
    if not current_user.is_diretoria():
        flash("Acesso não autorizado.", "warning")
        return redirect(url_for("index"))

    if request.method == "POST":
        nome = request.form.get("nome", "").strip()
        if not nome:
            flash("Informe o nome da série.", "danger")
            return redirect(url_for("series_nova"))
        if Serie.query.filter_by(nome=nome).first():
            flash("Já existe série com esse nome.", "warning")
            return redirect(url_for("series_list"))
        s = Serie(nome=nome)
        db.session.add(s)
        db.session.commit()
        flash("Série cadastrada.", "success")
        return redirect(url_for("series_list"))
    return render_template("series/form.html")


@app.route("/series/<int:id>/editar", methods=["POST"])
@login_required
def series_editar(id):
    if not current_user.is_diretoria():
        flash("Acesso não autorizado.", "warning")
        return redirect(url_for("index"))

    s = Serie.query.get_or_404(id)
    nome = request.form.get("nome", "").strip()
    if not nome:
        flash("Informe o nome.", "danger")
        return redirect(url_for("series_list"))
    if Serie.query.filter(Serie.id != id, Serie.nome == nome).first():
        flash("Já existe série com esse nome.", "warning")
        return redirect(url_for("series_list"))
    s.nome = nome
    db.session.commit()
    flash("Série atualizada.", "success")
    return redirect(url_for("series_list"))


@app.route("/series/<int:id>/excluir", methods=["POST"])
@login_required
def series_excluir(id):
    if not current_user.is_diretoria():
        flash("Acesso não autorizado.", "warning")
        return redirect(url_for("index"))

    s = Serie.query.get_or_404(id)
    db.session.delete(s)
    db.session.commit()
    flash("Série excluída.", "success")
    return redirect(url_for("series_list"))


# ---------------------------
# HORÁRIOS
# ---------------------------
@app.route("/horarios/")
@login_required
def horarios_list():
    if current_user.is_responsavel() or current_user.is_aluno():
        flash("Acesso não autorizado.", "warning")
        return redirect(url_for("index"))

    items = Horario.query.order_by(Horario.hora_inicio.asc()).all()
    for h in items:
        h.hora_inicio = HoraStrWrapper(h.hora_inicio)
        h.hora_fim = HoraStrWrapper(h.hora_fim)
    return render_template("horarios/listar.html", items=items)


@app.route("/horarios/novo", methods=["GET", "POST"])
@login_required
def horarios_novo():
    if not current_user.is_diretoria():
        flash("Acesso não autorizado.", "warning")
        return redirect(url_for("index"))

    if request.method == "POST":
        h_ini = request.form.get("hora_inicio", "").strip()
        h_fim = request.form.get("hora_fim", "").strip()
        if not _is_hhmm(h_ini) or not _is_hhmm(h_fim):
            flash("Informe horas válidas no formato HH:MM.", "danger")
            return redirect(url_for("horarios_novo"))
        if h_fim <= h_ini:
            flash("Hora fim deve ser maior que hora início.", "danger")
            return redirect(url_for("horarios_novo"))
        h = Horario(hora_inicio=h_ini, hora_fim=h_fim)
        db.session.add(h)
        db.session.commit()
        flash("Horário cadastrado.", "success")
        return redirect(url_for("horarios_list"))
    return render_template("horarios/form.html")


# Alias para corrigir url_for('horarios_new') eventualmente usado em templates
app.add_url_rule("/horarios/novo", endpoint="horarios_new", view_func=horarios_novo)


@app.route("/horarios/<int:id>/editar", methods=["POST"])
@login_required
def horarios_editar(id):
    if not current_user.is_diretoria():
        flash("Acesso não autorizado.", "warning")
        return redirect(url_for("index"))

    h = Horario.query.get_or_404(id)
    h_ini = request.form.get("hora_inicio", "").strip()
    h_fim = request.form.get("hora_fim", "").strip()
    if not _is_hhmm(h_ini) or not _is_hhmm(h_fim) or h_fim <= h_ini:
        flash("Horas inválidas.", "danger")
        return redirect(url_for("horarios_list"))
    h.hora_inicio = h_ini
    h.hora_fim = h_fim
    db.session.commit()
    flash("Horário atualizado.", "success")
    return redirect(url_for("horarios_list"))


@app.route("/horarios/<int:id>/excluir", methods=["POST"])
@login_required
def horarios_excluir(id):
    if not current_user.is_diretoria():
        flash("Acesso não autorizado.", "warning")
        return redirect(url_for("index"))

    h = Horario.query.get_or_404(id)
    db.session.delete(h)
    db.session.commit()
    flash("Horário excluído.", "success")
    return redirect(url_for("horarios_list"))


# ---------------------------
# ALUNOS
# ---------------------------
@app.route("/alunos/")
@login_required
def alunos_list():
    # Agora TODOS os perfis veem a lista completa de alunos
    items = Aluno.query.order_by(Aluno.nome.asc()).all()
    return render_template("alunos/listar.html", items=items)


@app.route("/alunos/novo", methods=["GET", "POST"])
@login_required
def alunos_novo():
    if not current_user.is_diretoria():
        flash("Acesso não autorizado.", "warning")
        return redirect(url_for("alunos_list"))

    if request.method == "POST":
        # campos principais
        nome = request.form.get("nome", "").strip()
        escola_id = request.form.get("escola_id")
        serie_id = request.form.get("serie_id")
        horario_id = request.form.get("horario_id")

        telefone_cel = request.form.get("telefone_cel")
        telefone_fixo = request.form.get("telefone_fixo")
        observacoes = request.form.get("observacoes")
        foto_path = request.form.get("foto_path")

        # campos extra
        naturalidade = request.form.get("naturalidade")
        nacionalidade = request.form.get("nacionalidade")
        data_nasc = request.form.get("data_nascimento")
        idade = request.form.get("idade") or None
        sexo = request.form.get("sexo")
        nome_pai = request.form.get("nome_pai")
        nome_mae = request.form.get("nome_mae")
        endereco = request.form.get("endereco")
        numero = request.form.get("numero")
        bairro = request.form.get("bairro")
        tem_dif = True if request.form.get("tem_dificuldade") == "on" else False
        qual_dif = request.form.get("qual_dificuldade")
        toma_med = True if request.form.get("toma_medicamento") == "on" else False
        qual_med = request.form.get("qual_medicamento")
        inicio_aulas = request.form.get("inicio_aulas")
        mensalidade_opcao = request.form.get("mensalidade_opcao")

        a = Aluno(
            nome=nome,
            escola_id=int(escola_id) if escola_id else None,
            serie_id=int(serie_id) if serie_id else None,
            horario_id=int(horario_id) if horario_id else None,
            telefone_cel=telefone_cel,
            telefone_fixo=telefone_fixo,
            observacoes=observacoes,
            foto_path=foto_path,
            naturalidade=naturalidade,
            nacionalidade=nacionalidade,
            data_nascimento=datetime.strptime(data_nasc, "%Y-%m-%d").date()
            if data_nasc
            else None,
            idade=int(idade) if idade else None,
            sexo=sexo,
            nome_pai=nome_pai,
            nome_mae=nome_mae,
            endereco=endereco,
            numero=numero,
            bairro=bairro,
            tem_dificuldade=tem_dif,
            qual_dificuldade=qual_dif,
            toma_medicamento=toma_med,
            qual_medicamento=qual_med,
            inicio_aulas=datetime.strptime(inicio_aulas, "%Y-%m-%d").date()
            if inicio_aulas
            else None,
            mensalidade_opcao=mensalidade_opcao,
        )
        db.session.add(a)
        db.session.commit()
        flash("Aluno cadastrado.", "success")
        return redirect(url_for("alunos_list"))

    escolas = Escola.query.order_by(Escola.nome.asc()).all()
    series = Serie.query.order_by(Serie.nome.asc()).all()
    horarios = Horario.query.order_by(Horario.hora_inicio.asc()).all()
    return render_template(
        "alunos/form.html", escolas=escolas, series=series, horarios=horarios
    )


# Alias opcional para compatibilidade (se tiver url_for('alunos_new'))
app.add_url_rule("/alunos/novo", endpoint="alunos_new", view_func=alunos_novo)


@app.route("/alunos/<int:id>/editar", methods=["GET", "POST"])
@login_required
def alunos_editar(id):
    if not current_user.is_diretoria():
        flash("Acesso não autorizado.", "warning")
        return redirect(url_for("alunos_list"))

    a = Aluno.query.get_or_404(id)
    if request.method == "POST":
        a.nome = request.form.get("nome", a.nome).strip()
        a.escola_id = (
            int(request.form.get("escola_id")) if request.form.get("escola_id") else None
        )
        a.serie_id = (
            int(request.form.get("serie_id")) if request.form.get("serie_id") else None
        )
        a.horario_id = (
            int(request.form.get("horario_id"))
            if request.form.get("horario_id")
            else None
        )
        a.telefone_cel = request.form.get("telefone_cel")
        a.telefone_fixo = request.form.get("telefone_fixo")
        a.observacoes = request.form.get("observacoes")
        a.foto_path = request.form.get("foto_path")

        # extras
        a.naturalidade = request.form.get("naturalidade")
        a.nacionalidade = request.form.get("nacionalidade")
        data_nasc = request.form.get("data_nascimento")
        a.data_nascimento = (
            datetime.strptime(data_nasc, "%Y-%m-%d").date() if data_nasc else None
        )
        idade = request.form.get("idade")
        a.idade = int(idade) if idade else None
        a.sexo = request.form.get("sexo")
        a.nome_pai = request.form.get("nome_pai")
        a.nome_mae = request.form.get("nome_mae")
        a.endereco = request.form.get("endereco")
        a.numero = request.form.get("numero")
        a.bairro = request.form.get("bairro")
        a.tem_dificuldade = (
            True if request.form.get("tem_dificuldade") == "on" else False
        )
        a.qual_dificuldade = request.form.get("qual_dificuldade")
        a.toma_medicamento = (
            True if request.form.get("toma_medicamento") == "on" else False
        )
        a.qual_medicamento = request.form.get("qual_medicamento")
        inicio_aulas = request.form.get("inicio_aulas")
        a.inicio_aulas = (
            datetime.strptime(inicio_aulas, "%Y-%m-%d").date()
            if inicio_aulas
            else None
        )
        a.mensalidade_opcao = request.form.get("mensalidade_opcao")

        db.session.commit()
        flash("Aluno atualizado.", "success")
        return redirect(url_for("alunos_list"))

    escolas = Escola.query.order_by(Escola.nome.asc()).all()
    series = Serie.query.order_by(Serie.nome.asc()).all()
    horarios = Horario.query.order_by(Horario.hora_inicio.asc()).all()
    return render_template(
        "alunos/form.html",
        aluno=a,
        escolas=escolas,
        series=series,
        horarios=horarios,
    )


@app.route("/alunos/<int:id>/excluir", methods=["POST"])
@login_required
def alunos_excluir(id):
    if not current_user.is_diretoria():
        flash("Acesso não autorizado.", "warning")
        return redirect(url_for("alunos_list"))

    a = Aluno.query.get_or_404(id)
    db.session.delete(a)
    db.session.commit()
    flash("Aluno excluído.", "success")
    return redirect(url_for("alunos_list"))


@app.route("/alunos/<int:id>")
@login_required
def alunos_ver(id):
    a = Aluno.query.get_or_404(id)

    # Diretoria e Professor podem ver qualquer aluno
    if current_user.is_diretoria() or current_user.is_professor():
        pass
    else:
        # Responsável / Aluno: só pode ver o aluno vinculado
        if not current_user.aluno_id or current_user.aluno_id != a.id:
            flash("Você não tem permissão para ver os dados deste aluno.", "warning")
            return redirect(url_for("alunos_list"))

    return render_template("alunos/ver.html", aluno=a)


# ---------- API DE BUSCA DE ALUNOS (usada em atividades, se houver JS) ----------
@app.route("/alunos/search")
@login_required
def alunos_search():
    q = request.args.get("q", "").strip()
    query = Aluno.query
    if q:
        like = f"%{q}%"
        query = query.filter(Aluno.nome.ilike(like))
    alunos = query.order_by(Aluno.nome.asc()).all()
    return jsonify([{"id": a.id, "nome": a.nome} for a in alunos])


# ---------------------------
# ATIVIDADES
# ---------------------------
@app.route("/atividades/")
@login_required
def atividades_listar():
    # Filtra atividades conforme o papel
    if current_user.is_diretoria() or current_user.is_professor():
        itens = Atividade.query.order_by(
            Atividade.data.desc(), Atividade.id.desc()
        ).all()
    else:
        # RESPONSAVEL / ALUNO: apenas do aluno vinculado
        if not current_user.aluno_id:
            itens = []
        else:
            itens = (
                Atividade.query.filter_by(aluno_id=current_user.aluno_id)
                .order_by(Atividade.data.desc(), Atividade.id.desc())
                .all()
            )

    alunos = Aluno.query.order_by(Aluno.nome.asc()).all()
    return render_template("atividades/listar.html", atividades=itens, alunos=alunos)


# Alias para compatibilidade com url_for('atividades_list')
app.add_url_rule(
    "/atividades/", endpoint="atividades_list", view_func=atividades_listar
)


@app.route("/atividades/novo", methods=["GET", "POST"])
@login_required
def atividades_nova():
    # Só diretoria e professor podem lançar novas atividades
    if not (current_user.is_diretoria() or current_user.is_professor()):
        flash("Você não tem permissão para adicionar atividades.", "warning")
        return redirect(url_for("atividades_listar"))

    if request.method == "POST":
        aluno_id = request.form.get("aluno_id")
        data_str = request.form.get("data")
        professor = request.form.get("professor")
        conteudo = request.form.get("conteudo")
        observacao = request.form.get("observacao")

        if not aluno_id or not data_str or not professor or not conteudo:
            flash("Preencha os campos obrigatórios.", "danger")
            return redirect(url_for("atividades_nova"))

        data_dt = datetime.strptime(data_str, "%Y-%m-%d").date()
        atv = Atividade(
            aluno_id=int(aluno_id),
            data=data_dt,
            professor=professor,
            conteudo=conteudo,
            observacao=observacao,
        )
        db.session.add(atv)
        db.session.commit()
        flash("Atividade cadastrada.", "success")
        return redirect(url_for("atividades_listar"))

    alunos = Aluno.query.order_by(Aluno.nome.asc()).all()
    return render_template("atividades/novo.html", alunos=alunos, item=None)


@app.route("/atividades/<int:id>/editar", methods=["GET", "POST"])
@login_required
def atividades_editar(id):
    # Apenas DIRETORIA pode editar
    if not current_user.is_diretoria():
        flash("Você não tem permissão para editar atividades.", "warning")
        return redirect(url_for("atividades_listar"))

    atv = Atividade.query.get_or_404(id)
    if request.method == "POST":
        atv.aluno_id = int(request.form.get("aluno_id"))
        data_str = request.form.get("data")
        atv.data = (
            datetime.strptime(data_str, "%Y-%m-%d").date() if data_str else atv.data
        )
        atv.professor = request.form.get("professor")
        atv.conteudo = request.form.get("conteudo")
        atv.observacao = request.form.get("observacao")
        db.session.commit()
        flash("Atividade atualizada.", "success")
        return redirect(url_for("atividades_listar"))

    alunos = Aluno.query.order_by(Aluno.nome.asc()).all()
    return render_template("atividades/form.html", item=atv, alunos=alunos)


@app.route("/atividades/<int:id>/excluir", methods=["POST"])
@login_required
def atividades_excluir(id):
    # Apenas DIRETORIA pode excluir
    if not current_user.is_diretoria():
        flash("Você não tem permissão para excluir atividades.", "warning")
        return redirect(url_for("atividades_listar"))

    atv = Atividade.query.get_or_404(id)
    db.session.delete(atv)
    db.session.commit()
    flash("Atividade excluída.", "success")
    return redirect(url_for("atividades_listar"))


# ---------------------------
# SEED ADMIN
# ---------------------------
def seed_admin():
    if not Usuario.query.filter_by(email="admin@escola.com").first():
        u = Usuario(
            email="admin@escola.com",
            senha_hash="Trocar123",
            papel="DIRETORIA",
            ativo=True,
        )
        db.session.add(u)
        db.session.commit()


# ---------------------------
# BOOT
# ---------------------------
if __name__ == "__main__":
    with app.app_context():
        db.create_all()
        ensure_schema()
        seed_admin()
    app.run(debug=True)
