import os
from datetime import datetime, timezone, timedelta
from flask import (
    Flask, render_template, request, redirect, url_for, flash,
    send_from_directory
)
from flask_sqlalchemy import SQLAlchemy
from flask_login import (
    LoginManager, UserMixin, login_user, logout_user,
    current_user, login_required
)
from werkzeug.security import generate_password_hash, check_password_hash

# -----------------------------------------------------------------------------
# App e Config
# -----------------------------------------------------------------------------
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

app = Flask(__name__, template_folder="templates", static_folder="static")
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-key")
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get(
    "DATABASE_URL",
    "sqlite:///" + os.path.join(BASE_DIR, "alunos.db")
)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

login_manager = LoginManager()
login_manager.login_view = "login"
login_manager.init_app(app)

# -----------------------------------------------------------------------------
# Models
# -----------------------------------------------------------------------------
class Usuario(db.Model, UserMixin):
    __tablename__ = "usuario"
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(180), unique=True, nullable=False)
    senha_hash = db.Column(db.String(255), nullable=False)
    # DIRETORIA | PROFESSOR | RESPONSAVEL | ALUNO
    papel = db.Column(db.String(20), nullable=False, default="RESPONSAVEL")
    ativo = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    def set_password(self, senha: str):
        self.senha_hash = generate_password_hash(senha)

    def check_password(self, senha: str) -> bool:
        return check_password_hash(self.senha_hash, senha)

    def get_id(self):
        return str(self.id)


class Escola(db.Model):
    __tablename__ = "escola"
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(120), unique=True, nullable=False)
    criado_em = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))


class Serie(db.Model):
    __tablename__ = "serie"
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(120), unique=True, nullable=False)
    criado_em = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))


class Horario(db.Model):
    __tablename__ = "horario"
    id = db.Column(db.Integer, primary_key=True)
    hora_inicio = db.Column(db.String(5), nullable=False)  # "07:00"
    hora_fim = db.Column(db.String(5), nullable=False)     # "11:00"
    criado_em = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))


class Aluno(db.Model):
    __tablename__ = "aluno"
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(180), nullable=False)

    # relacionamentos
    escola_id = db.Column(db.Integer, db.ForeignKey("escola.id"))
    serie_id = db.Column(db.Integer, db.ForeignKey("serie.id"))
    horario_id = db.Column(db.Integer, db.ForeignKey("horario.id"))

    escola = db.relationship("Escola", lazy="joined")
    serie = db.relationship("Serie", lazy="joined")
    horario = db.relationship("Horario", lazy="joined")

    telefone_cel = db.Column(db.String(30))
    telefone_fixo = db.Column(db.String(30))
    foto_path = db.Column(db.String(300))
    observacoes = db.Column(db.Text)

    criado_em = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))


# -----------------------------------------------------------------------------
# Login
# -----------------------------------------------------------------------------
@login_manager.user_loader
def load_user(uid):
    try:
        return db.session.get(Usuario, int(uid))
    except Exception:
        return None


# -----------------------------------------------------------------------------
# Helpers de Template
# -----------------------------------------------------------------------------
from flask import current_app as _current_app

@app.context_processor
def inject_ui_flags():
    """
    - is_diretoria: se usuário logado é Diretoria
    - has_endpoint: set com nomes dos endpoints registrados
    """
    try:
        endpoints = set(_current_app.view_functions.keys())
    except Exception:
        endpoints = set()

    is_dir = bool(
        getattr(current_user, "is_authenticated", False) and
        getattr(current_user, "papel", "") == "DIRETORIA"
    )
    return dict(is_diretoria=is_dir, has_endpoint=endpoints)


# -----------------------------------------------------------------------------
# Rotas de Autenticação
# -----------------------------------------------------------------------------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        senha = request.form.get("senha", "")
        user = Usuario.query.filter_by(email=email).first()
        if user and user.check_password(senha) and user.ativo:
            login_user(user)
            flash("Login realizado com sucesso!", "success")
            return redirect(url_for("index"))
        flash("Credenciais inválidas ou usuário inativo.", "danger")
    return render_template("login.html")


