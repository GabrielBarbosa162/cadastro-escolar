import os
import requests
import resend
from email.mime.text import MIMEText  # se já usa em outros lugares pode manter
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

# -------------------------------------------------------------------
# CONFIGURAÃ‡ÃƒO BÃSICA
# -------------------------------------------------------------------
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DB_PATH = os.path.join(BASE_DIR, "alunos.db")

app = Flask(__name__)
app.config["SECRET_KEY"] = "dev-secret"
app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{DB_PATH}"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# Pasta para uploads de fotos de alunos
UPLOAD_FOLDER = os.path.join(BASE_DIR, "static", "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

app.config["SMTP_SERVER"] = "smtp.gmail.com"
app.config["SMTP_PORT"] = 587
app.config["SMTP_USER"] = "amos.carvalho@gmail.com"
app.config["SMTP_PASS"] = "zhswmywmylvkrcnw"
app.config["SMTP_FROM"] = "amos.carvalho@gmail.com"




db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = "login"


# -------------------------------------------------------------------
# HELPERS
# -------------------------------------------------------------------
class HoraStrWrapper:
    """Wrapper simples para permitir .strftime('%H:%M') em strings HH:MM."""

    def __init__(self, text):
        self.text = text or ""

    def strftime(self, fmt):
        return self.text


def salvar_foto(file_storage, foto_atual=None):
    """
    Salva o arquivo enviado e devolve o caminho relativo "uploads/arquivo.jpg".
    Se nÃ£o houver arquivo novo, retorna foto_atual (mantÃ©m a existente).
    """
    if not file_storage:
        return foto_atual

    filename = secure_filename(file_storage.filename or "")
    if filename == "":
        return foto_atual

    caminho = os.path.join(app.config["UPLOAD_FOLDER"], filename)
    file_storage.save(caminho)
    return f"uploads/{filename}"


def enviar_codigo_email(email, codigo) -> bool:
    """
    Envia código de recuperação via Resend (API HTTP).
    Retorna True se enviou, False se falhou.
    """
    api_key = os.getenv("RESEND_API_KEY", "").strip()
    remetente = os.getenv("RESEND_FROM", "Sistema Escolar <onboarding@resend.dev>").strip()

    if not api_key:
        return False

    assunto = "Recuperação de senha - Sistema Escolar"
    texto = f"Seu código para redefinição de senha é: {codigo}"

    try:
        r = requests.post(
            "https://api.resend.com/emails",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "from": remetente,
                "to": [email],
                "subject": assunto,
                "text": texto,
            },
            timeout=20,
        )

        # 200/201 normalmente indicam sucesso
        if r.status_code in (200, 201):
            return True

        print("Erro Resend:", r.status_code, r.text)
        return False

    except Exception as e:
        print("Erro ao enviar e-mail (Resend):", e)
        return False



def enviar_email_generico(destinatarios, assunto, mensagem) -> bool:
    """
    Envia e-mail genérico via Resend (API HTTP).
    destinatarios pode ser string com ; ou , ou lista.
    """
    api_key = os.getenv("RESEND_API_KEY", "").strip()
    remetente = os.getenv("RESEND_FROM", "Sistema Escolar <onboarding@resend.dev>").strip()

    if not api_key:
        return False

    # normaliza destinatários
    if isinstance(destinatarios, str):
        d = destinatarios.replace(";", ",")
        lista = [x.strip() for x in d.split(",") if x.strip()]
    else:
        lista = [x.strip() for x in destinatarios if str(x).strip()]

    if not lista:
        return False

    try:
        r = requests.post(
            "https://api.resend.com/emails",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "from": remetente,
                "to": lista,
                "subject": assunto,
                "text": mensagem,
            },
            timeout=20,
        )

        if r.status_code in (200, 201):
            return True

        print("Erro Resend:", r.status_code, r.text)
        return False

    except Exception as e:
        print("Erro ao enviar e-mail (Resend):", e)
        return False

import resend

resend.api_key = "re_9h1NooAW_87hE1xs5sJLQMYQj3SgfevSy"

r = resend.Emails.send({
  "from": "onboarding@resend.dev",
  "to": "gabrielbarbosac2013@gmail.com",
  "subject": "Hello World",
  "html": "<p>Congrats on sending your <strong>first email</strong>!</p>"
})

