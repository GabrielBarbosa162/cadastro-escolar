# auth.py (CORRIGIDO: models são criadas dentro de register_auth)
from __future__ import annotations
import os, uuid
from datetime import datetime, timedelta
from functools import wraps

from flask import Blueprint, render_template, request, redirect, url_for, flash, abort, current_app
from flask_sqlalchemy import SQLAlchemy
from flask_login import (
    LoginManager, UserMixin, login_user, logout_user,
    current_user, login_required
)
from werkzeug.security import generate_password_hash, check_password_hash

# ---------------------------------------------------------------------
# Blueprint e extensões (db é injetado em register_auth)
# ---------------------------------------------------------------------
auth_bp = Blueprint("auth", __name__, template_folder="templates/auth")

login_manager = LoginManager()
login_manager.login_view = "auth.login"
login_manager.login_message_category = "warning"

db: SQLAlchemy | None = None  # será injetado

# Placeholders para tipos exportados após registro
Usuario = None
ResetToken = None

# ---------------------------------------------------------------------
# Decoradores RBAC (independentes das models)
# ---------------------------------------------------------------------
def role_required(*roles):
    def deco(fn):
        @wraps(fn)
        @login_required
        def wrapped(*args, **kwargs):
            if not current_user.is_authenticated:
                abort(401)
            if not getattr(current_user, "ativo", False):
                abort(403)
            if getattr(current_user, "papel", None) not in roles:
                abort(403)
            return fn(*args, **kwargs)
        return wrapped
    return deco

def any_role(*roles):
    def deco(fn):
        @wraps(fn)
        @login_required
        def wrapped(*args, **kwargs):
            if not current_user.is_authenticated or not getattr(current_user, "ativo", False):
                abort(403)
            if getattr(current_user, "papel", None) not in roles:
                abort(403)
            return fn(*args, **kwargs)
        return wrapped
    return deco

# ---------------------------------------------------------------------
# Rotas (as funções usam as globals Usuario/ResetToken em runtime)
# ---------------------------------------------------------------------
@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    global Usuario
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        senha = request.form.get("senha") or ""
        user = Usuario.query.filter_by(email=email).first()
        if not user or not user.check_password(senha):
            flash("E-mail ou senha inválidos.", "danger")
            return render_template("auth/login.html")
        if not user.ativo:
            flash("Usuário inativo. Procure a Diretoria.", "warning")
            return render_template("auth/login.html")
        login_user(user)
        flash("Bem-vindo!", "success")
        return redirect(request.args.get("next") or url_for("index"))
    return render_template("auth/login.html")

@auth_bp.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    flash("Sessão encerrada.", "info")
    return redirect(url_for("auth.login"))

@auth_bp.route("/usuarios")
@role_required("DIRETORIA")
def usuarios_list():
    global Usuario
    usuarios = Usuario.query.order_by(Usuario.created_at.desc()).all()
    return render_template("auth/usuarios_list.html", usuarios=usuarios)

@auth_bp.route("/usuarios/novo", methods=["GET", "POST"])
@role_required("DIRETORIA")
def usuario_novo():
    global Usuario, db
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        senha = request.form.get("senha") or ""
        confirmar = request.form.get("confirmar") or ""
        papel = (request.form.get("papel") or "").strip().upper()

        if not email or "@" not in email:
            flash("Informe um e-mail válido.", "warning"); return render_template("auth/usuario_form.html")
        if len(senha) < 8 or not any(c.isdigit() for c in senha):
            flash("Senha deve ter pelo menos 8 caracteres e 1 número.", "warning"); return render_template("auth/usuario_form.html")
        if senha != confirmar:
            flash("As senhas não conferem.", "warning"); return render_template("auth/usuario_form.html")
        if papel not in ("DIRETORIA", "PROFESSOR", "RESPONSAVEL", "ALUNO"):
            flash("Selecione um papel válido.", "warning"); return render_template("auth/usuario_form.html")

        if Usuario.query.filter_by(email=email).first():
            flash("Já existe um usuário com este e-mail.", "danger"); return render_template("auth/usuario_form.html")

        u = Usuario(email=email, papel=papel, ativo=True)
        u.set_password(senha)
        db.session.add(u)
        db.session.commit()
        flash("Usuário criado com sucesso!", "success")
        return redirect(url_for("auth.usuarios_list"))

    return render_template("auth/usuario_form.html")

@auth_bp.route("/usuarios/<int:uid>/ativar", methods=["POST"])
@role_required("DIRETORIA")
def usuario_ativar(uid: int):
    global Usuario, db
    u = Usuario.query.get_or_404(uid)
    u.ativo = not u.ativo
    db.session.commit()
    flash("Situação do usuário atualizada.", "success")
    return redirect(url_for("auth.usuarios_list"))

