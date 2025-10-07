import os
import json
import uuid
from datetime import datetime, time as dtime
from functools import wraps

from flask import (
    Flask, render_template, request, redirect, url_for,
    flash, abort, session as flask_session, send_from_directory, jsonify
)
from flask_sqlalchemy import SQLAlchemy
from flask_login import (
    LoginManager, UserMixin, login_user, logout_user,
    login_required, current_user
)
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import UniqueConstraint, ForeignKey
from sqlalchemy.orm import relationship
from werkzeug.exceptions import Forbidden, Unauthorized, NotFound

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

# Expor view_functions para Jinja (evita current_app undefined)
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

class AlunoExtra(db.Model):
    """
    Campos adicionais do Aluno (sem quebrar a tabela existente).
    Armazena como JSON: naturalidade, nacionalidade, datas, sexo,
    nomes dos pais, endereço, números, bairro, telefones, série, dificuldade etc.
    """
    __tablename__ = "aluno_extra"
    id = db.Column(db.Integer, primary_key=True)
    aluno_id = db.Column(db.Integer, db.ForeignKey("aluno.id", ondelete="CASCADE"), unique=True)
    dados = db.Column(db.Text, nullable=False, default="{}")  # JSON str
    aluno = relationship("Aluno", backref=db.backref("extra", uselist=False, cascade="all, delete-orphan"))

class Escola(db.Model):
    __tablename__ = "escola"
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(200), unique=True, nullable=False)
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)

class Serie(db.Model):
    __tablename__ = "serie"
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(120), unique=True, nullable=False)
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)

class Horario(db.Model):
    __tablename__ = "horario"
    id = db.Column(db.Integer, primary_key=True)
    hora_inicio = db.Column(db.String(5), nullable=False)  # HH:MM
    hora_fim = db.Column(db.String(5), nullable=False)     # HH:MM
    label = db.Column(db.String(20), nullable=False)       # "HH:MM - HH:MM"
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)

class Atividade(db.Model):
    __tablename__ = "atividade"
    id = db.Column(db.Integer, primary_key=True)
    aluno_id = db.Column(db.Integer, ForeignKey("aluno.id", ondelete="SET NULL"))
    aluno = relationship("Aluno")
    data_atividade = db.Column(db.String(10))  # dd/mm/aaaa
    conteudo = db.Column(db.Text)
    observacao = db.Column(db.Text)
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)

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
# SAÚDE / SESSÃO
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
# AUTH
# =============================================================================
@login_manager.user_loader
def load_user(user_id):
    return Usuario.query.get(int(user_id))

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
# USUÁRIOS + PERMISSÕES
# =============================================================================
@app.route("/usuarios", methods=["GET"], endpoint="usuarios_list")
@login_required
def usuarios_list():
    if current_user.papel != "DIRETORIA":
        abort(403)
    usuarios = Usuario.query.order_by(Usuario.email.asc()).all()
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
        permissoes_por_usuario=permissoes_por_usuario
    )

@app.route("/usuarios/<int:usuario_id>/permissoes", methods=["POST"], endpoint="usuarios_salvar_permissoes")
@login_required
def usuarios_salvar_permissoes(usuario_id):
    if current_user.papel != "DIRETORIA":
        abort(403)
    u = Usuario.query.get_or_404(usuario_id)

    if u.papel == "DIRETORIA":
        flash("Diretoria já possui todas as permissões por padrão.", "info")
        return redirect(url_for("usuarios_list"))

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
    return redirect(url_for("usuarios_list"))

@app.route("/usuarios/novo", methods=["GET", "POST"], endpoint="usuarios_novo")
@login_required
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

# =============================================================================
# HELPERS
# =============================================================================
def _parse_hhmm(val: str) -> dtime | None:
    try:
        hh, mm = val.split(":")
        return dtime(hour=int(hh), minute=int(mm))
    except Exception:
        return None

def _get_bool(val):
    return True if str(val).lower() in ("1", "true", "on", "sim") else False