def enviar_codigo_whatsapp(numero, codigo) -> bool:
    """
    Usa o script externo enviar_whatsapp.py para automatizar o WhatsApp Web
    e enviar a mensagem em background (headless, depois do primeiro login).

    - numero: string com o nÃºmero (pode ter +, espaÃ§os, etc. -> serÃ¡ limpo).
    - codigo: cÃ³digo numÃ©rico a ser enviado.

    Retorna True se o script terminar com exit code 0, False caso contrÃ¡rio.
    """
    numero_limpo = "".join(filter(str.isdigit, numero))
    mensagem = f"Seu cÃ³digo de recuperaÃ§Ã£o Ã©: {codigo}"

    # Monta comando: python enviar_whatsapp.py NUMERO "mensagem"
    cmd = f'{sys.executable} enviar_whatsapp.py {numero_limpo} "{mensagem}"'

    try:
        resultado = subprocess.run(
            shlex.split(cmd),
            capture_output=True,
            # text=True,
            timeout=180,
        )
        print("STDOUT enviar_whatsapp:", resultado.stdout)
        print("STDERR enviar_whatsapp:", resultado.stderr)
        return resultado.returncode == 0
    except Exception as e:
        print("Erro ao chamar enviar_whatsapp.py:", e)
        return False


def _is_hhmm(val: str) -> bool:
    if not val or len(val) != 5 or val[2] != ":":
        return False
    hh, mm = val.split(":")
    return hh.isdigit() and mm.isdigit() and 0 <= int(hh) <= 23 and 0 <= int(mm) <= 59


# -------------------------------------------------------------------
# MODELOS
# -------------------------------------------------------------------
class Usuario(db.Model, UserMixin):
    __tablename__ = "usuario"
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    senha_hash = db.Column(db.String(255), nullable=False)
    papel = db.Column(db.String(30), nullable=False, default="ALUNO")
    ativo = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

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
# -----------------------------
# PROFESSOR (cadastro separado)
# -----------------------------
professor_serie = db.Table(
    "professor_serie",
    db.Column("professor_id", db.Integer, db.ForeignKey("professor.id"), primary_key=True),
    db.Column("serie_id", db.Integer, db.ForeignKey("serie.id"), primary_key=True),
)

class Professor(db.Model):
    __tablename__ = "professor"
    id = db.Column(db.Integer, primary_key=True)

    # Email precisa existir em Usuario (vÃ­nculo)
    usuario_id = db.Column(db.Integer, db.ForeignKey("usuario.id"), nullable=False, unique=True)
    usuario = db.relationship("Usuario", lazy="joined")

    nome = db.Column(db.String(120), nullable=False)
    data_nascimento = db.Column(db.Date, nullable=True)

    series = db.relationship("Serie", secondary=professor_serie, lazy="subquery")

    def series_str(self):
        return ", ".join([s.nome for s in self.series]) if self.series else ""


class Horario(db.Model):
    __tablename__ = "horario"
    id = db.Column(db.Integer, primary_key=True)
    hora_inicio = db.Column(db.String(5), nullable=False)  # HH:MM
    hora_fim = db.Column(db.String(5), nullable=False)      # HH:MM


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

    naturalidade = db.Column(db.String(120))
    nacionalidade = db.Column(db.String(120))
    data_nascimento = db.Column(db.Date)
    idade = db.Column(db.Integer)
    sexo = db.Column(db.String(1))
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
    mensalidade_opcao = db.Column(db.String(60))

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


# -------------------------------------------------------------------
# LOGIN / AUTENTICAÃ‡ÃƒO
# -------------------------------------------------------------------
@login_manager.user_loader
def load_user(uid):
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
        flash("Credenciais invÃ¡lidas ou usuÃ¡rio inativo.", "danger")
    return render_template("auth/login.html")


# -------------------------------------------------------------------
# RECUPERAÇÃO DE SENHA
# -------------------------------------------------------------------
# /esqueci: pede e-mail + escolha E-MAIL ou WHATSAPP
@app.route("/esqueci", methods=["GET", "POST"])
def esqueci():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        metodo = request.form.get("metodo", "email")  # 'email' ou 'whatsapp'

        # valida e-mail
        if not email:
            flash("Informe um e-mail.", "warning")
            return redirect(url_for("esqueci"))

        user = Usuario.query.filter_by(email=email).first()
        if not user:
            flash("E-mail não encontrado no sistema.", "danger")
            return redirect(url_for("esqueci"))

        # guarda o e-mail para as próximas etapas
        session["recuperacao_email"] = email

        if metodo == "email":
            # gera código e tenta enviar por E-MAIL
            codigo = random.randint(100000, 999999)
            session["recuperacao_codigo"] = str(codigo)
            session["recuperacao_modo"] = "email"

            enviado = enviar_codigo_email(email, str(codigo))

            if enviado:
                flash("Enviamos um código para o seu e-mail.", "success")
            else:
                # Fallback: mostra o código na tela (não no terminal)
                flash(
                    f"(Modo teste) Não foi possível enviar o e-mail. "
                    f"Use este código para continuar: {codigo}",
                    "warning",
                )

            return redirect(url_for("verificar_codigo"))

        elif metodo == "whatsapp":
            # Vai para a tela que pede APENAS o número do WhatsApp
            session["recuperacao_modo"] = "whatsapp"
            return redirect(url_for("esqueci_whatsapp"))

        else:
            flash("Método inválido.", "danger")
            return redirect(url_for("esqueci"))

    return render_template("auth/esqueci.html")