@auth_bp.route("/esqueci", methods=["GET", "POST"])
def esqueci():
    global Usuario, ResetToken, db
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        msg_ok = "Se o e-mail existir, enviaremos instruções de redefinição."
        user = Usuario.query.filter_by(email=email).first()
        if not user:
            flash(msg_ok, "info"); return render_template("auth/esqueci.html")

        token = str(uuid.uuid4())
        rt = ResetToken(
            usuario_id=user.id,
            token=token,
            expira_em=datetime.utcnow() + timedelta(hours=1)
        )
        db.session.add(rt); db.session.commit()

        reset_link = f"{request.host_url.rstrip('/')}{url_for('auth.reset', token=token)}"
        current_app.logger.info(f"[RESET] Link para {email}: {reset_link}")
        flash(msg_ok, "info")
        return render_template("auth/esqueci.html", dev_link=reset_link)

    return render_template("auth/esqueci.html")

@auth_bp.route("/reset/<token>", methods=["GET", "POST"])
def reset(token: str):
    global ResetToken, db
    rt = ResetToken.query.filter_by(token=token).first()
    if not rt or rt.usado_em is not None or rt.expira_em < datetime.utcnow():
        flash("Link inválido ou expirado.", "danger")
        return redirect(url_for("auth.esqueci"))

    if request.method == "POST":
        senha = request.form.get("senha") or ""
        confirmar = request.form.get("confirmar") or ""
        if len(senha) < 8 or not any(c.isdigit() for c in senha):
            flash("Senha deve ter pelo menos 8 caracteres e 1 número.", "warning")
            return render_template("auth/reset.html")
        if senha != confirmar:
            flash("As senhas não conferem.", "warning")
            return render_template("auth/reset.html")
        u = rt.usuario
        u.set_password(senha)
        rt.usado_em = datetime.utcnow()
        db.session.commit()
        flash("Senha redefinida com sucesso. Faça login.", "success")
        return redirect(url_for("auth.login"))

    return render_template("auth/reset.html")

# ---------------------------------------------------------------------
# Registro no app principal (injeta db, cria models e seeds)
# ---------------------------------------------------------------------
def register_auth(app, database: SQLAlchemy):
    global db, Usuario, ResetToken

    db = database  # injeta a instância do app principal
    login_manager.init_app(app)
    app.register_blueprint(auth_bp)

    # ----- Declarar models AGORA, com db injetado -----
    class _Usuario(db.Model, UserMixin):  # type: ignore[misc]
        __tablename__ = "usuario"
        id = db.Column(db.Integer, primary_key=True)
        email = db.Column(db.String(180), unique=True, nullable=False, index=True)
        senha_hash = db.Column(db.String(255), nullable=False)
        papel = db.Column(db.String(20), nullable=False)  # DIRETORIA|PROFESSOR|RESPONSAVEL|ALUNO
        ativo = db.Column(db.Boolean, default=True)
        created_at = db.Column(db.DateTime, default=datetime.utcnow)

        def set_password(self, senha: str):
            self.senha_hash = generate_password_hash(senha)

        def check_password(self, senha: str) -> bool:
            return check_password_hash(self.senha_hash, senha)

    class _ResetToken(db.Model):  # type: ignore[misc]
        __tablename__ = "reset_token"
        id = db.Column(db.Integer, primary_key=True)
        usuario_id = db.Column(db.Integer, db.ForeignKey("usuario.id", ondelete="CASCADE"), nullable=False)
        token = db.Column(db.String(64), unique=True, nullable=False)
        expira_em = db.Column(db.DateTime, nullable=False)
        usado_em = db.Column(db.DateTime, nullable=True)
        created_at = db.Column(db.DateTime, default=datetime.utcnow)

        usuario = db.relationship("_Usuario")

    # Exporta para o módulo (rotas usam essas globals em runtime)
    globals()["Usuario"] = _Usuario
    globals()["ResetToken"] = _ResetToken

    # user_loader precisa existir DEPOIS das models
    @login_manager.user_loader
    def load_user(user_id: str):
        try:
            return _Usuario.query.get(int(user_id))
        except Exception:
            return None

    # Cria tabelas e seed do admin
    with app.app_context():
        db.create_all()
        if not _Usuario.query.first():
            admin_email = "admin@escola.com"
            admin_pass = os.getenv("ADMIN_PASS", "Trocar123")
            admin = _Usuario(email=admin_email, papel="DIRETORIA", ativo=True)
            admin.set_password(admin_pass)
            db.session.add(admin)
            db.session.commit()
            app.logger.info(f"[SEED] Usuário diretoria criado: {admin_email} / senha: {admin_pass}")

__all__ = ["register_auth", "role_required", "any_role"]
