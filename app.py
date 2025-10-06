import os
import uuid
import ssl
import smtplib
from email.message import EmailMessage
from datetime import datetime
from functools import wraps

from flask import (
    Flask, render_template, request, redirect, url_for,
    flash, abort, session as flask_session, send_from_directory
)
from flask_sqlalchemy import SQLAlchemy
from flask_login import (
    LoginManager, UserMixin, login_user, logout_user,
    login_required, current_user
)
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import UniqueConstraint
from werkzeug.exceptions import Forbidden, Unauthorized, NotFound
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

# =============================================================================
# APP & DB
# =============================================================================
app = Flask(__name__, template_folder="templates", static_folder="static")
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-keep-it-safe")

def _normalize_db_url(url: str) -> str:
    if not url:
        return "sqlite:///alunos.db"
    url = url.replace("postgres://", "postgresql://", 1)
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url

db_url_env = os.environ.get("DATABASE_URL", "sqlite:///alunos.db")
app.config["SQLALCHEMY_DATABASE_URI"] = _normalize_db_url(db_url_env)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_pre_ping": True,
    "pool_recycle": 280,
    "pool_size": 5,
    "max_overflow": 5,
}

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = "login"

UPLOAD_DIR = os.path.join(app.root_path, "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

# disponibiliza view_functions se precisar em algum template
@app.context_processor
def inject_view_functions():
    return {"view_functions": app.view_functions}

# =============================================================================
# MODELOS
# =============================================================================
class Usuario(db.Model, UserMixin):
    __tablename__ = "usuario"
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(180), unique=True, nullable=False)
    senha_hash = db.Column(db.String(255), nullable=False)
    papel = db.Column(db.String(20), nullable=False, default="RESPONSAVEL")  # DIRETORIA|PROFESSOR|RESPONSAVEL|ALUNO
    ativo = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, senha: str):
        self.senha_hash = generate_password_hash(senha)

    def check_password(self, senha: str) -> bool:
        return check_password_hash(self.senha_hash, senha)

    def get_id(self):
        return str(self.id)

class Permissao(db.Model):
    __tablename__ = "permissao"
    id = db.Column(db.Integer, primary_key=True)
    codigo = db.Column(db.String(50), unique=True, nullable=False)
    nome_exibicao = db.Column(db.String(120), nullable=False)

class UsuarioPermissao(db.Model):
    __tablename__ = "usuario_permissao"
    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey("usuario.id", ondelete="CASCADE"), nullable=False)
    permissao_id = db.Column(db.Integer, db.ForeignKey("permissao.id", ondelete="CASCADE"), nullable=False)
    __table_args__ = (UniqueConstraint("usuario_id", "permissao_id", name="_usuario_permissao_uc"),)

    usuario = db.relationship("Usuario", backref=db.backref("permissoes_rel", cascade="all, delete-orphan"))
    permissao = db.relationship("Permissao")

class UserSession(db.Model):
    __tablename__ = "user_session"
    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey("usuario.id", ondelete="CASCADE"), nullable=False)
    session_id = db.Column(db.String(80), unique=True, nullable=False)
    login_em = db.Column(db.DateTime, default=datetime.utcnow)
    ultimo_seen = db.Column(db.DateTime, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True, nullable=False)

    usuario = db.relationship("Usuario")

    def marcar_seen(self):
        self.ultimo_seen = datetime.utcnow()

class Aluno(db.Model):
    __tablename__ = "aluno"
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(200), nullable=False)
    escola = db.Column(db.String(200))
    horario = db.Column(db.String(50))
    telefone_mae = db.Column(db.String(30))
    foto_path = db.Column(db.String(255))
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)
    atualizado_em = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

# =============================================================================
# LOGIN
# =============================================================================
@login_manager.user_loader
def load_user(user_id):
    return Usuario.query.get(int(user_id))