# /esqueci/whatsapp: tela com APENAS o campo de nÃºmero WhatsApp
@app.route("/esqueci/whatsapp", methods=["GET", "POST"])
def esqueci_whatsapp():
    email = session.get("recuperacao_email")
    if not email:
        flash("SessÃ£o expirada. Recomece o processo de recuperaÃ§Ã£o.", "warning")
        return redirect(url_for("esqueci"))

    if request.method == "POST":
        numero = request.form.get("whatsapp", "").strip()
        if not numero:
            flash("Informe o nÃºmero de WhatsApp.", "danger")
            return redirect(url_for("esqueci_whatsapp"))

        # Gera cÃ³digo e tenta enviar pelo WhatsApp
        codigo = random.randint(100000, 999999)
        session["recuperacao_codigo"] = str(codigo)
        session["recuperacao_modo"] = "whatsapp"

        enviado = enviar_codigo_whatsapp(numero, codigo)

        if enviado:
            flash("Um cÃ³digo foi enviado para o WhatsApp informado.", "info")
        else:
            # Fallback: mostra o cÃ³digo na tela (nÃ£o no terminal)
            flash(
                f"(Modo teste) NÃ£o foi possÃ­vel enviar pelo WhatsApp. "
                f"Use este cÃ³digo para continuar: {codigo}",
                "warning",
            )

        return redirect(url_for("verificar_codigo"))

    return render_template("auth/esqueci_whatsapp.html")


@app.route("/verificar-codigo", methods=["GET", "POST"])
def verificar_codigo():
    if request.method == "POST":
        codigo_digitado = request.form.get("codigo", "").strip()
        codigo_correto = session.get("recuperacao_codigo")

        if codigo_digitado == codigo_correto and codigo_correto:
            return redirect(url_for("redefinir_senha"))

        flash("CÃ³digo incorreto.", "danger")
        return redirect(url_for("verificar_codigo"))

    return render_template("auth/verificar_codigo.html")


@app.route("/redefinir-senha", methods=["GET", "POST"])
def redefinir_senha():
    email = session.get("recuperacao_email")
    if not email:
        flash("Processo de recuperaÃ§Ã£o expirado. Tente novamente.", "warning")
        return redirect(url_for("esqueci"))

    if request.method == "POST":
        senha1 = request.form.get("senha1")
        senha2 = request.form.get("senha2")

        if senha1 != senha2:
            flash("As senhas nÃ£o coincidem.", "danger")
            return redirect(url_for("redefinir_senha"))

        if len(senha1) < 8 or not any(c.isdigit() for c in senha1):
            flash("Senha deve ter no mÃ­nimo 8 caracteres e conter nÃºmeros.", "danger")
            return redirect(url_for("redefinir_senha"))

        user = Usuario.query.filter_by(email=email).first()
        if not user:
            flash("UsuÃ¡rio nÃ£o encontrado.", "danger")
            return redirect(url_for("login"))

        user.senha_hash = senha1
        db.session.commit()

        session.pop("recuperacao_email", None)
        session.pop("recuperacao_codigo", None)
        session.pop("recuperacao_modo", None)

        flash("Senha redefinida com sucesso! FaÃ§a login.", "success")
        return redirect(url_for("login"))

    return render_template("auth/redefinir_senha.html")


@app.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))


# -------------------------------------------------------------------
# MIGRAÃ‡ÃƒO LEVE / SCHEMA
# -------------------------------------------------------------------
def _add_col_if_missing(table: str, column: str, ddl: str):
    info = db.session.execute(sa_text(f"PRAGMA table_info({table})")).mappings().all()
    cols = {c["name"] for c in info}
    if column not in cols:
        db.session.execute(sa_text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}"))
        db.session.commit()


def ensure_schema():
    try:
        _add_col_if_missing("atividade", "data", "DATE")
        _add_col_if_missing("atividade", "professor", "TEXT")
        _add_col_if_missing("atividade", "conteudo", "TEXT")
        _add_col_if_missing("atividade", "observacao", "TEXT")
    except Exception:
        db.session.rollback()

    try:
        _add_col_if_missing("horario", "hora_inicio", "TEXT")
        _add_col_if_missing("horario", "hora_fim", "TEXT")
    except Exception:
        db.session.rollback()

    try:
        _add_col_if_missing("escola", "nome", "TEXT")
    except Exception:
        db.session.rollback()

    try:
        _add_col_if_missing("usuario", "aluno_id", "INTEGER")
    except Exception:
        db.session.rollback()