@app.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    flash("Sessão encerrada.", "info")
    return redirect(url_for("login"))


# -----------------------------------------------------------------------------
# Index
# -----------------------------------------------------------------------------
@app.route("/")
@login_required
def index():
    total = Aluno.query.count()
    return render_template("index.html", alunos_total=total)


# -----------------------------------------------------------------------------
# Uploads (fotos)
# -----------------------------------------------------------------------------
@app.route("/uploads/<path:filename>")
@login_required
def uploads(filename):
    return send_from_directory(UPLOAD_DIR, filename)


# -----------------------------------------------------------------------------
# Usuários – lista simples (só pra satisfazer navbar + checagens)
# -----------------------------------------------------------------------------
@app.route("/usuarios")
@login_required
def usuarios_list():
    if current_user.papel != "DIRETORIA":
        flash("Você não possui permissão para esta tarefa.", "warning")
        return redirect(url_for("index"))
    usuarios = Usuario.query.order_by(Usuario.email.asc()).all()
    return render_template("usuarios/listar.html", usuarios=usuarios)


# -----------------------------------------------------------------------------
# Alunos – Listar / Novo / Editar / Excluir
# -----------------------------------------------------------------------------
@app.route("/alunos/")
@login_required
def alunos_list():
    q = request.args.get("q", "").strip()
    query = Aluno.query
    if q:
        like = f"%{q}%"
        query = query.filter(Aluno.nome.ilike(like))
    items = query.order_by(Aluno.nome.asc()).all()
    return render_template("alunos/listar.html", items=items)


@app.route("/alunos/novo", methods=["GET", "POST"])
@login_required
def alunos_novo():
    if current_user.papel != "DIRETORIA":
        flash("Você não possui permissão para esta tarefa.", "warning")
        return redirect(url_for("alunos_list"))

    escolas = Escola.query.order_by(Escola.nome.asc()).all()
    series = Serie.query.order_by(Serie.nome.asc()).all()
    horarios = Horario.query.order_by(Horario.hora_inicio.asc()).all()

    if request.method == "POST":
        nome = request.form.get("nome", "").strip()
        escola_id = request.form.get("escola_id")
        serie_id = request.form.get("serie_id")
        horario_id = request.form.get("horario_id")
        telefone_cel = request.form.get("telefone_cel", "").strip()
        telefone_fixo = request.form.get("telefone_fixo", "").strip()
        observacoes = request.form.get("observacoes", "").strip()

        if not nome:
            flash("Informe o nome do aluno.", "warning")
            return render_template("alunos/novo.html", escolas=escolas, series=series, horarios=horarios)

        a = Aluno(
            nome=nome,
            escola_id=int(escola_id) if escola_id else None,
            serie_id=int(serie_id) if serie_id else None,
            horario_id=int(horario_id) if horario_id else None,
            telefone_cel=telefone_cel or None,
            telefone_fixo=telefone_fixo or None,
            observacoes=observacoes or None,
        )

        # upload de foto (opcional)
        foto = request.files.get("foto")
        if foto and foto.filename:
            safe_name = f"aluno_{int(datetime.now().timestamp())}_{foto.filename}"
            path = os.path.join(UPLOAD_DIR, safe_name)
            foto.save(path)
            a.foto_path = safe_name

        db.session.add(a)
        db.session.commit()
        flash("Aluno cadastrado com sucesso!", "success")
        return redirect(url_for("alunos_list"))

    return render_template("alunos/novo.html", escolas=escolas, series=series, horarios=horarios)