# =============================================================================
# PERMISSÕES
# =============================================================================
PERMISSOES_CODIGOS = [
    "ALUNO_EDITAR", "ALUNO_CRIAR", "ALUNO_EXCLUIR",
    "ATIVIDADE_ADICIONAR", "ATIVIDADE_EXCLUIR",
    "HORARIO_ADICIONAR", "HORARIO_EXCLUIR",
    "ESCOLA_ADICIONAR", "ESCOLA_EXCLUIR",
    "SERIE_ADICIONAR", "SERIE_EXCLUIR",
    "USUARIO_CRIAR"
]
PERMISSOES_NOMES = {
    "ALUNO_EDITAR": "Alterar cadastro de aluno",
    "ALUNO_CRIAR": "Cadastrar novo aluno",
    "ALUNO_EXCLUIR": "Excluir aluno",
    "ATIVIDADE_ADICIONAR": "Adicionar atividade",
    "ATIVIDADE_EXCLUIR": "Excluir atividade",
    "HORARIO_ADICIONAR": "Adicionar novo horário",
    "HORARIO_EXCLUIR": "Excluir horário",
    "ESCOLA_ADICIONAR": "Adicionar nova escola",
    "ESCOLA_EXCLUIR": "Excluir escola",
    "SERIE_ADICIONAR": "Adicionar série escolar",
    "SERIE_EXCLUIR": "Excluir série escolar",
    "USUARIO_CRIAR": "Cadastrar novo usuário",
}

def usuario_tem_permissao(usuario: Usuario, codigo: str) -> bool:
    if not usuario or not usuario.ativo:
        return False
    if usuario.papel == "DIRETORIA":
        return True
    up = (UsuarioPermissao.query
          .join(Permissao, UsuarioPermissao.permissao_id == Permissao.id)
          .filter(UsuarioPermissao.usuario_id == usuario.id,
                  Permissao.codigo == codigo)
          .first())
    return up is not None

def perm_required(codigo: str):
    def deco(fn):
        @wraps(fn)
        @login_required
        def wrapper(*args, **kwargs):
            if not current_user.is_authenticated:
                abort(401)
            if not current_user.ativo or not usuario_tem_permissao(current_user, codigo):
                flash("Você não possui permissão para esta tarefa.", "danger")
                abort(403)
            return fn(*args, **kwargs)
        return wrapper
    return deco

# =============================================================================
# UTIL / SAÚDE / SESSÃO
# =============================================================================
@app.route("/healthz")
def healthz():
    return "ok", 200

@app.before_request
def _atualiza_ultimo_seen():
    if current_user.is_authenticated:
        sid = flask_session.get("session_id")
        if sid:
            us = UserSession.query.filter_by(session_id=sid).first()
            if us:
                us.marcar_seen()
                db.session.commit()

def registrar_login_sessao(usuario: Usuario):
    sid = flask_session.get("session_id")
    if not sid:
        sid = str(uuid.uuid4())
        flask_session["session_id"] = sid
    # garante unicidade
    if UserSession.query.filter_by(session_id=sid).first():
        sid = f"{sid}-{uuid.uuid4().hex[:6]}"
        flask_session["session_id"] = sid
    db.session.add(UserSession(usuario_id=usuario.id, session_id=sid, is_active=True))
    db.session.commit()

def registrar_logout_sessao():
    sid = flask_session.get("session_id")
    if sid and current_user.is_authenticated:
        us = UserSession.query.filter_by(session_id=sid, usuario_id=current_user.id, is_active=True).first()
        if us:
            us.is_active = False
            db.session.commit()
    flask_session.pop("session_id", None)

# =============================================================================
# SEEDS
# =============================================================================
def seed_permissoes():
    criadas = 0
    for cod in PERMISSOES_CODIGOS:
        if not Permissao.query.filter_by(codigo=cod).first():
            db.session.add(Permissao(codigo=cod, nome_exibicao=PERMISSOES_NOMES[cod]))
            criadas += 1
    if criadas:
        db.session.commit()

def seed_admin():
    if Usuario.query.count() == 0:
        admin = Usuario(email="admin@escola.com", papel="DIRETORIA", ativo=True)
        admin.set_password(os.environ.get("ADMIN_PASS", "Trocar123"))
        db.session.add(admin)
        db.session.commit()
        print("Usuário DIRETORIA: admin@escola.com / ADMIN_PASS")