# -------------------------------------------------------------------
# PERMISSÃ•ES
# -------------------------------------------------------------------
def can(permission: str) -> bool:
    if not current_user.is_authenticated:
        return False

    role = current_user.papel_upper()

    if role == "DIRETORIA":
        return True

    if permission == "ver_usuarios":
        return False

    if permission == "gerenciar_usuarios":
        return False

    if permission == "gerenciar_estrutura":
        return role == "DIRETORIA"

    if permission == "alunos_crud":
        return role == "DIRETORIA"

    if permission == "atividades_criar":
        return role in ("DIRETORIA", "PROFESSOR")

    if permission == "atividades_editar":
        return role == "DIRETORIA"

    if permission == "ver_tudo":
        return role in ("DIRETORIA", "PROFESSOR")

    if permission == "ver_restrito_aluno":
        return role in ("RESPONSAVEL", "ALUNO")

    return False


@app.context_processor
def inject_can():
    return dict(can=can)


# -------------------------------------------------------------------
# INDEX
# -------------------------------------------------------------------
@app.route("/")
@login_required
def index():
    return render_template("index.html")


# -------------------------------------------------------------------
# USUÃRIOS
# -------------------------------------------------------------------
@app.route("/usuarios/", methods=["GET"])
@login_required
def usuarios_list():
    if not current_user.is_diretoria():
        flash("Acesso restrito Ã  DIRETORIA.", "warning")
        return redirect(url_for("index"))

    items = Usuario.query.order_by(Usuario.email.asc()).all()
    alunos = Aluno.query.order_by(Aluno.nome.asc()).all()
    return render_template("usuarios/listar.html", items=items, alunos=alunos)


@app.route("/usuarios/novo", methods=["POST"])
@login_required
def usuarios_novo():
    if not current_user.is_diretoria():
        flash("Acesso restrito Ã  DIRETORIA.", "warning")
        return redirect(url_for("index"))

    email = request.form.get("email", "").strip().lower()
    senha = request.form.get("senha", "")
    senha2 = request.form.get("senha2", "")
    papel = (request.form.get("papel", "ALUNO") or "ALUNO").upper()
    aluno_id = request.form.get("aluno_id")

    if not email or "@" not in email:
        flash("E-mail invÃ¡lido.", "danger")
        return redirect(url_for("usuarios_list"))
    if len(senha) < 8 or not any(c.isdigit() for c in senha):
        flash("Senha deve ter 8+ caracteres e ao menos 1 dÃ­gito.", "danger")
        return redirect(url_for("usuarios_list"))
    if senha != senha2:
        flash("ConfirmaÃ§Ã£o de senha nÃ£o confere.", "danger")
        return redirect(url_for("usuarios_list"))
    if Usuario.query.filter_by(email=email).first():
        flash("E-mail jÃ¡ cadastrado.", "danger")
        return redirect(url_for("usuarios_list"))

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
    flash("UsuÃ¡rio criado.", "success")
    return redirect(url_for("usuarios_list"))


@app.route("/usuarios/<int:id>/editar", methods=["POST"])
@login_required
def usuarios_editar(id):
    if not current_user.is_diretoria():
        flash("Acesso restrito Ã  DIRETORIA.", "warning")
        return redirect(url_for("index"))

    u = Usuario.query.get_or_404(id)
    papel = (request.form.get("papel", u.papel) or u.papel).upper()
    ativo = True if request.form.get("ativo") == "on" else False
    new_pass = request.form.get("nova_senha", "").strip()
    aluno_id = request.form.get("aluno_id")

    if new_pass:
        if len(new_pass) < 8 or not any(c.isdigit() for c in new_pass):
            flash("Nova senha invÃ¡lida (8+ e 1 dÃ­gito).", "danger")
            return redirect(url_for("usuarios_list"))
        u.senha_hash = new_pass

    if papel in ("RESPONSAVEL", "ALUNO") and not aluno_id:
        flash("Selecione o aluno vinculado para esse perfil.", "danger")
        return redirect(url_for("usuarios_list"))

    u.papel = papel
    u.ativo = ativo
    u.aluno_id = int(aluno_id) if aluno_id else None

    db.session.commit()
    flash("UsuÃ¡rio atualizado.", "success")
    return redirect(url_for("usuarios_list"))


