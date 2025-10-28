import os
import uuid
from datetime import datetime, timedelta, timezone
from functools import wraps

from flask import (
    Flask, render_template, request, redirect, url_for,
    flash, abort, session as flask_session, send_from_directory, current_app
)
from flask_sqlalchemy import SQLAlchemy
from flask_login import (
    LoginManager, UserMixin, login_user, logout_user,
    login_required, current_user
)
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import UniqueConstraint

# ============================ Tempo (sempre timezone-aware UTC) ============================
def utcnow():
    return datetime.now(timezone.utc)

def _aware(dt):
    """Conserta registros antigos sem tz (naive) assumindo UTC."""
    if dt is None:
        return utcnow()
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)

# ============================ Extensões globais (sem bind no import) ======================
db = SQLAlchemy()
login_manager = LoginManager()
login_manager.login_view = "login"

# ======================================= MODELOS ==========================================
class Usuario(db.Model, UserMixin):
    __tablename__ = "usuario"
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(180), unique=True, nullable=False)
    senha_hash = db.Column(db.String(255), nullable=False)
    papel = db.Column(db.String(20), nullable=False, default="RESPONSAVEL")  # DIRETORIA|PROFESSOR|RESPONSAVEL|ALUNO
    ativo = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow)

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
    session_id = db.Column(db.String(60), unique=True, nullable=False)
    login_em = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    ultimo_seen = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    is_active = db.Column(db.Boolean, default=True, nullable=False)

    usuario = db.relationship("Usuario")

    def marcar_seen(self):
        self.ultimo_seen = utcnow()

# ===================================== LOGIN MANAGER =======================================
@login_manager.user_loader
def load_user(user_id):
    try:
        return db.session.get(Usuario, int(user_id))
    except Exception:
        return None

# ======================================== PERMISSÕES =======================================
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
    if not usuario or not getattr(usuario, "is_authenticated", False) or not usuario.ativo:
        return False
    if usuario.papel == "DIRETORIA":
        return True
    up = (
        UsuarioPermissao.query
        .join(Permissao, UsuarioPermissao.permissao_id == Permissao.id)
        .filter(UsuarioPermissao.usuario_id == usuario.id, Permissao.codigo == codigo)
        .first()
    )
    return up is not None

def perm_required(codigo: str):
    def deco(fn):
        @wraps(fn)
        @login_required
        def wrapper(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for("login"))
            if not current_user.ativo:
                flash("Sua conta está inativa.", "warning")
                return redirect(url_for("index"))
            if not usuario_tem_permissao(current_user, codigo):
                flash("Você não possui permissão para esta tarefa.", "warning")
                return redirect(request.referrer or url_for("index"))
            return fn(*args, **kwargs)
        return wrapper
    return deco

