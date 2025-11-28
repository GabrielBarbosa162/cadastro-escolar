import os
import random
import smtplib
from email.mime.text import MIMEText
from datetime import datetime, date
import subprocess
import sys
import shlex

from flask import (
    Flask,
    render_template,
    redirect,
    url_for,
    request,
    flash,
    jsonify,
    session,
)
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
from werkzeug.utils import secure_filename


# ============================================================
# CONFIGURAÇÃO DO SISTEMA
# ============================================================
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DB_PATH = os.path.join(BASE_DIR, "alunos.db")

app = Flask(__name__)
app.config["SECRET_KEY"] = "dev-secret"
app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{DB_PATH}"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False


# ============================================================
# UPLOADS
# ============================================================
UPLOAD_FOLDER = os.path.join(BASE_DIR, "static", "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER


# ============================================================
# BANCO DE DADOS
# ============================================================
db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = "login"


# ============================================================
# HELPERS
# ============================================================
class HoraStrWrapper:
    """Permite que strings HH:MM se comportem como datetime.strftime()."""

    def __init__(self, text):
        self.text = text or ""

    def strftime(self, fmt):
        return self.text


def salvar_foto(file_storage, foto_atual=None):
    """Salva foto do aluno."""
    if not file_storage:
        return foto_atual
    filename = secure_filename(file_storage.filename or "")
    if filename == "":
        return foto_atual
    caminho = os.path.join(app.config["UPLOAD_FOLDER"], filename)
    file_storage.save(caminho)
    return f"uploads/{filename}"


# ============================================================
# ENVIO DO CÓDIGO VIA WHATSAPP (Selenium - WhatsApp Web)
# ============================================================

def enviar_codigo_whatsapp(numero, codigo) -> bool:
    """
    Executa o script enviar_whatsapp.py em background (headless).
    """

    numero_limpo = "".join(filter(str.isdigit, numero))
    mensagem = f"Seu código de recuperação é: {codigo}"

    cmd = f'{sys.executable} enviar_whatsapp.py {numero_limpo} "{mensagem}"'

    try:
        resultado = subprocess.run(
            shlex.split(cmd),
            capture_output=True,
            text=True,
            timeout=180
        )

        print("STDOUT enviar_whatsapp:", resultado.stdout)
        print("STDERR enviar_whatsapp:", resultado.stderr)

        return resultado.returncode == 0

    except Exception as e:
        print("Erro ao chamar enviar_whatsapp.py:", e)
        return False


# ============================================================
# VALIDAÇÃO DE HORÁRIO
# ============================================================
def _is_hhmm(val: str) -> bool:
    if not val or len(val) != 5 or val[2] != ":":
        return False
    hh, mm = val.split(":")
    return hh.isdigit() and mm.isdigit() and 0 <= int(hh) <= 23 and 0 <= int(mm) <= 59
# ============================================================
# MODELOS
# ============================================================
class Usuario(db.Model, UserMixin):
    __tablename__ = "usuario"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    senha_hash = db.Column(db.String(255), nullable=False)
    papel = db.Column(db.String(30), nullable=False, default="ALUNO")
    ativo = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    # Vínculo opcional com um aluno específico
    aluno_id = db.Column(db.Integer, db.ForeignKey("aluno.id"), nullable=True)
    aluno = db.relationship("Aluno", lazy="joined")

    # Helpers de papel
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
    # Guardados como strings "HH:MM"
    hora_inicio = db.Column(db.String(5), nullable=False)
    hora_fim = db.Column(db.String(5), nullable=False)


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

    # Campos estendidos do cadastro de alunos
    naturalidade = db.Column(db.String(120))
    nacionalidade = db.Column(db.String(120))
    data_nascimento = db.Column(db.Date)
    idade = db.Column(db.Integer)
    sexo = db.Column(db.String(1))  # 'M' ou 'F'
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
    mensalidade_opcao = db.Column(db.String(60))  # ex: "PRE_1_A_5", "6_A_7", "8_A_9"

    # Relacionamentos de conveniência
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

# ============================================================
# LOGIN / AUTENTICAÇÃO
# ============================================================

@login_manager.user_loader
def load_user(uid):
    return db.session.get(Usuario, int(uid))


# ------------------------------------------------------------
# LOGIN
# ------------------------------------------------------------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        senha = request.form.get("senha", "").strip()

        user = Usuario.query.filter_by(email=email).first()

        if user and user.ativo and user.senha_hash == senha:
            login_user(user)
            return redirect(url_for("index"))

        flash("Credenciais inválidas.", "danger")
        return redirect(url_for("login"))

    return render_template("auth/login.html")


# ============================================================
# ESQUECI MINHA SENHA — SOMENTE WHATSAPP
# ============================================================

# ------------------------------------------------------------
# ETAPA 1 — Usuário informa e-mail → vai direto para WhatsApp
# ------------------------------------------------------------
@app.route("/esqueci", methods=["GET", "POST"])
def esqueci():
    """
    Nesta versão, o usuário NÃO escolhe método.
    Não existe e-mail, apenas WhatsApp.
    Primeiro ele informa o e-mail, depois o número.
    """
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()

        if not email:
            flash("Informe o e-mail cadastrado.", "danger")
            return redirect(url_for("esqueci"))

        user = Usuario.query.filter_by(email=email).first()
        if not user:
            flash("E-mail não encontrado.", "danger")
            return redirect(url_for("esqueci"))

        # Guarda o email para as próximas etapas
        session["rec_email"] = email

        return redirect(url_for("esqueci_whatsapp"))

    return render_template("auth/esqueci.html")


# ------------------------------------------------------------
# ETAPA 2 — Usuário digita o número do WhatsApp
# ------------------------------------------------------------
@app.route("/esqueci/whatsapp", methods=["GET", "POST"])
def esqueci_whatsapp():
    email = session.get("rec_email")
    if not email:
        flash("Sessão expirada. Recomece o processo.", "warning")
        return redirect(url_for("esqueci"))

    if request.method == "POST":
        numero = request.form.get("whatsapp", "").strip()

        if not numero:
            flash("Informe o número de WhatsApp.", "danger")
            return redirect(url_for("esqueci_whatsapp"))

        # Gera o código
        codigo = random.randint(100000, 999999)
        session["rec_codigo"] = str(codigo)

        # Envia pelo Selenium → WhatsApp Web
        enviado = enviar_codigo_whatsapp(numero, codigo)

        if enviado:
            flash("Código enviado via WhatsApp!", "success")
        else:
            flash(
                f"(Modo teste) Não foi possível enviar automaticamente. "
                f"Seu código é: {codigo}",
                "warning",
            )

        return redirect(url_for("verificar_codigo"))

    return render_template("auth/esqueci_whatsapp.html")


# ------------------------------------------------------------
# ETAPA 3 — Usuário digita o código recebido
# ------------------------------------------------------------
@app.route("/verificar-codigo", methods=["GET", "POST"])
def verificar_codigo():
    if request.method == "POST":
        cod_digitado = request.form.get("codigo", "").strip()
        cod_correto = session.get("rec_codigo")

        if cod_digitado == cod_correto:
            return redirect(url_for("redefinir_senha"))

        flash("Código incorreto.", "danger")
        return redirect(url_for("verificar_codigo"))

    return render_template("auth/verificar_codigo.html")


# ------------------------------------------------------------
# ETAPA 4 — Redefinição da senha
# ------------------------------------------------------------
@app.route("/redefinir-senha", methods=["GET", "POST"])
def redefinir_senha():
    email = session.get("rec_email")
    if not email:
        flash("Sessão expirada. Recomece o processo.", "warning")
        return redirect(url_for("esqueci"))

    if request.method == "POST":
        senha1 = request.form.get("senha1", "")
        senha2 = request.form.get("senha2", "")

        if senha1 != senha2:
            flash("As senhas não coincidem.", "danger")
            return redirect(url_for("redefinir_senha"))

        if len(senha1) < 8 or not any(c.isdigit() for c in senha1):
            flash("Senha inválida: mínimo 8 caracteres + 1 número.", "danger")
            return redirect(url_for("redefinir_senha"))

        user = Usuario.query.filter_by(email=email).first()
        if not user:
            flash("Usuário não encontrado.", "danger")
            return redirect(url_for("login"))

        user.senha_hash = senha1
        db.session.commit()

        # limpa sessão
        session.pop("rec_email", None)
        session.pop("rec_codigo", None)

        flash("Senha redefinida com sucesso!", "success")
        return redirect(url_for("login"))

    return render_template("auth/redefinir_senha.html")


# ------------------------------------------------------------
# LOGOUT
# ------------------------------------------------------------
@app.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))
# ============================================================
# PERMISSÕES / AUTORIZAÇÃO
# ============================================================