@app.route("/usuarios/<int:id>/excluir", methods=["POST"])
@login_required
def usuarios_excluir(id):
    if not current_user.is_diretoria():
        flash("Acesso restrito Ã  DIRETORIA.", "warning")
        return redirect(url_for("index"))
    if current_user.id == id:
        flash("VocÃª nÃ£o pode excluir a si mesmo.", "warning")
        return redirect(url_for("usuarios_list"))
    u = Usuario.query.get_or_404(id)
    db.session.delete(u)
    db.session.commit()
    flash("UsuÃ¡rio removido.", "success")
    return redirect(url_for("usuarios_list"))

# -------------------------------------------------------------------
# PROFESSORES (somente Diretoria)
# -------------------------------------------------------------------
@app.route("/professores/")
@login_required
def professores_listar():
    if not current_user.is_diretoria():
        flash("VocÃª nÃ£o tem permissÃ£o para acessar Professores.", "warning")
        return redirect(url_for("index"))

    itens = Professor.query.order_by(Professor.nome.asc()).all()
    return render_template("professores/listar.html", itens=itens)


@app.route("/professores/novo", methods=["GET", "POST"])
@login_required
def professores_novo():
    if not current_user.is_diretoria():
        flash("VocÃª nÃ£o tem permissÃ£o para cadastrar Professores.", "warning")
        return redirect(url_for("index"))

    usuarios = Usuario.query.order_by(Usuario.email.asc()).all()
    series = Serie.query.order_by(Serie.nome.asc()).all()

    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        nome = (request.form.get("nome") or "").strip()
        dn_str = (request.form.get("data_nascimento") or "").strip()
        series_ids = request.form.getlist("series_ids")

        if not email or not nome:
            flash("Preencha E-mail e Nome.", "danger")
            return redirect(request.url)

        u = Usuario.query.filter(sa_text("lower(email)=:e")).params(e=email).first()
        if not u:
            flash("E-mail nÃ£o registrado.", "danger")
            return redirect(request.url)

            return redirect(request.url)

        # data nascimento (opcional)
        dn = None
        if dn_str:
            try:
                dn = datetime.strptime(dn_str, "%Y-%m-%d").date()
            except ValueError:
                flash("Data de nascimento invÃ¡lida. Use o seletor de data.", "danger")
                return redirect(request.url)

        # busca sÃ©ries selecionadas
        sel_series = []
        if series_ids:
            try:
                ids_int = [int(x) for x in series_ids]
                sel_series = Serie.query.filter(Serie.id.in_(ids_int)).all()
            except ValueError:
                flash("SeleÃ§Ã£o de sÃ©ries invÃ¡lida.", "danger")
                return redirect(request.url)

        # se jÃ¡ existir cadastro de professor para este usuÃ¡rio, atualiza (evita duplicar)
        prof = Professor.query.filter_by(usuario_id=u.id).first()
        if not prof:
            prof = Professor(usuario_id=u.id, nome=nome, data_nascimento=dn)
            db.session.add(prof)
        else:
            prof.nome = nome
            prof.data_nascimento = dn

        prof.series = sel_series

        # transforma o usuÃ¡rio em PROFESSOR (perfil)
        u.papel = "PROFESSOR"

        db.session.commit()
        flash("Professor cadastrado com sucesso.", "success")
        return redirect(url_for("professores_listar"))

    return render_template("professores/form.html", usuarios=usuarios, series=series, item=None)


@app.route("/professores/<int:id>/editar", methods=["GET", "POST"])
@login_required
def professores_editar(id):
    if not current_user.is_diretoria():
        flash("VocÃª nÃ£o tem permissÃ£o para editar Professores.", "warning")
        return redirect(url_for("index"))

    prof = Professor.query.get_or_404(id)

    usuarios = Usuario.query.order_by(Usuario.email.asc()).all()
    series = Serie.query.order_by(Serie.nome.asc()).all()

    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        nome = (request.form.get("nome") or "").strip()
        dn_str = (request.form.get("data_nascimento") or "").strip()
        series_ids = request.form.getlist("series_ids")

        if not email or not nome:
            flash("Preencha E-mail e Nome.", "danger")
            return redirect(request.url)

        u = Usuario.query.filter(sa_text("lower(email)=:e")).params(e=email).first()
        if not u:
            flash("Este e-mail nÃ£o estÃ¡ cadastrado no sistema.", "danger")
            return redirect(request.url)

        # garante unicidade: um usuÃ¡rio sÃ³ pode ser um professor
        outro = Professor.query.filter_by(usuario_id=u.id).first()
        if outro and outro.id != prof.id:
            flash("Este e-mail jÃ¡ estÃ¡ vinculado a outro professor.", "danger")
            return redirect(request.url)

        dn = None
        if dn_str:
            try:
                dn = datetime.strptime(dn_str, "%Y-%m-%d").date()
            except ValueError:
                flash("Data de nascimento invÃ¡lida. Use o seletor de data.", "danger")
                return redirect(request.url)

        sel_series = []
        if series_ids:
            try:
                ids_int = [int(x) for x in series_ids]
                sel_series = Serie.query.filter(Serie.id.in_(ids_int)).all()
            except ValueError:
                flash("SeleÃ§Ã£o de sÃ©ries invÃ¡lida.", "danger")
                return redirect(request.url)

        prof.usuario_id = u.id
        prof.nome = nome
        prof.data_nascimento = dn
        prof.series = sel_series

        u.papel = "PROFESSOR"

        db.session.commit()
        flash("Professor atualizado com sucesso.", "success")
        return redirect(url_for("professores_listar"))

    return render_template("professores/form.html", usuarios=usuarios, series=series, item=prof)