# ====================================== APP FACTORY ========================================
def create_app():
    app = Flask(__name__, template_folder="templates", static_folder="static")

    # ---------- Config ----------
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-keep-it-safe")
    base_dir = os.path.abspath(os.path.dirname(__file__))
    upload_dir = os.path.join(base_dir, "uploads")
    os.makedirs(upload_dir, exist_ok=True)
    app.config["UPLOAD_DIR"] = upload_dir

    _db_url = os.environ.get("DATABASE_URL", f"sqlite:///{os.path.join(base_dir, 'alunos.db')}")
    if _db_url.startswith("postgres://"):
        _db_url = _db_url.replace("postgres://", "postgresql://", 1)
    app.config["SQLALCHEMY_DATABASE_URI"] = _db_url
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    # ---------- Bind extensões ----------
    db.init_app(app)
    login_manager.init_app(app)

    # ---------- Helpers em templates ----------
    @app.context_processor
    def inject_template_helpers():
        vfs = {}
        try:
            vfs = current_app.view_functions
        except Exception:
            pass

        def can(cod: str) -> bool:
            try:
                return usuario_tem_permissao(current_user, cod)
            except Exception:
                return False

        def safe_url(endpoint: str, **values):
            """Só faz url_for se endpoint existir; senão, retorna '#'."""
            try:
                if endpoint in vfs:
                    return url_for(endpoint, **values)
            except Exception:
                pass
            return "#"

        is_dir = bool(
            getattr(current_user, "is_authenticated", False)
            and getattr(current_user, "papel", "") == "DIRETORIA"
        )
        return {"view_functions": vfs, "can": can, "is_diretoria": is_dir, "safe_url": safe_url}

    # ---------- Hooks de sessão ----------
    @app.before_request
    def _atualiza_ultimo_seen():
        if current_user.is_authenticated:
            sid = flask_session.get("session_id")
            if sid:
                us = UserSession.query.filter_by(session_id=sid, usuario_id=current_user.id, is_active=True).first()
                if us:
                    us.marcar_seen()
                    db.session.commit()

    def registrar_login_sessao(usuario: Usuario):
        sid = flask_session.get("session_id")
        if not sid:
            sid = str(uuid.uuid4())
            flask_session["session_id"] = sid
        existe = UserSession.query.filter_by(session_id=sid, usuario_id=usuario.id, is_active=True).first()
        if not existe:
            us = UserSession(usuario_id=usuario.id, session_id=sid, is_active=True)
            db.session.add(us)
            db.session.commit()

    def registrar_logout_sessao():
        sid = flask_session.get("session_id")
        if sid and current_user.is_authenticated:
            us = UserSession.query.filter_by(session_id=sid, usuario_id=current_user.id, is_active=True).first()
            if us:
                us.is_active = False
                db.session.commit()
        flask_session.pop("session_id", None)

    app.registrar_login_sessao = registrar_login_sessao
    app.registrar_logout_sessao = registrar_logout_sessao

    # ---------- Seeds ----------
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
            admin = Usuario(
                email=os.environ.get("ADMIN_EMAIL", "admin@escola.com"),
                papel="DIRETORIA",
                ativo=True,
            )
            admin.set_password(os.environ.get("ADMIN_PASS", "Trocar123"))
            db.session.add(admin)
            db.session.commit()
            print("Usuário DIRETORIA criado: admin@escola.com / Trocar123")

    # ---------- Rotas principais ----------
    @app.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "POST":
            email = request.form.get("email", "").strip().lower()
            senha = request.form.get("senha", "")
            user = Usuario.query.filter_by(email=email).first()
            if user and user.check_password(senha) and user.ativo:
                login_user(user)
                current_app.registrar_login_sessao(user)
                flash("Login realizado com sucesso!", "success")
                return redirect(url_for("index"))
            flash("Credenciais inválidas ou usuário inativo.", "danger")
        return render_template("login.html")

    @app.route("/logout", methods=["POST"])
    @login_required
    def logout():
        current_app.registrar_logout_sessao()
        logout_user()
        flash("Sessão encerrada.", "info")
        return redirect(url_for("login"))

    @app.route("/")
    @login_required
    def index():
        return render_template("index.html")

    @app.route("/usuarios/novo", methods=["GET", "POST"])
    @login_required
    @perm_required("USUARIO_CRIAR")
    def usuarios_novo():
        if current_user.papel != "DIRETORIA":
            flash("Você não possui permissão para esta tarefa.", "warning")
            return redirect(url_for("index"))

        if request.method == "POST":
            email = request.form.get("email", "").strip().lower()
            senha = request.form.get("senha", "")
            confirmar = request.form.get("confirmar", "")
            papel = request.form.get("papel", "RESPONSAVEL")

            if not email or not senha or not confirmar:
                flash("Preencha todos os campos.", "warning")
                return render_template("usuario_form.html")

            if senha != confirmar:
                flash("A confirmação de senha não confere.", "warning")
                return render_template("usuario_form.html")

            if len(senha) < 8 or not any(ch.isdigit() for ch in senha):
                flash("Senha deve ter ao menos 8 caracteres e 1 dígito.", "warning")
                return render_template("usuario_form.html")

            if Usuario.query.filter_by(email=email).first():
                flash("E-mail já cadastrado.", "warning")
                return render_template("usuario_form.html")

            u = Usuario(email=email, papel=papel, ativo=True)
            u.set_password(senha)
            db.session.add(u)
            db.session.commit()
            flash("Usuário criado com sucesso.", "success")
            return redirect(url_for("usuarios_list"))

        return render_template("usuario_form.html")

    @app.route("/usuarios")
    @login_required
    def usuarios_list():
        if current_user.papel != "DIRETORIA":
            flash("Você não possui permissão para esta tarefa.", "warning")
            return redirect(url_for("index"))

        mostrar_todos = request.args.get("mostrar") == "todos"
        usuarios = Usuario.query.order_by(Usuario.email.asc()).all()

        last_seen_map = {}
        active_map = {}

        def _is_active_session(sess: UserSession) -> bool:
            # sempre comparar aware com aware
            return sess.is_active and (utcnow() - _aware(sess.ultimo_seen)) <= timedelta(minutes=15)

        if not mostrar_todos:
            filtrados = []
            for u in usuarios:
                s = (
                    UserSession.query
                    .filter_by(usuario_id=u.id, is_active=True)
                    .order_by(UserSession.ultimo_seen.desc())
                    .first()
                )
                if s and _is_active_session(s):
                    filtrados.append(u)
                    last_seen_map[u.id] = _aware(s.ultimo_seen)
                    active_map[u.id] = True
            usuarios = filtrados
        else:
            for u in usuarios:
                s = (
                    UserSession.query
                    .filter_by(usuario_id=u.id, is_active=True)
                    .order_by(UserSession.ultimo_seen.desc())
                    .first()
                )
                if s:
                    last_seen_map[u.id] = _aware(s.ultimo_seen)
                    active_map[u.id] = _is_active_session(s)
                else:
                    last_seen_map[u.id] = None
                    active_map[u.id] = False

        permissoes_por_usuario = {}
        for u in usuarios:
            if u.papel == "DIRETORIA":
                permissoes_por_usuario[u.id] = {cod: True for cod in PERMISSOES_CODIGOS}
            else:
                marcadas = set(
                    p.codigo for p in (
                        Permissao.query
                        .join(UsuarioPermissao, UsuarioPermissao.permissao_id == Permissao.id)
                        .filter(UsuarioPermissao.usuario_id == u.id)
                        .all()
                    )
                )
                permissoes_por_usuario[u.id] = {cod: (cod in marcadas) for cod in PERMISSOES_CODIGOS}

        return render_template(
            "usuarios_list.html",
            usuarios=usuarios,
            permissoes_codigos=PERMISSOES_CODIGOS,
            permissoes_nomes=PERMISSOES_NOMES,
            mostrar_todos=mostrar_todos,
            last_seen_map=last_seen_map,
            active_map=active_map,
            permissoes_por_usuario=permissoes_por_usuario
        )

    @app.route("/usuarios/<int:usuario_id>/permissoes", methods=["POST"])
    @login_required
    def usuarios_salvar_permissoes(usuario_id):
        if current_user.papel != "DIRETORIA":
            flash("Você não possui permissão para esta tarefa.", "warning")
            return redirect(url_for("usuarios_list"))

        u = db.session.get(Usuario, usuario_id)
        if not u:
            flash("Usuário não encontrado.", "warning")
            return redirect(url_for("usuarios_list"))

        if u.papel == "DIRETORIA":
            flash("Diretoria já possui todas as permissões por padrão.", "info")
            return redirect(url_for("usuarios_list", mostrar=request.args.get("mostrar")))

        enviados = set(request.form.getlist("permissoes[]"))
        for cod in enviados:
            if cod not in PERMISSOES_CODIGOS:
                abort(400, f"Código de permissão inválido: {cod}")

        atuais = {
            p.codigo: up for (p, up) in db.session.query(Permissao, UsuarioPermissao)
            .join(UsuarioPermissao, UsuarioPermissao.permissao_id == Permissao.id, isouter=True)
            .all()
            if up is not None and up.usuario_id == u.id
        }

        cache_perm = {p.codigo: p for p in Permissao.query.all()}

        for cod, up in list(atuais.items()):
            if cod not in enviados:
                db.session.delete(up)

        for cod in enviados:
            if cod not in atuais:
                perm = cache_perm.get(cod)
                if perm:
                    db.session.add(UsuarioPermissao(usuario_id=u.id, permissao_id=perm.id))

        db.session.commit()
        flash("Permissões atualizadas.", "success")
        return redirect(url_for("usuarios_list", mostrar=request.args.get("mostrar")))

    @app.route("/usuarios/<int:usuario_id>/painel")
    @login_required
    def usuario_painel(usuario_id):
        if current_user.papel != "DIRETORIA":
            flash("Você não possui permissão para esta tarefa.", "warning")
            return redirect(url_for("index"))
        u = db.session.get(Usuario, usuario_id)
        if not u:
            flash("Usuário não encontrado.", "warning")
            return redirect(url_for("usuarios_list"))
        has_perm = {cod: usuario_tem_permissao(u, cod) for cod in PERMISSOES_CODIGOS}
        return render_template("usuario_painel.html", user=u, has_perm=has_perm)

    @app.route("/uploads/<path:filename>")
    @login_required
    def uploads(filename):
        return send_from_directory(current_app.config["UPLOAD_DIR"], filename)

    # ---------- Registro opcional dos blueprints ----------
    def register_optional_blueprints(_app: Flask):
        # alunos
        try:
            from alunos import bp as alunos_bp
            _app.register_blueprint(alunos_bp)
            @_app.route("/alunos", endpoint="alunos_listar")
            @login_required
            def _alunos_listar_alias():
                # se blueprint saiu do ar por hot-reload, não quebra:
                try:
                    return redirect(url_for("alunos.listar"))
                except Exception:
                    flash("Módulo de alunos não disponível.", "warning")
                    return redirect(url_for("index"))
        except Exception as e:
            print("Blueprint 'alunos' não encontrado/erro:", e)

        # escolas
        try:
            from escolas import bp as escolas_bp
            _app.register_blueprint(escolas_bp)
            @_app.route("/escolas", endpoint="escolas_listar")
            @login_required
            def _escolas_listar_alias():
                try:
                    return redirect(url_for("escolas.listar"))
                except Exception:
                    flash("Módulo de escolas não disponível.", "warning")
                    return redirect(url_for("index"))
        except Exception as e:
            print("Blueprint 'escolas' não encontrado/erro:", e)

        # series
        try:
            from series import bp as series_bp
            _app.register_blueprint(series_bp)
            @_app.route("/series", endpoint="series_listar")
            @login_required
            def _series_listar_alias():
                try:
                    return redirect(url_for("series.listar"))
                except Exception:
                    flash("Módulo de séries não disponível.", "warning")
                    return redirect(url_for("index"))
        except Exception as e:
            print("Blueprint 'series' não encontrado/erro:", e)

        # atividades
        try:
            from atividades import bp as atividades_bp
            _app.register_blueprint(atividades_bp)
            @_app.route("/atividades", endpoint="atividades_listar")
            @login_required
            def _atividades_listar_alias():
                try:
                    return redirect(url_for("atividades.listar"))
                except Exception:
                    flash("Módulo de atividades não disponível.", "warning")
                    return redirect(url_for("index"))
        except Exception as e:
            print("Blueprint 'atividades' não encontrado/erro:", e)

        # horarios
        try:
            from horarios import bp as horarios_bp
            _app.register_blueprint(horarios_bp)
            @_app.route("/horarios", endpoint="horarios_listar")
            @login_required
            def _horarios_listar_alias():
                try:
                    return redirect(url_for("horarios.listar"))
                except Exception:
                    flash("Módulo de horários não disponível.", "warning")
                    return redirect(url_for("index"))
        except Exception as e:
            print("Blueprint 'horarios' não encontrado/erro:", e)

    # ---------- Inicialização: DB + seeds + BPs + templates mínimos ----------
    with app.app_context():
        db.create_all()
        seed_permissoes()
        seed_admin()
        register_optional_blueprints(app)
        _ensure_min_templates(app)

    # ---------- Handlers ----------
    @app.errorhandler(403)
    def forbidden(_e):
        flash("Você não possui permissão para esta tarefa.", "warning")
        return redirect(request.referrer or url_for("index"))

    @app.errorhandler(404)
    def not_found(_e):
        flash("Página não encontrada.", "warning")
        return redirect(url_for("index"))

    return app