def can(permission: str) -> bool:
    """
    Helper usado nos templates Jinja: {{ can('alguma_coisa') }}
    Controla o que cada papel pode fazer / ver.
    """
    if not current_user.is_authenticated:
        return False

    role = current_user.papel_upper()

    # DIRETORIA pode tudo
    if role == "DIRETORIA":
        return True

    # -----------------------------
    # Permissões específicas
    # -----------------------------
    if permission == "ver_usuarios":
        return False  # só diretoria

    if permission == "gerenciar_usuarios":
        return False  # só diretoria

    if permission == "gerenciar_estrutura":
        # escolas, séries, horários — só diretoria
        return role == "DIRETORIA"

    if permission == "alunos_crud":
        # criar/editar/excluir alunos — só diretoria
        return role == "DIRETORIA"

    if permission == "atividades_criar":
        # professores e diretoria podem lançar atividades
        return role in ("DIRETORIA", "PROFESSOR")

    if permission == "atividades_editar":
        # só diretoria pode editar/excluir atividades
        return role == "DIRETORIA"

    if permission == "ver_tudo":
        # diretoria e professor veem tudo
        return role in ("DIRETORIA", "PROFESSOR")

    if permission == "ver_restrito_aluno":
        # responsável e aluno veem apenas o aluno vinculado
        return role in ("RESPONSAVEL", "ALUNO")

    return False