# =============================================================================
# ALUNOS (lista + novo/editar/excluir) — com campos extras no JSON
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
    escolas = Escola.query.order_by(Escola.nome.asc()).all()
    series = Serie.query.order_by(Serie.nome.asc()).all()
    horarios = Horario.query.order_by(Horario.hora_inicio.asc()).all()

    if request.method == "POST":
        nome = request.form.get("nome","").strip()
        escola = request.form.get("escola") or request.form.get("escola_text","")
        serie = request.form.get("serie","")
        horario_sel = request.form.get("horario_sel","")
        horario_txt = request.form.get("horario_txt","").strip()
        horario = horario_sel or horario_txt  # usa o horário selecionado ou texto livre
        telefone_mae = request.form.get("telefone_mae","").strip()

        # Foto
        foto_file = request.files.get("foto")
        foto_path = None
        if foto_file and foto_file.filename:
            fname = f"{uuid.uuid4().hex}_{foto_file.filename}"
            foto_file.save(os.path.join(UPLOAD_DIR, fname))
            foto_path = fname

        if not nome:
            flash("Informe o nome do aluno.", "warning")
            return render_template("alunos/novo.html", escolas=escolas, series=series, horarios=horarios)

        # cria aluno básico
        aluno = Aluno(nome=nome, escola=escola, horario=horario, telefone_mae=telefone_mae, foto_path=foto_path)
        db.session.add(aluno)
        db.session.flush()  # obter ID

        # monta JSON dos campos extras
        dados = {
            "naturalidade": request.form.get("naturalidade","").strip(),
            "nacionalidade": request.form.get("nacionalidade","").strip(),
            "data_nascimento": request.form.get("data_nascimento","").strip(),
            "idade": request.form.get("idade","").strip(),
            "anos": request.form.get("anos","").strip(),
            "sexo": request.form.get("sexo","").strip(),
            "nome_pai": request.form.get("nome_pai","").strip(),
            "nome_mae": request.form.get("nome_mae","").strip(),
            "endereco": request.form.get("endereco","").strip(),
            "numero": request.form.get("numero","").strip(),
            "bairro": request.form.get("bairro","").strip(),
            "telefone_celular": request.form.get("telefone_celular","").strip(),
            "telefone_fixo": request.form.get("telefone_fixo","").strip(),
            "serie": serie,
            "dificuldade": request.form.get("dificuldade","nao"),
            "dificuldade_qual": request.form.get("dificuldade_qual","").strip(),
            "medicamento_controlado": request.form.get("medicamento_controlado","nao"),
            "medicamento_qual": request.form.get("medicamento_qual","").strip(),
            "matutino_sim": _get_bool(request.form.get("matutino_sim")),
            "horario_matutino": request.form.get("horario_matutino","").strip(),
            "vespertino_sim": _get_bool(request.form.get("vespertino_sim")),
            "horario_vespertino": request.form.get("horario_vespertino","").strip(),
            "inicio_aulas": request.form.get("inicio_aulas","").strip(),
            "mensalidade": request.form.get("mensalidade","").strip(),  # 170/180/190
        }
        db.session.add(AlunoExtra(aluno_id=aluno.id, dados=json.dumps(dados, ensure_ascii=False)))
        db.session.commit()
        flash("Aluno cadastrado!", "success")
        return redirect(url_for("alunos_listar"))

    return render_template("alunos/novo.html", escolas=escolas, series=series, horarios=horarios)