# =============================================================================
# AUTH MÍNIMO (login/logout)
# =============================================================================
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email","").strip().lower()
        senha = request.form.get("senha","")
        user = Usuario.query.filter_by(email=email).first()
        if user and user.check_password(senha) and user.ativo:
            login_user(user)
            registrar_login_sessao(user)
            flash("Bem-vindo!", "success")
            return redirect(url_for("index"))
        flash("Credenciais inválidas ou usuário inativo.", "danger")
    return render_template("login.html")

@app.route("/logout", methods=["POST"])
@login_required
def logout():
    registrar_logout_sessao()
    logout_user()
    flash("Sessão encerrada.", "info")
    return redirect(url_for("login"))

# =============================================================================
# HOME
# =============================================================================
@app.route("/", endpoint="index")
@login_required
def index():
    return render_template("index.html")

# =============================================================================
# ALUNOS
# =============================================================================
@app.route("/uploads/<path:filename>", endpoint="uploads")
@login_required
def uploads(filename):
    return send_from_directory(UPLOAD_DIR, filename, as_attachment=False)

@app.route("/alunos", endpoint="alunos_listar")
@login_required
def alunos_listar():
    alunos = Aluno.query.order_by(Aluno.nome.asc()).all()
    return render_template("alunos/listar.html", alunos=alunos)

@app.route("/alunos/novo", methods=["GET", "POST"], endpoint="alunos_novo")
@login_required
@perm_required("ALUNO_CRIAR")
def alunos_novo():
    if request.method == "POST":
        nome = request.form.get("nome","").strip()
        escola = request.form.get("escola","").strip()
        horario = request.form.get("horario","").strip()
        telefone_mae = request.form.get("telefone_mae","").strip()
        foto_file = request.files.get("foto")
        foto_path = None
        if foto_file and foto_file.filename:
            fname = f"{uuid.uuid4().hex}_{foto_file.filename}"
            foto_file.save(os.path.join(UPLOAD_DIR, fname))
            foto_path = fname
        if not nome:
            flash("Informe o nome do aluno.", "warning")
            return render_template("alunos/novo.html")
        db.session.add(Aluno(
            nome=nome, escola=escola, horario=horario,
            telefone_mae=telefone_mae, foto_path=foto_path
        ))
        db.session.commit()
        flash("Aluno cadastrado!", "success")
        return redirect(url_for("alunos_listar"))
    return render_template("alunos/novo.html")

@app.route("/alunos/<int:id>/editar", methods=["GET", "POST"], endpoint="alunos_editar")
@login_required
@perm_required("ALUNO_EDITAR")
def alunos_editar(id):
    aluno = Aluno.query.get_or_404(id)
    if request.method == "POST":
        aluno.nome = request.form.get("nome","").strip()
        aluno.escola = request.form.get("escola","").strip()
        aluno.horario = request.form.get("horario","").strip()
        aluno.telefone_mae = request.form.get("telefone_mae","").strip()
        foto_file = request.files.get("foto")
        if foto_file and foto_file.filename:
            fname = f"{uuid.uuid4().hex}_{foto_file.filename}"
            foto_file.save(os.path.join(UPLOAD_DIR, fname))
            aluno.foto_path = fname
        if not aluno.nome:
            flash("Informe o nome do aluno.", "warning")
            return render_template("alunos/editar.html", aluno=aluno)
        db.session.commit()
        flash("Alterações salvas!", "success")
        return redirect(url_for("alunos_listar"))
    return render_template("alunos/editar.html", aluno=aluno)

@app.route("/alunos/<int:id>/excluir", methods=["POST"], endpoint="alunos_excluir")
@login_required
@perm_required("ALUNO_EXCLUIR")
def alunos_excluir(id):
    aluno = Aluno.query.get_or_404(id)
    db.session.delete(aluno)
    db.session.commit()
    flash("Aluno excluído!", "success")
    return redirect(url_for("alunos_listar"))