@app.context_processor
def inject_can():
    """
    Deixa {{ can(...) }} disponível em todos os templates.
    """
    return dict(can=can)


# ============================================================
# PÁGINA INICIAL
# ============================================================
@app.route("/")
@login_required
def index():
    return render_template("index.html")


# ============================================================
# USUÁRIOS (SOMENTE DIRETORIA)
# ============================================================

@app.route("/usuarios/", methods=["GET"])
@login_required
def usuarios_list():
    if not current_user.is_diretoria():
        flash("Acesso restrito à DIRETORIA.", "warning")
        return redirect(url_for("index"))

    usuarios = Usuario.query.order_by(Usuario.email.asc()).all()
    alunos = Aluno.query.order_by(Aluno.nome.asc()).all()
    return render_template("usuarios/listar.html", usuarios=usuarios, alunos=alunos)


@app.route("/usuarios/novo", methods=["POST"])
@login_required
def usuarios_novo():
    if not current_user.is_diretoria():
        flash("Acesso restrito à DIRETORIA.", "warning")
        return redirect(url_for("index"))

    email = request.form.get("email", "").strip().lower()
    senha = request.form.get("senha", "").strip()
    senha2 = request.form.get("senha2", "").strip()
    papel = (request.form.get("papel", "ALUNO") or "ALUNO").upper()
    aluno_id = request.form.get("aluno_id")

    if not email or "@" not in email:
        flash("Informe um e-mail válido.", "danger")
        return redirect(url_for("usuarios_list"))

    if Usuario.query.filter_by(email=email).first():
        flash("Já existe usuário com esse e-mail.", "danger")
        return redirect(url_for("usuarios_list"))

    if len(senha) < 8 or not any(c.isdigit() for c in senha):
        flash("Senha deve ter no mínimo 8 caracteres e conter número.", "danger")
        return redirect(url_for("usuarios_list"))

    if senha != senha2:
        flash("Confirmação de senha não confere.", "danger")
        return redirect(url_for("usuarios_list"))

    # Responsável e Aluno precisam estar vinculados a um aluno
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
    flash("Usuário criado com sucesso.", "success")
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
    aluno_id = request.form.get("aluno_id")
    nova_senha = request.form.get("nova_senha", "").strip()

    if nova_senha:
        if len(nova_senha) < 8 or not any(c.isdigit() for c in nova_senha):
            flash("Nova senha inválida (mín. 8 caracteres + número).", "danger")
            return redirect(url_for("usuarios_list"))
        u.senha_hash = nova_senha

    if papel in ("RESPONSAVEL", "ALUNO") and not aluno_id:
        flash("Selecione o aluno vinculado para esse perfil.", "danger")
        return redirect(url_for("usuarios_list"))

    u.papel = papel
    u.ativo = ativo
    u.aluno_id = int(aluno_id) if aluno_id else None

    db.session.commit()
    flash("Usuário atualizado com sucesso.", "success")
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
    flash("Usuário excluído com sucesso.", "success")
    return redirect(url_for("usuarios_list"))