@app.route("/alunos/<int:id>/editar", methods=["GET", "POST"], endpoint="alunos_editar")
@login_required
@perm_required("ALUNO_EDITAR")
def alunos_editar(id):
    aluno = Aluno.query.get_or_404(id)
    escolas = Escola.query.order_by(Escola.nome.asc()).all()
    series = Serie.query.order_by(Serie.nome.asc()).all()
    horarios = Horario.query.order_by(Horario.hora_inicio.asc()).all()

    extra = aluno.extra.dados if aluno.extra else "{}"
    dados = {}
    try:
        dados = json.loads(extra)
    except Exception:
        dados = {}

    if request.method == "POST":
        aluno.nome = request.form.get("nome","").strip()
        aluno.escola = request.form.get("escola") or request.form.get("escola_text","")
        aluno.horario = request.form.get("horario_sel","") or request.form.get("horario_txt","").strip()
        aluno.telefone_mae = request.form.get("telefone_mae","").strip()

        foto_file = request.files.get("foto")
        if foto_file and foto_file.filename:
            fname = f"{uuid.uuid4().hex}_{foto_file.filename}"
            foto_file.save(os.path.join(UPLOAD_DIR, fname))
            aluno.foto_path = fname

        if not aluno.nome:
            flash("Informe o nome do aluno.", "warning")
            return render_template("alunos/editar.html", aluno=aluno, dados=dados, escolas=escolas, series=series, horarios=horarios)

        dados_atual = {
            "naturalidade": request.form.get("naturalidade","").strip(),
            "nacionalidade": request.form.get("nacionalidade","").strip(),
            "data_nascimento": request.form.get("data_nascimento","").strip(),
            "idade": request.form.get("idade","").strip(),
            "anos": request.form.get("anos","").strip(),
            "sexo": request.form.get("sexo","").strip(),
            "nome_pai": request.form.get("nome_pai","").strip(),
            "nome_mae": request.form.get("nome_mae","").strip(),
            "endereco": request.form.get("endereco","").strip(),
            "numero": request.form.get("numero","").strip(),
            "bairro": request.form.get("bairro","").strip(),
            "telefone_celular": request.form.get("telefone_celular","").strip(),
            "telefone_fixo": request.form.get("telefone_fixo","").strip(),
            "serie": request.form.get("serie",""),
            "dificuldade": request.form.get("dificuldade","nao"),
            "dificuldade_qual": request.form.get("dificuldade_qual","").strip(),
            "medicamento_controlado": request.form.get("medicamento_controlado","nao"),
            "medicamento_qual": request.form.get("medicamento_qual","").strip(),
            "matutino_sim": _get_bool(request.form.get("matutino_sim")),
            "horario_matutino": request.form.get("horario_matutino","").strip(),
            "vespertino_sim": _get_bool(request.form.get("vespertino_sim")),
            "horario_vespertino": request.form.get("horario_vespertino","").strip(),
            "inicio_aulas": request.form.get("inicio_aulas","").strip(),
            "mensalidade": request.form.get("mensalidade","").strip(),
        }

        if aluno.extra:
            aluno.extra.dados = json.dumps(dados_atual, ensure_ascii=False)
        else:
            db.session.add(AlunoExtra(aluno_id=aluno.id, dados=json.dumps(dados_atual, ensure_ascii=False)))

        db.session.commit()
        flash("Alterações salvas!", "success")
        return redirect(url_for("alunos_listar"))

    return render_template("alunos/editar.html", aluno=aluno, dados=dados, escolas=escolas, series=series, horarios=horarios)

@app.route("/alunos/<int:id>/excluir", methods=["POST"], endpoint="alunos_excluir")
@login_required
@perm_required("ALUNO_EXCLUIR")
def alunos_excluir(id):
    aluno = Aluno.query.get_or_404(id)
    db.session.delete(aluno)
    db.session.commit()
    flash("Aluno excluído!", "success")
    return redirect(url_for("alunos_listar"))

# Busca dinâmica (para atividades etc.)
@app.route("/alunos/search")
@login_required
def alunos_search():
    q = request.args.get("q","").strip().lower()
    qry = Aluno.query
    if q:
        qry = qry.filter(Aluno.nome.ilike(f"%{q}%"))
    results = qry.order_by(Aluno.nome.asc()).limit(20).all()
    return jsonify([{"id": a.id, "nome": a.nome} for a in results])

# =============================================================================
# ESCOLAS
# =============================================================================
@app.route("/escolas", endpoint="escolas_listar")
@login_required
def escolas_listar():
    escolas = Escola.query.order_by(Escola.nome.asc()).all()
    return render_template("escolas/listar.html", escolas=escolas)

@app.route("/escolas/novo", methods=["GET", "POST"], endpoint="escolas_novo")
@login_required
@perm_required("ESCOLA_ADICIONAR")
def escolas_novo():
    if request.method == "POST":
        nome = request.form.get("nome","").strip()
        if not nome:
            flash("Informe o nome da escola.", "warning")
            return render_template("escolas/novo.html")
        if Escola.query.filter(Escola.nome.ilike(nome)).first():
            flash("Já existe uma escola com esse nome.", "warning")
            return render_template("escolas/novo.html")
        db.session.add(Escola(nome=nome))
        db.session.commit()
        flash("Escola cadastrada!", "success")
        return redirect(url_for("escolas_listar"))
    return render_template("escolas/novo.html")