# =============================================================================
# STUBS – para os botões existirem agora (podem ser substituídos depois)
# =============================================================================
@app.route("/escolas", endpoint="escolas_listar")
@login_required
def escolas_listar():
    itens = []  # substitua por sua query real depois
    return render_template("stubs/lista_com_botao.html",
                           titulo="Escolas",
                           endpoint_novo="escolas_novo",
                           label_botao="Nova Escola",
                           itens=itens)

@app.route("/escolas/novo", methods=["GET", "POST"], endpoint="escolas_novo")
@login_required
@perm_required("ESCOLA_ADICIONAR")
def escolas_novo():
    if request.method == "POST":
        flash("Stub: Escola criada (implemente depois).", "info")
        return redirect(url_for("escolas_listar"))
    return render_template("stubs/novo_stub.html", titulo="Nova Escola")

@app.route("/series", endpoint="series_listar")
@login_required
def series_listar():
    itens = []
    return render_template("stubs/lista_com_botao.html",
                           titulo="Séries",
                           endpoint_novo="series_novo",
                           label_botao="Nova Série",
                           itens=itens)

@app.route("/series/novo", methods=["GET", "POST"], endpoint="series_novo")
@login_required
@perm_required("SERIE_ADICIONAR")
def series_novo():
    if request.method == "POST":
        flash("Stub: Série criada (implemente depois).", "info")
        return redirect(url_for("series_listar"))
    return render_template("stubs/novo_stub.html", titulo="Nova Série")

@app.route("/atividades", endpoint="atividades_listar")
@login_required
def atividades_listar():
    itens = []
    return render_template("stubs/lista_com_botao.html",
                           titulo="Atividades",
                           endpoint_novo="atividades_novo",
                           label_botao="Nova Atividade",
                           itens=itens)

@app.route("/atividades/novo", methods=["GET", "POST"], endpoint="atividades_novo")
@login_required
@perm_required("ATIVIDADE_ADICIONAR")
def atividades_novo():
    if request.method == "POST":
        flash("Stub: Atividade criada (implemente depois).", "info")
        return redirect(url_for("atividades_listar"))
    return render_template("stubs/novo_stub.html", titulo="Nova Atividade")

@app.route("/horarios", endpoint="horarios_listar")
@login_required
def horarios_listar():
    itens = []
    return render_template("stubs/lista_com_botao.html",
                           titulo="Horários",
                           endpoint_novo="horarios_novo",
                           label_botao="Novo Horário",
                           itens=itens)

@app.route("/horarios/novo", methods=["GET", "POST"], endpoint="horarios_novo")
@login_required
@perm_required("HORARIO_ADICIONAR")
def horarios_novo():
    if request.method == "POST":
        flash("Stub: Horário criado (implemente depois).", "info")
        return redirect(url_for("horarios_listar"))
    return render_template("stubs/novo_stub.html", titulo="Novo Horário")

# =============================================================================
# ERROS
# =============================================================================
@app.errorhandler(Forbidden)
@app.errorhandler(403)
def handle_forbidden(e):
    flash("Você não possui permissão para esta tarefa.", "danger")
    ref = request.referrer
    return redirect(ref or url_for("index"))

@app.errorhandler(Unauthorized)
@app.errorhandler(401)
def handle_unauthorized(e):
    flash("Faça login para continuar.", "warning")
    return redirect(url_for("login"))

@app.errorhandler(NotFound)
@app.errorhandler(404)
def handle_not_found(e):
    flash("Página não encontrada.", "warning")
    ref = request.referrer
    return redirect(ref or url_for("index"))

# =============================================================================
# INIT
# =============================================================================
def init_db_if_needed():
    with app.app_context():
        db.create_all()
        seed_permissoes()
        seed_admin()

if os.environ.get("RUN_INIT_ON_BOOT", "1") == "1":
    try:
        init_db_if_needed()
    except Exception as e:
        print("Init-on-boot falhou:", e)

if __name__ == "__main__":
    with app.app_context():
        init_db_if_needed()
    app.run(debug=True)
