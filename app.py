import os
import uuid
from datetime import datetime, timedelta

from flask import (
    Flask, render_template, request, redirect, url_for,
    flash, abort, session as flask_session, send_from_directory
)
from flask_login import (
    LoginManager, login_user, logout_user,
    login_required, current_user
)
from functools import wraps
from werkzeug.exceptions import Forbidden, Unauthorized, NotFound
from models import (
    db, Usuario, Permissao, UsuarioPermissao, UserSession,
    Escola, Serie, Horario, Mensalidade
)

# -----------------------------------------------------------------------------
# Config básica
# -----------------------------------------------------------------------------
app = Flask(__name__, template_folder="templates", static_folder="static")
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-keep-it-safe")
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL", "sqlite:///alunos.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

UPLOAD_DIR = os.path.join(app.root_path, "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

db.init_app(app)

# -----------------------------------------------------------------------------
# Login Manager
# -----------------------------------------------------------------------------
login_manager = LoginManager(app)
login_manager.login_view = "login"

@login_manager.user_loader
def load_user(user_id):
    return Usuario.query.get(int(user_id))

@app.context_processor
def inject_blueprints_and_perms():
    from flask import current_app
    def _has(code):
        try:
            return current_user.is_authenticated and usuario_tem_permissao(current_user, code)
        except Exception:
            return False
    papel_ok = current_user.is_authenticated and (getattr(current_user, "papel", "") in ("DIRETORIA", "PROFESSOR"))
    return {
        "bp_names": set(current_app.blueprints.keys()),
        "can_aluno_criar": papel_ok or _has("ALUNO_CRIAR"),
        "can_aluno_editar": papel_ok or _has("ALUNO_EDITAR"),
        "can_aluno_excluir": papel_ok or _has("ALUNO_EXCLUIR"),
    }

# -----------------------------------------------------------------------------
# Permissões
# -----------------------------------------------------------------------------
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
PERMISSOES_CODIGOS = list(PERMISSOES_NOMES.keys())

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

# -----------------------------------------------------------------------------
# Sessão (presença)
# -----------------------------------------------------------------------------
SESS_ACTIVE_MINUTES = 15

@app.before_request
def _atualiza_ultimo_seen():
    if current_user.is_authenticated:
        sid = flask_session.get("session_id")
        if sid:
            us = UserSession.query.filter_by(session_id=sid).first()
            if us:
                us.ultimo_seen = datetime.utcnow()
                db.session.commit()

def registrar_login_sessao(usuario: Usuario):
    sid = flask_session.get("session_id")
    if not sid:
        sid = str(uuid.uuid4())
        flask_session["session_id"] = sid
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

# -----------------------------------------------------------------------------
# Seeds
# -----------------------------------------------------------------------------
def seed_permissoes():
    criadas = 0
    for cod, nome in PERMISSOES_NOMES.items():
        if not Permissao.query.filter_by(codigo=cod).first():
            db.session.add(Permissao(codigo=cod, nome_exibicao=nome))
            criadas += 1
    if criadas:
        db.session.commit()

def seed_admin():
    if Usuario.query.count() == 0:
        admin = Usuario(email="admin@escola.com", papel="DIRETORIA", ativo=True)
        admin.set_password(os.environ.get("ADMIN_PASS", "Trocar123"))
        db.session.add(admin)
        db.session.commit()
        print("Usuário DIRETORIA criado: admin@escola.com / Trocar123")

def seed_mensalidades():
    if Mensalidade.query.count() == 0:
        db.session.add_all([
            Mensalidade(faixa="PRE_1_5", label="Pré 1 a 5º ano – 170,00 R$", valor=170.00),
            Mensalidade(faixa="6_7",   label="6º a 7º ano – 180,00 R$", valor=180.00),
            Mensalidade(faixa="8_9",   label="8º a 9º ano – 190,00 R$", valor=190.00),
        ])
        db.session.commit()

# -----------------------------------------------------------------------------
# Uploads
# -----------------------------------------------------------------------------
@app.route("/uploads/<path:filename>")
def uploads(filename):
    return send_from_directory(UPLOAD_DIR, filename, as_attachment=False)

# -----------------------------------------------------------------------------
# Auth
# -----------------------------------------------------------------------------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        senha = request.form.get("senha", "")
        user = Usuario.query.filter_by(email=email).first()
        if user and user.check_password(senha) and user.ativo:
            login_user(user)
            registrar_login_sessao(user)
            flash("Login realizado com sucesso!", "success")
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

# -----------------------------------------------------------------------------
# Usuários (lista / novo / salvar permissões / painel)
# -----------------------------------------------------------------------------
@app.route("/usuarios")
@login_required
def usuarios_list():
    if current_user.papel != "DIRETORIA":
        abort(403)

    mostrar_todos = request.args.get("mostrar") == "todos"
    usuarios = Usuario.query.order_by(Usuario.email.asc()).all()

    last_seen_map, active_map = {}, {}
    def _is_active_session(sess: UserSession) -> bool:
        return sess.is_active and (datetime.utcnow() - sess.ultimo_seen) <= timedelta(minutes=SESS_ACTIVE_MINUTES)

    if not mostrar_todos:
        filtrados = []
        for u in usuarios:
            s = (UserSession.query
                 .filter_by(usuario_id=u.id, is_active=True)
                 .order_by(UserSession.ultimo_seen.desc())
                 .first())
            if s and _is_active_session(s):
                filtrados.append(u)
                last_seen_map[u.id] = s.ultimo_seen
                active_map[u.id] = True
        usuarios = filtrados
    else:
        for u in usuarios:
            s = (UserSession.query
                 .filter_by(usuario_id=u.id, is_active=True)
                 .order_by(UserSession.ultimo_seen.desc())
                 .first())
            if s:
                last_seen_map[u.id] = s.ultimo_seen
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

    return render_template("usuarios_list.html",
        usuarios=usuarios,
        permissoes_codigos=PERMISSOES_CODIGOS,
        permissoes_nomes=PERMISSOES_NOMES,
        mostrar_todos=mostrar_todos,
        last_seen_map=last_seen_map,
        active_map=active_map,
        permissoes_por_usuario=permissoes_por_usuario
    )

@app.route("/usuarios/novo", methods=["GET", "POST"])
@login_required
@perm_required("USUARIO_CRIAR")
def usuarios_novo():
    if current_user.papel != "DIRETORIA":
        abort(403)
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

@app.route("/usuarios/<int:usuario_id>/permissoes", methods=["POST"])
@login_required
def usuarios_salvar_permissoes(usuario_id):
    if current_user.papel != "DIRETORIA":
        abort(403)
    u = Usuario.query.get_or_404(usuario_id)

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
        abort(403)
    u = Usuario.query.get_or_404(usuario_id)
    has_perm = {cod: usuario_tem_permissao(u, cod) for cod in PERMISSOES_CODIGOS}
    return render_template("usuario_painel.html", user=u, has_perm=has_perm)

# -----------------------------------------------------------------------------
# Index
# -----------------------------------------------------------------------------
@app.route("/")
@login_required
def index():
    return render_template("index.html")

# -----------------------------------------------------------------------------
# Handlers de erro (alerta no topo + redirect)
# -----------------------------------------------------------------------------
@app.errorhandler(Forbidden)
@app.errorhandler(403)
def handle_forbidden(e):
    flash("Você não possui permissão para esta tarefa.", "danger")
    ref = request.referrer
    if ref and ref != request.url:
        return redirect(ref)
    return redirect(url_for("index"))

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
    if ref and ref != request.url:
        return redirect(ref)
    return redirect(url_for("index"))

# -----------------------------------------------------------------------------
# Blueprints
# -----------------------------------------------------------------------------
from alunos import bp as alunos_bp
app.register_blueprint(alunos_bp)

from escolas import bp as escolas_bp
app.register_blueprint(escolas_bp)

from series import bp as series_bp
app.register_blueprint(series_bp)

from atividades import bp as atividades_bp
app.register_blueprint(atividades_bp)

from horarios import bp as horarios_bp
app.register_blueprint(horarios_bp)

# -----------------------------------------------------------------------------
# Boot
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    with app.app_context():
        db.create_all()
        seed_permissoes()
        seed_admin()
        seed_mensalidades()
    app.run(debug=True)