@app.route("/escolas/<int:id>/editar", methods=["GET", "POST"], endpoint="escolas_editar")
@login_required
@perm_required("ESCOLA_ADICIONAR")
def escolas_editar(id):
    e = Escola.query.get_or_404(id)
    if request.method == "POST":
        nome = request.form.get("nome","").strip()
        if not nome:
            flash("Informe o nome da escola.", "warning")
            return render_template("escolas/editar.html", escola=e)
        existe = Escola.query.filter(Escola.nome.ilike(nome), Escola.id != e.id).first()
        if existe:
            flash("Já existe outra escola com esse nome.", "warning")
            return render_template("escolas/editar.html", escola=e)
        e.nome = nome
        db.session.commit()
        flash("Escola atualizada!", "success")
        return redirect(url_for("escolas_listar"))
    return render_template("escolas/editar.html", escola=e)

@app.route("/escolas/<int:id>/excluir", methods=["POST"], endpoint="escolas_excluir")
@login_required
@perm_required("ESCOLA_EXCLUIR")
def escolas_excluir(id):
    e = Escola.query.get_or_404(id)
    db.session.delete(e)
    db.session.commit()
    flash("Escola excluída!", "success")
    return redirect(url_for("escolas_listar"))

# =============================================================================
# SÉRIES
# =============================================================================
@app.route("/series", endpoint="series_listar")
@login_required
def series_listar():
    series = Serie.query.order_by(Serie.nome.asc()).all()
    return render_template("series/listar.html", series=series)

@app.route("/series/novo", methods=["GET", "POST"], endpoint="series_novo")
@login_required
@perm_required("SERIE_ADICIONAR")
def series_novo():
    if request.method == "POST":
        nome = request.form.get("nome","").strip()
        if not nome:
            flash("Informe o nome da série.", "warning")
            return render_template("series/novo.html")
        if Serie.query.filter(Serie.nome.ilike(nome)).first():
            flash("Já existe uma série com esse nome.", "warning")
            return render_template("series/novo.html")
        db.session.add(Serie(nome=nome))
        db.session.commit()
        flash("Série cadastrada!", "success")
        return redirect(url_for("series_listar"))
    return render_template("series/novo.html")

@app.route("/series/<int:id>/editar", methods=["GET", "POST"], endpoint="series_editar")
@login_required
@perm_required("SERIE_ADICIONAR")
def series_editar(id):
    s = Serie.query.get_or_404(id)
    if request.method == "POST":
        nome = request.form.get("nome","").strip()
        if not nome:
            flash("Informe o nome da série.", "warning")
            return render_template("series/editar.html", serie=s)
        existe = Serie.query.filter(Serie.nome.ilike(nome), Serie.id != s.id).first()
        if existe:
            flash("Já existe outra série com esse nome.", "warning")
            return render_template("series/editar.html", serie=s)
        s.nome = nome
        db.session.commit()
        flash("Série atualizada!", "success")
        return redirect(url_for("series_listar"))
    return render_template("series/editar.html", serie=s)

@app.route("/series/<int:id>/excluir", methods=["POST"], endpoint="series_excluir")
@login_required
@perm_required("SERIE_EXCLUIR")
def series_excluir(id):
    s = Serie.query.get_or_404(id)
    db.session.delete(s)
    db.session.commit()
    flash("Série excluída!", "success")
    return redirect(url_for("series_listar"))

# =============================================================================
# HORÁRIOS
# =============================================================================
@app.route("/horarios", endpoint="horarios_listar")
@login_required
def horarios_listar():
    horarios = Horario.query.order_by(Horario.hora_inicio.asc()).all()
    return render_template("horarios/listar.html", horarios=horarios)

@app.route("/horarios/novo", methods=["GET", "POST"], endpoint="horarios_novo")
@login_required
@perm_required("HORARIO_ADICIONAR")
def horarios_novo():
    if request.method == "POST":
        h_ini = request.form.get("hora_inicio","").strip()
        h_fim = request.form.get("hora_fim","").strip()

        t_ini = _parse_hhmm(h_ini)
        t_fim = _parse_hhmm(h_fim)

        if not t_ini or not t_fim:
            flash("Informe horas válidas no formato HH:MM.", "warning")
            return render_template("horarios/novo.html")

        if t_fim <= t_ini:
            flash("A hora fim deve ser MAIOR que a hora início.", "danger")
            return render_template("horarios/novo.html")

        label = f"{h_ini} - {h_fim}"
        db.session.add(Horario(hora_inicio=h_ini, hora_fim=h_fim, label=label))
        db.session.commit()
        flash("Horário cadastrado!", "success")
        return redirect(url_for("horarios_listar"))

    return render_template("horarios/novo.html")