# ============================================================
# ESCOLAS
# ============================================================

@app.route("/escolas/")
@login_required
def escolas_list():
    # Responsável e Aluno não têm acesso
    if current_user.is_responsavel() or current_user.is_aluno():
        flash("Acesso não autorizado.", "warning")
        return redirect(url_for("index"))

    escolas = Escola.query.order_by(Escola.nome.asc()).all()
    return render_template("escolas/listar.html", escolas=escolas)


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
            flash("Já existe escola com esse nome.", "danger")
            return redirect(url_for("escolas_list"))

        e = Escola(nome=nome)
        db.session.add(e)
        db.session.commit()
        flash("Escola cadastrada com sucesso.", "success")
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
        flash("Informe o nome da escola.", "danger")
        return redirect(url_for("escolas_list"))

    if Escola.query.filter(Escola.id != id, Escola.nome == nome).first():
        flash("Já existe escola com esse nome.", "danger")
        return redirect(url_for("escolas_list"))

    e.nome = nome
    db.session.commit()
    flash("Escola atualizada com sucesso.", "success")
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
    flash("Escola excluída com sucesso.", "success")
    return redirect(url_for("escolas_list"))


# ============================================================
# SÉRIES
# ============================================================

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
            flash("Já existe série com esse nome.", "danger")
            return redirect(url_for("series_list"))

        s = Serie(nome=nome)
        db.session.add(s)
        db.session.commit()
        flash("Série cadastrada com sucesso.", "success")
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
        flash("Informe o nome da série.", "danger")
        return redirect(url_for("series_list"))

    if Serie.query.filter(Serie.id != id, Serie.nome == nome).first():
        flash("Já existe série com esse nome.", "danger")
        return redirect(url_for("series_list"))

    s.nome = nome
    db.session.commit()
    flash("Série atualizada com sucesso.", "success")
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
    flash("Série excluída com sucesso.", "success")
    return redirect(url_for("series_list"))


# ============================================================
# HORÁRIOS
# ============================================================