@app.route("/alunos/<int:id>/editar", methods=["GET", "POST"])
@login_required
def alunos_editar(id):
    if current_user.papel != "DIRETORIA":
        flash("Você não possui permissão para esta tarefa.", "warning")
        return redirect(url_for("alunos_list"))

    a = Aluno.query.get_or_404(id)
    escolas = Escola.query.order_by(Escola.nome.asc()).all()
    series = Serie.query.order_by(Serie.nome.asc()).all()
    horarios = Horario.query.order_by(Horario.hora_inicio.asc()).all()

    if request.method == "POST":
        a.nome = request.form.get("nome", "").strip() or a.nome
        a.escola_id = int(request.form.get("escola_id")) if request.form.get("escola_id") else None
        a.serie_id = int(request.form.get("serie_id")) if request.form.get("serie_id") else None
        a.horario_id = int(request.form.get("horario_id")) if request.form.get("horario_id") else None
        a.telefone_cel = request.form.get("telefone_cel", "").strip() or None
        a.telefone_fixo = request.form.get("telefone_fixo", "").strip() or None
        a.observacoes = request.form.get("observacoes", "").strip() or None

        foto = request.files.get("foto")
        if foto and foto.filename:
            safe_name = f"aluno_{int(datetime.now().timestamp())}_{foto.filename}"
            path = os.path.join(UPLOAD_DIR, safe_name)
            foto.save(path)
            a.foto_path = safe_name

        db.session.commit()
        flash("Cadastro do aluno atualizado!", "success")
        return redirect(url_for("alunos_list"))

    return render_template("alunos/editar.html", a=a, escolas=escolas, series=series, horarios=horarios)


@app.route("/alunos/<int:id>/excluir", methods=["POST"])
@login_required
def alunos_excluir(id):
    if current_user.papel != "DIRETORIA":
        flash("Você não possui permissão para esta tarefa.", "warning")
        return redirect(url_for("alunos_list"))
    a = Aluno.query.get_or_404(id)
    db.session.delete(a)
    db.session.commit()
    flash("Aluno excluído!", "success")
    return redirect(url_for("alunos_list"))


# -----------------------------------------------------------------------------
# Listas simples para Escolas, Séries e Horários (navbar funcionando)
# -----------------------------------------------------------------------------
@app.route("/escolas/")
@login_required
def escolas_list():
    escolas = Escola.query.order_by(Escola.nome.asc()).all()
    return render_template("escolas/listar.html", escolas=escolas)

@app.route("/series/")
@login_required
def series_list():
    series = Serie.query.order_by(Serie.nome.asc()).all()
    return render_template("series/listar.html", series=series)

@app.route("/horarios/")
@login_required
def horarios_list():
    horarios = Horario.query.order_by(Horario.hora_inicio.asc()).all()
    return render_template("horarios/listar.html", horarios=horarios)


# -----------------------------------------------------------------------------
# Seeds
# -----------------------------------------------------------------------------
def seed_admin():
    if Usuario.query.count() == 0:
        admin = Usuario(email=os.environ.get("ADMIN_EMAIL", "admin@escola.com"), papel="DIRETORIA", ativo=True)
        admin.set_password(os.environ.get("ADMIN_PASS", "Trocar123"))
        db.session.add(admin)
        db.session.commit()
        print("Usuário DIRETORIA criado: admin@escola.com / Trocar123")


def seed_tabelas_basicas():
    if Escola.query.count() == 0:
        db.session.add_all([Escola(nome="Escola Municipal Central"), Escola(nome="Escola Estadual Modelo")])
    if Serie.query.count() == 0:
        db.session.add_all([Serie(nome="1º Ano"), Serie(nome="2º Ano"), Serie(nome="3º Ano")])
    if Horario.query.count() == 0:
        db.session.add_all([Horario(hora_inicio="07:00", hora_fim="11:00"),
                            Horario(hora_inicio="13:00", hora_fim="17:00")])
    db.session.commit()

# -----------------------------------------------------------------------------
# Util: criar apenas as tabelas que não existem
# -----------------------------------------------------------------------------
from sqlalchemy import inspect

def create_missing_tables():
    """
    Cria apenas as tabelas que ainda não existem no banco,
    evitando o erro 'table X already exists'.
    """
    insp = inspect(db.engine)
    existentes = set(insp.get_table_names())
    # pega as Table() já mapeadas no metadata
    a_criar = [t for t in db.metadata.sorted_tables if t.name not in existentes]
    if a_criar:
        db.metadata.create_all(bind=db.engine, tables=a_criar, checkfirst=True)

# -----------------------------------------------------------------------------
# Inicialização
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    with app.app_context():
        create_missing_tables()
        seed_admin()
        seed_tabelas_basicas()
    app.run(debug=True)