@app.route("/horarios/<int:id>/editar", methods=["GET", "POST"], endpoint="horarios_editar")
@login_required
@perm_required("HORARIO_ADICIONAR")
def horarios_editar(id):
    h = Horario.query.get_or_404(id)
    if request.method == "POST":
        h_ini = request.form.get("hora_inicio","").strip()
        h_fim = request.form.get("hora_fim","").strip()
        t_ini = _parse_hhmm(h_ini)
        t_fim = _parse_hhmm(h_fim)
        if not t_ini or not t_fim:
            flash("Informe horas válidas no formato HH:MM.", "warning")
            return render_template("horarios/editar.html", horario=h)
        if t_fim <= t_ini:
            flash("A hora fim deve ser MAIOR que a hora início.", "danger")
            return render_template("horarios/editar.html", horario=h)
        h.hora_inicio = h_ini
        h.hora_fim = h_fim
        h.label = f"{h_ini} - {h_fim}"
        db.session.commit()
        flash("Horário atualizado!", "success")
        return redirect(url_for("horarios_listar"))
    return render_template("horarios/editar.html", horario=h)

@app.route("/horarios/<int:id>/excluir", methods=["POST"], endpoint="horarios_excluir")
@login_required
@perm_required("HORARIO_EXCLUIR")
def horarios_excluir(id):
    h = Horario.query.get_or_404(id)
    db.session.delete(h)
    db.session.commit()
    flash("Horário excluído!", "success")
    return redirect(url_for("horarios_listar"))

# =============================================================================
# ATIVIDADES
# =============================================================================
@app.route("/atividades", endpoint="atividades_listar")
@login_required
def atividades_listar():
    atividades = (Atividade.query
                  .order_by(Atividade.criado_em.desc())
                  .all())
    return render_template("atividades/listar.html", atividades=atividades)

@app.route("/atividades/novo", methods=["GET", "POST"], endpoint="atividades_novo")
@login_required
@perm_required("ATIVIDADE_ADICIONAR")
def atividades_novo():
    if request.method == "POST":
        aluno_id = request.form.get("aluno_id")
        data_atividade = request.form.get("data_atividade","").strip()
        conteudo = request.form.get("conteudo","").strip()
        observacao = request.form.get("observacao","").strip()

        if not aluno_id or not aluno_id.isdigit():
            flash("Selecione um aluno.", "warning")
            alunos = Aluno.query.order_by(Aluno.nome.asc()).all()
            return render_template("atividades/novo.html", alunos=alunos)

        atv = Atividade(
            aluno_id=int(aluno_id),
            data_atividade=data_atividade,
            conteudo=conteudo,
            observacao=observacao
        )
        db.session.add(atv)
        db.session.commit()
        flash("Atividade lançada!", "success")
        return redirect(url_for("atividades_listar"))

    alunos = Aluno.query.order_by(Aluno.nome.asc()).all()
    return render_template("atividades/novo.html", alunos=alunos)

@app.route("/atividades/<int:id>/editar", methods=["GET", "POST"], endpoint="atividades_editar")
@login_required
@perm_required("ATIVIDADE_ADICIONAR")
def atividades_editar(id):
    atv = Atividade.query.get_or_404(id)
    if request.method == "POST":
        aluno_id = request.form.get("aluno_id")
        data_atividade = request.form.get("data_atividade","").strip()
        conteudo = request.form.get("conteudo","").strip()
        observacao = request.form.get("observacao","").strip()
        if not aluno_id or not aluno_id.isdigit():
            flash("Selecione um aluno.", "warning")
            alunos = Aluno.query.order_by(Aluno.nome.asc()).all()
            return render_template("atividades/editar.html", atividade=atv, alunos=alunos)
        atv.aluno_id = int(aluno_id)
        atv.data_atividade = data_atividade
        atv.conteudo = conteudo
        atv.observacao = observacao
        db.session.commit()
        flash("Atividade atualizada!", "success")
        return redirect(url_for("atividades_listar"))
    alunos = Aluno.query.order_by(Aluno.nome.asc()).all()
    return render_template("atividades/editar.html", atividade=atv, alunos=alunos)

@app.route("/atividades/<int:id>/excluir", methods=["POST"], endpoint="atividades_excluir")
@login_required
@perm_required("ATIVIDADE_EXCLUIR")
def atividades_excluir(id):
    atv = Atividade.query.get_or_404(id)
    db.session.delete(atv)
    db.session.commit()
    flash("Atividade excluída!", "success")
    return redirect(url_for("atividades_listar"))

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