@app.route("/horarios/")
@login_required
def horarios_list():
    if current_user.is_responsavel() or current_user.is_aluno():
        flash("Acesso não autorizado.", "warning")
        return redirect(url_for("index"))

    horarios = Horario.query.order_by(Horario.hora_inicio.asc()).all()
    # Wrap para permitir usar .strftime('%H:%M') nos templates
    for h in horarios:
        h.hora_inicio = HoraStrWrapper(h.hora_inicio)
        h.hora_fim = HoraStrWrapper(h.hora_fim)
    return render_template("horarios/listar.html", horarios=horarios)


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
            flash("Informe horários válidos no formato HH:MM.", "danger")
            return redirect(url_for("horarios_novo"))

        if h_fim <= h_ini:
            flash("Hora final deve ser maior que hora inicial.", "danger")
            return redirect(url_for("horarios_novo"))

        h = Horario(hora_inicio=h_ini, hora_fim=h_fim)
        db.session.add(h)
        db.session.commit()
        flash("Horário cadastrado com sucesso.", "success")
        return redirect(url_for("horarios_list"))

    return render_template("horarios/form.html")


# Alias para corrigir templates que usam endpoint 'horarios_new'
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
        flash("Horários inválidos.", "danger")
        return redirect(url_for("horarios_list"))

    h.hora_inicio = h_ini
    h.hora_fim = h_fim
    db.session.commit()
    flash("Horário atualizado com sucesso.", "success")
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
    flash("Horário excluído com sucesso.", "success")
    return redirect(url_for("horarios_list"))
# ============================================================
# ALUNOS
# ============================================================

@app.route("/alunos/")
@login_required
def alunos_list():
    """
    DIRETORIA + PROFESSOR → vê TODOS os alunos.
    RESPONSÁVEL + ALUNO → vê SOMENTE o aluno vinculado.
    """

    # Diretoria e Professores podem ver tudo
    if current_user.is_diretoria() or current_user.is_professor():
        alunos = Aluno.query.order_by(Aluno.nome.asc()).all()
        return render_template("alunos/listar.html", alunos=alunos)

    # Responsável e aluno só veem o aluno vinculado
    if current_user.is_responsavel() or current_user.is_aluno():
        if not current_user.aluno_id:
            flash("Nenhum aluno vinculado a este usuário.", "warning")
            return redirect(url_for("index"))

        aluno = Aluno.query.get(current_user.aluno_id)
        return render_template("alunos/listar.html", alunos=[aluno])

    # fallback
    alunos = Aluno.query.order_by(Aluno.nome.asc()).all()
    return render_template("alunos/listar.html", alunos=alunos)



# ------------------------------------------------------------
# NOVO ALUNO
# ------------------------------------------------------------
@app.route("/alunos/novo", methods=["GET", "POST"])
@login_required
def alunos_novo():
    if not current_user.is_diretoria():
        flash("Acesso não autorizado.", "warning")
        return redirect(url_for("alunos_list"))

    if request.method == "POST":
        nome = request.form.get("nome")
        escola_id = request.form.get("escola_id")
        serie_id = request.form.get("serie_id")
        horario_id = request.form.get("horario_id")

        # Telefones
        telefone_cel = request.form.get("telefone_cel")
        telefone_fixo = request.form.get("telefone_fixo")

        # Ficha escolar completa
        naturalidade = request.form.get("naturalidade")
        nacionalidade = request.form.get("nacionalidade")
        data_nasc = request.form.get("data_nascimento")
        idade = request.form.get("idade")
        sexo = request.form.get("sexo")
        nome_pai = request.form.get("nome_pai")
        nome_mae = request.form.get("nome_mae")
        endereco = request.form.get("endereco")
        numero = request.form.get("numero")
        bairro = request.form.get("bairro")

        tem_dificuldade = request.form.get("tem_dificuldade") == "on"
        qual_dificuldade = request.form.get("qual_dificuldade")

        toma_medicamento = request.form.get("toma_medicamento") == "on"
        qual_medicamento = request.form.get("qual_medicamento")

        inicio_aulas = request.form.get("inicio_aulas")
        mensalidade_opcao = request.form.get("mensalidade_opcao")

        observacoes = request.form.get("observacoes")

        # Foto do aluno — sempre a última opção
        foto_file = request.files.get("foto")
        foto_path = salvar_foto(foto_file)

        aluno = Aluno(
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
            data_nascimento=datetime.strptime(data_nasc, "%Y-%m-%d").date() if data_nasc else None,
            idade=int(idade) if idade else None,
            sexo=sexo,
            nome_pai=nome_pai,
            nome_mae=nome_mae,
            endereco=endereco,
            numero=numero,
            bairro=bairro,
            tem_dificuldade=tem_dificuldade,
            qual_dificuldade=qual_dificuldade,
            toma_medicamento=toma_medicamento,
            qual_medicamento=qual_medicamento,
            inicio_aulas=datetime.strptime(inicio_aulas, "%Y-%m-%d").date() if inicio_aulas else None,
            mensalidade_opcao=mensalidade_opcao,
        )

        db.session.add(aluno)
        db.session.commit()

        flash("Aluno cadastrado com sucesso!", "success")
        return redirect(url_for("alunos_list"))

    escolas = Escola.query.order_by(Escola.nome.asc()).all()
    series = Serie.query.order_by(Serie.nome.asc()).all()
    horarios = Horario.query.order_by(Horario.hora_inicio.asc()).all()

    return render_template("alunos/form.html",
                           escolas=escolas,
                           series=series,
                           horarios=horarios,
                           aluno=None)