# -------------------------------------------------------------------
# ESCOLAS
# -------------------------------------------------------------------
@app.route("/escolas/")
@login_required
def escolas_list():
    if current_user.is_responsavel() or current_user.is_aluno():
        flash("Acesso nÃ£o autorizado.", "warning")
        return redirect(url_for("index"))

    items = Escola.query.order_by(Escola.nome.asc()).all()
    return render_template("escolas/listar.html", items=items)


@app.route("/escolas/novo", methods=["GET", "POST"])
@login_required
def escolas_nova():
    if not current_user.is_diretoria():
        flash("Acesso nÃ£o autorizado.", "warning")
        return redirect(url_for("index"))

    if request.method == "POST":
        nome = request.form.get("nome", "").strip()
        if not nome:
            flash("Informe o nome da escola.", "danger")
            return redirect(url_for("escolas_nova"))
        if Escola.query.filter_by(nome=nome).first():
            flash("JÃ¡ existe escola com esse nome.", "warning")
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
        flash("Acesso nÃ£o autorizado.", "warning")
        return redirect(url_for("index"))

    e = Escola.query.get_or_404(id)
    nome = request.form.get("nome", "").strip()
    if not nome:
        flash("Informe o nome.", "danger")
        return redirect(url_for("escolas_list"))
    if Escola.query.filter(Escola.id != id, Escola.nome == nome).first():
        flash("JÃ¡ existe escola com esse nome.", "warning")
        return redirect(url_for("escolas_list"))
    e.nome = nome
    db.session.commit()
    flash("Escola atualizada.", "success")
    return redirect(url_for("escolas_list"))


@app.route("/escolas/<int:id>/excluir", methods=["POST"])
@login_required
def escolas_excluir(id):
    if not current_user.is_diretoria():
        flash("Acesso nÃ£o autorizado.", "warning")
        return redirect(url_for("index"))

    e = Escola.query.get_or_404(id)
    db.session.delete(e)
    db.session.commit()
    flash("Escola excluÃ­da.", "success")
    return redirect(url_for("escolas_list"))


# -------------------------------------------------------------------
# SÃ‰RIES
# -------------------------------------------------------------------
@app.route("/series/")
@login_required
def series_list():
    if current_user.is_responsavel() or current_user.is_aluno():
        flash("Acesso nÃ£o autorizado.", "warning")
        return redirect(url_for("index"))

    series = Serie.query.order_by(Serie.nome.asc()).all()
    return render_template("series/listar.html", series=series)


@app.route("/series/novo", methods=["GET", "POST"])
@login_required
def series_nova():
    if not current_user.is_diretoria():
        flash("Acesso nÃ£o autorizado.", "warning")
        return redirect(url_for("index"))

    if request.method == "POST":
        nome = request.form.get("nome", "").strip()
        if not nome:
            flash("Informe o nome da sÃ©rie.", "danger")
            return redirect(url_for("series_nova"))
        if Serie.query.filter_by(nome=nome).first():
            flash("JÃ¡ existe sÃ©rie com esse nome.", "warning")
            return redirect(url_for("series_list"))
        s = Serie(nome=nome)
        db.session.add(s)
        db.session.commit()
        flash("SÃ©rie cadastrada.", "success")
        return redirect(url_for("series_list"))
    return render_template("series/form.html")


@app.route("/series/<int:id>/editar", methods=["POST"])
@login_required
def series_editar(id):
    if not current_user.is_diretoria():
        flash("Acesso nÃ£o autorizado.", "warning")
        return redirect(url_for("index"))

    s = Serie.query.get_or_404(id)
    nome = request.form.get("nome", "").strip()
    if not nome:
        flash("Informe o nome.", "danger")
        return redirect(url_for("series_list"))
    if Serie.query.filter(Serie.id != id, Serie.nome == nome).first():
        flash("JÃ¡ existe sÃ©rie com esse nome.", "warning")
        return redirect(url_for("series_list"))
    s.nome = nome
    db.session.commit()
    flash("SÃ©rie atualizada.", "success")
    return redirect(url_for("series_list"))