# ============================ Templates mínimos para evitar 404 =============================
def _ensure_min_templates(app: Flask):
    base_path = os.path.join(app.root_path, "templates")
    os.makedirs(base_path, exist_ok=True)
    os.makedirs(os.path.join(base_path, "horarios"), exist_ok=True)

    templates = {
        "base.html": """<!doctype html>
<html lang="pt-br" data-bs-theme="dark">
<head>
  <meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{% block title %}Cadastro Escolar{% endblock %}</title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
  <style>.avatar-sm{width:42px;height:42px;object-fit:cover;border-radius:8px}</style>
</head>
<body>
<nav class="navbar navbar-expand-lg bg-body-tertiary border-bottom">
  <div class="container">
    <a class="navbar-brand fw-bold" href="{{ url_for('index') }}">Cadastro Escolar</a>
    <button class="navbar-toggler" type="button" data-bs-toggle="collapse" data-bs-target="#nv"><span class="navbar-toggler-icon"></span></button>
    <div id="nv" class="collapse navbar-collapse">
      <ul class="navbar-nav me-auto mb-2 mb-lg-0">
        {% if current_user.is_authenticated %}
          <li class="nav-item"><a class="nav-link" href="{{ safe_url('alunos_listar') }}">Alunos</a></li>
          {% if can('ESCOLA_ADICIONAR') or can('ESCOLA_EXCLUIR') %}
            <li class="nav-item"><a class="nav-link" href="{{ safe_url('escolas_listar') }}">Escolas</a></li>
          {% endif %}
          {% if can('SERIE_ADICIONAR') or can('SERIE_EXCLUIR') %}
            <li class="nav-item"><a class="nav-link" href="{{ safe_url('series_listar') }}">Séries</a></li>
          {% endif %}
          {% if can('ATIVIDADE_ADICIONAR') or can('ATIVIDADE_EXCLUIR') %}
            <li class="nav-item"><a class="nav-link" href="{{ safe_url('atividades_listar') }}">Atividades</a></li>
          {% endif %}
          {% if can('HORARIO_ADICIONAR') or can('HORARIO_EXCLUIR') %}
            <li class="nav-item"><a class="nav-link" href="{{ safe_url('horarios_listar') }}">Horários</a></li>
          {% endif %}
          {% if is_diretoria %}
            <li class="nav-item"><a class="nav-link" href="{{ url_for('usuarios_list') }}">Usuários</a></li>
          {% endif %}
        {% endif %}
      </ul>
      <div class="d-flex">
        {% if current_user.is_authenticated %}
          <form method="post" action="{{ url_for('logout') }}"><button class="btn btn-outline-light btn-sm">Sair</button></form>
        {% else %}
          <a class="btn btn-outline-light btn-sm" href="{{ url_for('login') }}">Entrar</a>
        {% endif %}
      </div>
    </div>
  </div>
</nav>

<div class="container position-relative" style="min-height: calc(100vh - 56px);">
  <div class="position-fixed top-0 start-50 translate-middle-x mt-3" style="z-index:1080;">
    {% with messages = get_flashed_messages(with_categories=true) %}
      {% if messages %}
        {% for category, message in messages %}
          <div class="alert alert-{{ 'warning' if category=='warning' else (category or 'secondary') }} shadow-sm mb-2 auto-hide" role="alert">
            {{ message }}
          </div>
        {% endfor %}
      {% endif %}
    {% endwith %}
  </div>
  {% block content %}{% endblock %}
</div>

<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js"></script>
<script>
  setTimeout(() => {
    document.querySelectorAll('.auto-hide').forEach(el => {
      el.classList.add('fade','show');
      setTimeout(() => el.remove(), 500);
    });
  }, 5000);
</script>
</body>
</html>
""",
        "index.html": """{% extends 'base.html' %}{% block title %}Início{% endblock %}{% block content %}
<div class="py-5"><h2>Bem-vindo!</h2><p>Use a navbar para navegar.</p></div>
{% endblock %}
""",
        "login.html": """<!doctype html><html lang="pt-br"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet"><title>Login</title>
</head><body class="d-flex align-items-center" style="min-height:100vh;">
<div class="container"><div class="row justify-content-center"><div class="col-12 col-sm-10 col-md-6 col-lg-4">
  <div class="card bg-dark text-white border-secondary mt-4">
    <div class="card-body">
      <h4 class="mb-4">Login</h4>
      <form method="post">
        <div class="mb-3"><label class="form-label">E-mail</label><input type="email" name="email" class="form-control" required></div>
        <div class="mb-3"><label class="form-label">Senha</label><input type="password" name="senha" class="form-control" required></div>
        <div class="d-flex justify-content-end"><button class="btn btn-light" type="submit">Entrar</button></div>
      </form>
    </div>
  </div>
</div></div></div>
</body></html>
""",
        "usuarios_list.html": """{% extends 'base.html' %}{% block title %}Usuários{% endblock %}{% block content %}
<div class="container py-4">
  <div class="d-flex justify-content-between align-items-center">
    <h3 class="mb-0">Usuários</h3>
    <div class="d-flex gap-2">
      <a href="{{ url_for('usuarios_list', mostrar='todos' if not mostrar_todos else None) }}" class="btn btn-outline-light">
        {{ 'Mostrar apenas ativos' if mostrar_todos else 'Mostrar todos' }}
      </a>
      {% if current_user.papel == 'DIRETORIA' %}
        <a href="{{ url_for('usuarios_novo') }}" class="btn btn-light">Novo usuário</a>
      {% endif %}
    </div>
  </div>
  <div class="table-responsive mt-3">
    <table class="table table-dark table-striped align-middle">
      <thead><tr>
        <th>#</th><th>E-mail</th><th>Papel</th><th>Ativo</th><th>Último acesso</th><th>Online</th><th>Permissões</th>
      </tr></thead>
      <tbody>
      {% for u in usuarios %}
        <tr>
          <td>{{ u.id }}</td>
          <td>{{ u.email }}</td>
          <td>{{ u.papel }}</td>
          <td>{{ 'Sim' if u.ativo else 'Não' }}</td>
          <td>{% if last_seen_map.get(u.id) %}{{ last_seen_map[u.id].astimezone().strftime('%d/%m/%Y %H:%M') }}{% else %}—{% endif %}</td>
          <td>{% if active_map.get(u.id) %}<span class="badge text-bg-success">online</span>{% else %}<span class="badge text-bg-secondary">offline</span>{% endif %}</td>
          <td style="min-width:380px;">
            {% if u.papel == 'DIRETORIA' %}
              <span class="text-success">Diretoria já tem todas as permissões.</span>
            {% else %}
              <form method="post" action="{{ url_for('usuarios_salvar_permissoes', usuario_id=u.id, mostrar=('todos' if mostrar_todos else None)) }}">
                <div class="row g-2">
                  {% for cod in permissoes_codigos %}
                    <div class="col-12 col-md-6">
                      <div class="form-check">
                        <input class="form-check-input" type="checkbox" name="permissoes[]" id="perm_{{ u.id }}_{{ cod }}" value="{{ cod }}" {% if permissoes_por_usuario[u.id][cod] %}checked{% endif %}>
                        <label class="form-check-label small" for="perm_{{ u.id }}_{{ cod }}">{{ permissoes_nomes[cod] }}</label>
                      </div>
                    </div>
                  {% endfor %}
                </div>
                <div class="mt-2">
                  <button class="btn btn-sm btn-primary">Salvar</button>
                  <a class="btn btn-sm btn-outline-light" href="{{ url_for('usuario_painel', usuario_id=u.id) }}">Ver painel</a>
                </div>
              </form>
            {% endif %}
          </td>
        </tr>
      {% endfor %}
      </tbody>
    </table>
  </div>
</div>
{% endblock %}
""",
        os.path.join("horarios", "listar.html"): """{% extends 'base.html' %}{% block title %}Horários{% endblock %}{% block content %}
<div class="container py-4">
  <div class="d-flex justify-content-between align-items-center mb-3">
    <h3 class="mb-0">Lista de Horários</h3>
    {% if can("HORARIO_ADICIONAR") %}
      <a href="{{ url_for('horarios.novo') }}" class="btn btn-success">Novo Horário</a>
    {% endif %}
  </div>
  {% if horarios %}
    <div class="table-responsive">
      <table class="table table-dark table-striped align-middle">
        <thead><tr><th>#</th><th>Início</th><th>Fim</th><th>Faixa</th><th class="text-end">Ações</th></tr></thead>
        <tbody>
        {% for h in horarios %}
          <tr>
            <td>{{ h.id }}</td>
            <td>{{ h.hora_inicio }}</td>
            <td>{{ h.hora_fim }}</td>
            <td>{{ h.hora_inicio }} - {{ h.hora_fim }}</td>
            <td class="text-end">
              {% if can("HORARIO_ADICIONAR") %}
                <a class="btn btn-sm btn-primary" href="{{ url_for('horarios.editar', id=h.id) }}">Editar</a>
              {% endif %}
              {% if can("HORARIO_EXCLUIR") %}
                <form action="{{ url_for('horarios.excluir', id=h.id) }}" method="post" class="d-inline">
                  <button class="btn btn-sm btn-danger" onclick="return confirm('Excluir este horário?')">Excluir</button>
                </form>
              {% endif %}
            </td>
          </tr>
        {% endfor %}
        </tbody>
      </table>
    </div>
  {% else %}
    <div class="alert alert-warning">Nenhum horário cadastrado ainda.</div>
  {% endif %}
</div>
{% endblock %}
""",
        os.path.join("horarios", "form.html"): """{% extends 'base.html' %}{% block title %}{{ 'Editar' if horario else 'Novo' }} Horário{% endblock %}{% block content %}
<div class="container py-4">
  <h3>{{ 'Editar' if horario else 'Novo' }} Horário</h3>
  <form method="post" class="mt-3">
    <div class="row g-3">
      <div class="col-12 col-md-6">
        <label class="form-label">Hora início</label>
        <input type="time" class="form-control" name="hora_inicio" value="{{ horario.hora_inicio if horario else '' }}" required>
      </div>
      <div class="col-12 col-md-6">
        <label class="form-label">Hora fim</label>
        <input type="time" class="form-control" name="hora_fim" value="{{ horario.hora_fim if horario else '' }}" required>
      </div>
    </div>
    <div class="mt-3 d-flex gap-2">
      <button class="btn btn-primary">Salvar</button>
      <a href="{{ url_for('horarios.listar') }}" class="btn btn-secondary">Cancelar</a>
    </div>
  </form>
</div>
{% endblock %}
""",
    }

    for rel, content in templates.items():
        p = os.path.join(base_path, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        if not os.path.exists(p):
            with open(p, "w", encoding="utf-8") as f:
                f.write(content)

# ========================================== MAIN ===========================================
if __name__ == "__main__":
    app = create_app()
    app.run(debug=True)