# ------------------------------------------------------------
# EDITAR ALUNO
# ------------------------------------------------------------
@app.route("/alunos/<int:id>/editar", methods=["GET", "POST"])
@login_required
def alunos_editar(id):
    if not current_user.is_diretoria():
        flash("Acesso não autorizado.", "warning")
        return redirect(url_for("alunos_list"))

    aluno = Aluno.query.get_or_404(id)

    if request.method == "POST":
        aluno.nome = request.form.get("nome")
        aluno.escola_id = int(request.form.get("escola_id")) if request.form.get("escola_id") else None
        aluno.serie_id = int(request.form.get("serie_id")) if request.form.get("serie_id") else None
        aluno.horario_id = int(request.form.get("horario_id")) if request.form.get("horario_id") else None

        aluno.telefone_cel = request.form.get("telefone_cel")
        aluno.telefone_fixo = request.form.get("telefone_fixo")

        aluno.naturalidade = request.form.get("naturalidade")
        aluno.nacionalidade = request.form.get("nacionalidade")

        data_nasc = request.form.get("data_nascimento")
        aluno.data_nascimento = datetime.strptime(data_nasc, "%Y-%m-%d").date() if data_nasc else None

        idade = request.form.get("idade")
        aluno.idade = int(idade) if idade else None

        aluno.sexo = request.form.get("sexo")
        aluno.nome_pai = request.form.get("nome_pai")
        aluno.nome_mae = request.form.get("nome_mae")
        aluno.endereco = request.form.get("endereco")
        aluno.numero = request.form.get("numero")
        aluno.bairro = request.form.get("bairro")

        aluno.tem_dificuldade = request.form.get("tem_dificuldade") == "on"
        aluno.qual_dificuldade = request.form.get("qual_dificuldade")

        aluno.toma_medicamento = request.form.get("toma_medicamento") == "on"
        aluno.qual_medicamento = request.form.get("qual_medicamento")

        inicio_aulas = request.form.get("inicio_aulas")
        aluno.inicio_aulas = datetime.strptime(inicio_aulas, "%Y-%m-%d").date() if inicio_aulas else None

        aluno.mensalidade_opcao = request.form.get("mensalidade_opcao")

        aluno.observacoes = request.form.get("observacoes")

        # Foto — mantém existente caso não envie nova
        foto_file = request.files.get("foto")
        aluno.foto_path = salvar_foto(foto_file, aluno.foto_path)

        db.session.commit()
        flash("Aluno atualizado com sucesso!", "success")
        return redirect(url_for("alunos_list"))

    escolas = Escola.query.order_by(Escola.nome.asc()).all()
    series = Serie.query.order_by(Serie.nome.asc()).all()
    horarios = Horario.query.order_by(Horario.hora_inicio.asc()).all()

    return render_template("alunos/form.html",
                           aluno=aluno,
                           escolas=escolas,
                           series=series,
                           horarios=horarios)