@app.route("/series/<int:id>/excluir", methods=["POST"])
@login_required
def series_excluir(id):
    if not current_user.is_diretoria():
        flash("Acesso nÃ£o autorizado.", "warning")
        return redirect(url_for("index"))

    s = Serie.query.get_or_404(id)
    db.session.delete(s)
    db.session.commit()
    flash("SÃ©rie excluÃ­da.", "success")
    return redirect(url_for("series_list"))


# -------------------------------------------------------------------
# HORÃRIOS
# -------------------------------------------------------------------
@app.route("/horarios/")
@login_required
def horarios_list():
    if current_user.is_responsavel() or current_user.is_aluno():
        flash("Acesso nÃ£o autorizado.", "warning")
        return redirect(url_for("index"))

    items = Horario.query.order_by(Horario.hora_inicio.asc()).all()

    # âœ… Alunos agrupados por horÃ¡rio
    alunos = Aluno.query.order_by(Aluno.nome.asc()).all()

    alunos_por_horario = {}
    alunos_sem_horario = []

    for a in alunos:
        if a.horario_id:
            alunos_por_horario.setdefault(a.horario_id, []).append(a)
        else:
            alunos_sem_horario.append(a)

    return render_template(
        "horarios/listar.html",
        items=items,
        alunos_por_horario=alunos_por_horario,
        alunos_sem_horario=alunos_sem_horario,
    )



@app.route("/horarios/novo", methods=["GET", "POST"])
@login_required
def horarios_novo():
    if not current_user.is_diretoria():
        flash("Acesso nÃ£o autorizado.", "warning")
        return redirect(url_for("index"))

    if request.method == "POST":
        h_ini = request.form.get("hora_inicio", "").strip()
        h_fim = request.form.get("hora_fim", "").strip()
        if not _is_hhmm(h_ini) or not _is_hhmm(h_fim):
            flash("Informe horas vÃ¡lidas no formato HH:MM.", "danger")
            return redirect(url_for("horarios_novo"))
        if h_fim <= h_ini:
            flash("Hora fim deve ser maior que hora inÃ­cio.", "danger")
            return redirect(url_for("horarios_novo"))
        h = Horario(hora_inicio=h_ini, hora_fim=h_fim)
        db.session.add(h)
        db.session.commit()
        flash("HorÃ¡rio cadastrado.", "success")
        return redirect(url_for("horarios_list"))
    return render_template("horarios/form.html")


app.add_url_rule("/horarios/novo", endpoint="horarios_new", view_func=horarios_novo)


@app.route("/horarios/<int:id>/editar", methods=["POST"])
@login_required
def horarios_editar(id):
    if not current_user.is_diretoria():
        flash("Acesso nÃ£o autorizado.", "warning")
        return redirect(url_for("index"))

    h = Horario.query.get_or_404(id)
    h_ini = request.form.get("hora_inicio", "").strip()
    h_fim = request.form.get("hora_fim", "").strip()
    if not _is_hhmm(h_ini) or not _is_hhmm(h_fim) or h_fim <= h_ini:
        flash("Horas invÃ¡lidas.", "danger")
        return redirect(url_for("horarios_list"))
    h.hora_inicio = h_ini
    h.hora_fim = h_fim
    db.session.commit()
    flash("HorÃ¡rio atualizado.", "success")
    return redirect(url_for("horarios_list"))


@app.route("/horarios/<int:id>/excluir", methods=["POST"])
@login_required
def horarios_excluir(id):
    if not current_user.is_diretoria():
        flash("Acesso nÃ£o autorizado.", "warning")
        return redirect(url_for("index"))

    h = Horario.query.get_or_404(id)
    db.session.delete(h)
    db.session.commit()
    flash("HorÃ¡rio excluÃ­do.", "success")
    return redirect(url_for("horarios_list"))


# -------------------------------------------------------------------
# ALUNOS
# -------------------------------------------------------------------
@app.route("/alunos/")
@login_required
def alunos_list():
    items = Aluno.query.order_by(Aluno.nome.asc()).all()
    return render_template("alunos/listar.html", items=items)


@app.route("/alunos/novo", methods=["GET", "POST"])
@login_required
def alunos_novo():
    if not current_user.is_diretoria():
        flash("Acesso nÃ£o autorizado.", "warning")
        return redirect(url_for("alunos_list"))

    if request.method == "POST":
        nome = request.form.get("nome", "").strip()
        escola_id = request.form.get("escola_id")
        serie_id = request.form.get("serie_id")
        horario_id = request.form.get("horario_id")

        telefone_cel = request.form.get("telefone_cel")
        telefone_fixo = request.form.get("telefone_fixo")
        observacoes = request.form.get("observacoes")

        file = request.files.get("foto")
        foto_path = salvar_foto(file)

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


app.add_url_rule("/alunos/novo", endpoint="alunos_new", view_func=alunos_novo)


@app.route("/alunos/<int:id>/editar", methods=["GET", "POST"])
@login_required
def alunos_editar(id):
    if not current_user.is_diretoria():
        flash("Acesso nÃ£o autorizado.", "warning")
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

        file = request.files.get("foto")
        a.foto_path = salvar_foto(file, foto_atual=a.foto_path)

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
        flash("Acesso nÃ£o autorizado.", "warning")
        return redirect(url_for("alunos_list"))

    a = Aluno.query.get_or_404(id)
    db.session.delete(a)
    db.session.commit()
    flash("Aluno excluÃ­do.", "success")
    return redirect(url_for("alunos_list"))


@app.route("/alunos/<int:id>")
@login_required
def alunos_ver(id):
    a = Aluno.query.get_or_404(id)

    if current_user.is_diretoria() or current_user.is_professor():
        pass
    else:
        if not current_user.aluno_id or current_user.aluno_id != a.id:
            flash("VocÃª nÃ£o tem permissÃ£o para ver os dados deste aluno.", "warning")
            return redirect(url_for("alunos_list"))

    return render_template("alunos/ver.html", aluno=a)


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


# -------------------------------------------------------------------
# ATIVIDADES
# -------------------------------------------------------------------
@app.route("/atividades/")
@login_required
def atividades_listar():
    if current_user.is_diretoria() or current_user.is_professor():
        itens = Atividade.query.order_by(
            Atividade.data.desc(), Atividade.id.desc()
        ).all()
    else:
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


app.add_url_rule(
    "/atividades/", endpoint="atividades_list", view_func=atividades_listar
)


@app.route("/atividades/novo", methods=["GET", "POST"])
@login_required
def atividades_nova():
    if not (current_user.is_diretoria() or current_user.is_professor()):
        flash("VocÃª nÃ£o tem permissÃ£o para adicionar atividades.", "warning")
        return redirect(url_for("atividades_listar"))

    if request.method == "POST":
        aluno_id = request.form.get("aluno_id")
        data_str = request.form.get("data")
        professor = request.form.get("professor")
        conteudo = request.form.get("conteudo")
        observacao = request.form.get("observacao")

        if not aluno_id or not data_str or not professor or not conteudo:
            flash("Preencha os campos obrigatÃ³rios.", "danger")
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
    if not current_user.is_diretoria():
        flash("VocÃª nÃ£o tem permissÃ£o para editar atividades.", "warning")
        return redirect(url_for("atividades_listar"))

    atv = Atividade.query.get_or_404(id)

    if request.method == "POST":
        atv.aluno_id = int(request.form.get("aluno_id"))

        data_str = request.form.get("data")
        atv.data = (
            datetime.strptime(data_str, "%D/%m/%Y").date() if False else
            (datetime.strptime(data_str, "%Y-%m-%d").date() if data_str else atv.data)
        )

        professor = (request.form.get("professor") or "").strip()
        conteudo = (request.form.get("conteudo") or "").strip()
        observacao = request.form.get("observacao")

        # âœ… Evita gravar NULL/vazio em campos NOT NULL
        if not professor or not conteudo:
            flash("Preencha os campos obrigatÃ³rios: Professor e ConteÃºdo.", "danger")
            return redirect(request.url)

        atv.professor = professor
        atv.conteudo = conteudo
        atv.observacao = observacao

        db.session.commit()
        flash("Atividade atualizada.", "success")
        return redirect(url_for("atividades_listar"))

    alunos = Aluno.query.order_by(Aluno.nome.asc()).all()
    return render_template("atividades/form.html", item=atv, alunos=alunos)



@app.route("/atividades/<int:id>/excluir", methods=["POST"])
@login_required
def atividades_excluir(id):
    if not current_user.is_diretoria():
        flash("VocÃª nÃ£o tem permissÃ£o para excluir atividades.", "warning")
        return redirect(url_for("atividades_listar"))

    atv = Atividade.query.get_or_404(id)
    db.session.delete(atv)
    db.session.commit()
    flash("Atividade excluÃ­da.", "success")
    return redirect(url_for("atividades_listar"))


# -------------------------------------------------------------------
# SEED ADMIN
# -------------------------------------------------------------------
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


# -------------------------------------------------------------------
# BOOT
# -------------------------------------------------------------------
if __name__ == "__main__":
    with app.app_context():
        db.create_all()
        ensure_schema()
        seed_admin()
    app.run(debug=True)