# ------------------------------------------------------------
# EXCLUIR ALUNO
# ------------------------------------------------------------
@app.route("/alunos/<int:id>/excluir", methods=["POST"])
@login_required
def alunos_excluir(id):
    if not current_user.is_diretoria():
        flash("Acesso não autorizado.", "warning")
        return redirect(url_for("alunos_list"))

    aluno = Aluno.query.get_or_404(id)
    db.session.delete(aluno)
    db.session.commit()

    flash("Aluno excluído com sucesso.", "success")
    return redirect(url_for("alunos_list"))



# ------------------------------------------------------------
# VER ALUNO
# ------------------------------------------------------------
@app.route("/alunos/<int:id>")
@login_required
def alunos_ver(id):
    aluno = Aluno.query.get_or_404(id)

    # Diretoria e Professores podem ver qualquer aluno
    if current_user.is_diretoria() or current_user.is_professor():
        return render_template("alunos/ver.html", aluno=aluno)

    # Responsável / aluno só podem ver o aluno vinculado
    if current_user.aluno_id != aluno.id:
        flash("Você não tem permissão para ver esse aluno.", "danger")
        return redirect(url_for("alunos_list"))

    return render_template("alunos/ver.html", aluno=aluno)



# ------------------------------------------------------------
# BUSCA PARA ATIVIDADES
# ------------------------------------------------------------
@app.route("/alunos/search")
@login_required
def alunos_search():
    q = request.args.get("q", "").strip()
    query = Aluno.query

    if q:
        query = query.filter(Aluno.nome.ilike(f"%{q}%"))

    alunos = query.order_by(Aluno.nome.asc()).all()

    return jsonify([
        {"id": aluno.id, "nome": aluno.nome}
        for aluno in alunos
    ])
# ============================================================
# ATIVIDADES
# ============================================================

@app.route("/atividades/")
@login_required
def atividades_listar():
    """
    DIRETORIA + PROFESSOR → veem TODAS as atividades.
    RESPONSÁVEL + ALUNO → veem somente as atividades do aluno vinculado.
    """
    if current_user.is_diretoria() or current_user.is_professor():
        atividades = Atividade.query.order_by(
            Atividade.data.desc(), Atividade.id.desc()
        ).all()
    else:
        if not current_user.aluno_id:
            atividades = []
        else:
            atividades = (
                Atividade.query.filter_by(aluno_id=current_user.aluno_id)
                .order_by(Atividade.data.desc(), Atividade.id.desc())
                .all()
            )

    alunos = Aluno.query.order_by(Aluno.nome.asc()).all()
    return render_template("atividades/listar.html",
                           atividades=atividades,
                           alunos=alunos)


# Alias para corrigir templates antigos que usam endpoint 'atividades_list'
app.add_url_rule("/atividades/",
                 endpoint="atividades_list",
                 view_func=atividades_listar)


# ------------------------------------------------------------
# NOVA ATIVIDADE
# ------------------------------------------------------------
@app.route("/atividades/novo", methods=["GET", "POST"])
@login_required
def atividades_nova():
    if not (current_user.is_diretoria() or current_user.is_professor()):
        flash("Você não tem permissão para lançar atividades.", "warning")
        return redirect(url_for("atividades_listar"))

    if request.method == "POST":
        aluno_id = request.form.get("aluno_id")
        data_str = request.form.get("data")
        professor = request.form.get("professor")
        conteudo = request.form.get("conteudo")
        observacao = request.form.get("observacao")

        if not aluno_id or not data_str or not professor or not conteudo:
            flash("Preencha todos os campos obrigatórios.", "danger")
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

        flash("Atividade cadastrada com sucesso!", "success")
        return redirect(url_for("atividades_listar"))

    alunos = Aluno.query.order_by(Aluno.nome.asc()).all()
    return render_template("atividades/novo.html", alunos=alunos)



# ------------------------------------------------------------
# EDITAR ATIVIDADE
# ------------------------------------------------------------
@app.route("/atividades/<int:id>/editar", methods=["GET", "POST"])
@login_required
def atividades_editar(id):
    if not current_user.is_diretoria():
        flash("Você não tem permissão para editar atividades.", "warning")
        return redirect(url_for("atividades_listar"))

    atv = Atividade.query.get_or_404(id)

    if request.method == "POST":
        atv.aluno_id = int(request.form.get("aluno_id"))

        data_str = request.form.get("data")
        atv.data = datetime.strptime(data_str, "%Y-%m-%d").date() if data_str else atv.data

        atv.professor = request.form.get("professor")
        atv.conteudo = request.form.get("conteudo")
        atv.observacao = request.form.get("observacao")

        db.session.commit()
        flash("Atividade atualizada com sucesso!", "success")
        return redirect(url_for("atividades_listar"))

    alunos = Aluno.query.order_by(Aluno.nome.asc()).all()
    return render_template("atividades/form.html", atividade=atv, alunos=alunos)



# ------------------------------------------------------------
# EXCLUIR ATIVIDADE
# ------------------------------------------------------------
@app.route("/atividades/<int:id>/excluir", methods=["POST"])
@login_required
def atividades_excluir(id):
    if not current_user.is_diretoria():
        flash("Você não tem permissão para excluir atividades.", "warning")
        return redirect(url_for("atividades_listar"))

    atv = Atividade.query.get_or_404(id)
    db.session.delete(atv)
    db.session.commit()

    flash("Atividade excluída com sucesso!", "success")
    return redirect(url_for("atividades_listar"))


# ============================================================
# MIGRAÇÃO LEVE / AJUSTE DE SCHEMA
# ============================================================

def _add_col_if_missing(table: str, column: str, ddl: str):
    """
    Adiciona coluna em tabela SQLite se ainda não existir.
    Usado para evoluir o banco sem perder dados.
    """
    info = db.session.execute(sa_text(f"PRAGMA table_info({table})")).mappings().all()
    cols = {c["name"] for c in info}
    if column not in cols:
        db.session.execute(sa_text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}"))
        db.session.commit()


def ensure_schema():
    # Ajustes na tabela atividade
    try:
        _add_col_if_missing("atividade", "data", "DATE")
        _add_col_if_missing("atividade", "professor", "TEXT")
        _add_col_if_missing("atividade", "conteudo", "TEXT")
        _add_col_if_missing("atividade", "observacao", "TEXT")
    except Exception:
        db.session.rollback()

    # Ajustes em horario
    try:
        _add_col_if_missing("horario", "hora_inicio", "TEXT")
        _add_col_if_missing("horario", "hora_fim", "TEXT")
    except Exception:
        db.session.rollback()

    # Ajustes em escola
    try:
        _add_col_if_missing("escola", "nome", "TEXT")
    except Exception:
        db.session.rollback()

    # Ajustes em usuario (vínculo com aluno)
    try:
        _add_col_if_missing("usuario", "aluno_id", "INTEGER")
    except Exception:
        db.session.rollback()

    # Ajustes extras em aluno (se necessário)
    try:
        _add_col_if_missing("aluno", "foto_path", "TEXT")
    except Exception:
        db.session.rollback()


# ============================================================
# SEED ADMIN
# ============================================================

def seed_admin():
    """
    Cria um usuário DIRETORIA padrão se ainda não existir.
    Email: admin@escola.com
    Senha: Trocar123
    """
    if not Usuario.query.filter_by(email="admin@escola.com").first():
        admin = Usuario(
            email="admin@escola.com",
            senha_hash="Trocar123",
            papel="DIRETORIA",
            ativo=True,
        )
        db.session.add(admin)
        db.session.commit()
        print("Usuário admin@escola.com criado com senha 'Trocar123'.")


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
        ensure_schema()
        seed_admin()

    app.run(debug=True)
