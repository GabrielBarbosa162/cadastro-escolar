import os
from datetime import datetime, date, timedelta
from flask import (
    Flask, render_template, request, redirect, url_for,
    flash, send_from_directory
)
from flask_sqlalchemy import SQLAlchemy
from flask_login import (
    LoginManager, UserMixin, login_user, logout_user,
    login_required, current_user
)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

# =============================
# CONFIG
# =============================
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

app = Flask(__name__, template_folder="templates", static_folder="static")
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret")
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get(
    "DATABASE_URL",
    f"sqlite:///{os.path.join(BASE_DIR, 'alunos.db')}"
)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

if app.config["SQLALCHEMY_DATABASE_URI"].startswith("postgres://"):
    app.config["SQLALCHEMY_DATABASE_URI"] = app.config["SQLALCHEMY_DATABASE_URI"].replace(
        "postgres://", "postgresql://", 1
    )

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = "login"

# =============================
# MODELS
# =============================
class Usuario(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(180), unique=True, nullable=False)
    senha_hash = db.Column(db.String(255), nullable=False)
    papel = db.Column(db.String(20), nullable=False, default="RESPONSAVEL")  # DIRETORIA, PROFESSOR, etc.
    ativo = db.Column(db.Boolean, default=True)

    def set_password(self, senha):
        self.senha_hash = generate_password_hash(senha)

    def check_password(self, senha):
        return check_password_hash(self.senha_hash, senha)


class Escola(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(120), nullable=False, unique=True)


class Serie(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(120), nullable=False, unique=True)


class Horario(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    hora_inicio = db.Column(db.String(5), nullable=False)  # HH:MM
    hora_fim = db.Column(db.String(5), nullable=False)     # HH:MM


class Aluno(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(180), nullable=False)
    escola_id = db.Column(db.Integer, db.ForeignKey("escola.id"))
    serie_id = db.Column(db.Integer, db.ForeignKey("serie.id"))
    horario_id = db.Column(db.Integer, db.ForeignKey("horario.id"))
    telefone_mae = db.Column(db.String(50))
    foto_path = db.Column(db.String(255))
    observacoes = db.Column(db.Text)

    escola = db.relationship("Escola", backref="alunos")
    serie = db.relationship("Serie", backref="alunos")
    horario = db.relationship("Horario", backref="alunos")


class Atividade(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    aluno_id = db.Column(db.Integer, db.ForeignKey("aluno.id"), nullable=False)
    data = db.Column(db.Date, nullable=False)
    conteudo = db.Column(db.Text)
    observacao = db.Column(db.Text)
    aluno = db.relationship("Aluno", backref="atividades")


# =============================
# CONTEXT PROCESSOR (can / is_diretoria)
# =============================
@app.context_processor
def inject_perms():
    def can(code: str) -> bool:
        # Simples: Diretoria pode tudo; demais, sem granularidade por enquanto.
        return getattr(current_user, "is_authenticated", False) and getattr(current_user, "papel", "") == "DIRETORIA"

    return {
        "can": can,
        "is_diretoria": getattr(current_user, "papel", "") == "DIRETORIA" if current_user.is_authenticated else False
    }

# =============================
# AUTH
# =============================
@login_manager.user_loader
def load_user(uid):
    try:
        return Usuario.query.get(int(uid))
    except Exception:
        return None

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        senha = request.form.get("senha", "")
        u = Usuario.query.filter_by(email=email).first()
        if u and u.check_password(senha) and u.ativo:
            login_user(u)
            flash("Bem-vindo!", "success")
            return redirect(url_for("index"))
        flash("Credenciais inválidas ou usuário inativo.", "danger")
    return render_template("login.html")

@app.post("/logout")
@login_required
def logout():
    logout_user()
    flash("Sessão encerrada.", "success")
    return redirect(url_for("login"))

# =============================
# DASHBOARD
# =============================
@app.route("/")
@login_required
def index():
    total = Aluno.query.count()
    return render_template("index.html", alunos_total=total)

@app.route("/uploads/<path:filename>")
@login_required
def uploads(filename):
    return send_from_directory(UPLOAD_DIR, filename)

# =============================
# HELPERS
# =============================
def _valida_horas(h_ini: str, h_fim: str) -> bool:
    try:
        i = datetime.strptime(h_ini, "%H:%M")
        f = datetime.strptime(h_fim, "%H:%M")
        return f > i
    except Exception:
        return False

# =============================
# ALUNOS
# =============================
@app.route("/alunos/", endpoint="alunos_list")
@login_required
def alunos_list():
    items = Aluno.query.order_by(Aluno.nome.asc()).all()
    return render_template("alunos/listar.html", items=items)

@app.route("/alunos/listar", endpoint="alunos_listar")
@login_required
def alunos_listar_alias():
    return redirect(url_for("alunos_list"))

@app.route("/alunos/novo", methods=["GET", "POST"], endpoint="alunos_novo")
@login_required
def alunos_novo():
    if request.method == "POST":
        nome = request.form["nome"].strip()
        escola_id = request.form.get("escola_id") or None
        serie_id = request.form.get("serie_id") or None
        horario_id = request.form.get("horario_id") or None
        telefone_mae = request.form.get("telefone_mae")
        observacoes = request.form.get("observacoes")

        foto = request.files.get("foto")
        foto_path = None
        if foto and foto.filename:
            fname = datetime.now().strftime("%Y%m%d%H%M%S_") + secure_filename(foto.filename)
            foto.save(os.path.join(UPLOAD_DIR, fname))
            foto_path = fname

        novo = Aluno(
            nome=nome, escola_id=escola_id, serie_id=serie_id, horario_id=horario_id,
            telefone_mae=telefone_mae, foto_path=foto_path, observacoes=observacoes
        )
        db.session.add(novo)
        db.session.commit()
        flash("Aluno cadastrado com sucesso!", "success")
        return redirect(url_for("alunos_list"))

    escolas = Escola.query.order_by(Escola.nome.asc()).all()
    series = Serie.query.order_by(Serie.nome.asc()).all()
    horarios = Horario.query.order_by(Horario.hora_inicio.asc()).all()
    return render_template("alunos/form.html", aluno=None, escolas=escolas, series=series, horarios=horarios)

@app.route("/alunos/<int:id>/editar", methods=["GET", "POST"], endpoint="alunos_editar")
@login_required
def alunos_editar(id):
    a = Aluno.query.get_or_404(id)
    if request.method == "POST":
        a.nome = request.form["nome"].strip()
        a.escola_id = request.form.get("escola_id") or None
        a.serie_id = request.form.get("serie_id") or None
        a.horario_id = request.form.get("horario_id") or None
        a.telefone_mae = request.form.get("telefone_mae")
        a.observacoes = request.form.get("observacoes")

        foto = request.files.get("foto")
        if foto and foto.filename:
            fname = datetime.now().strftime("%Y%m%d%H%M%S_") + secure_filename(foto.filename)
            foto.save(os.path.join(UPLOAD_DIR, fname))
            a.foto_path = fname

        db.session.commit()
        flash("Aluno atualizado!", "success")
        return redirect(url_for("alunos_list"))

    escolas = Escola.query.order_by(Escola.nome.asc()).all()
    series = Serie.query.order_by(Serie.nome.asc()).all()
    horarios = Horario.query.order_by(Horario.hora_inicio.asc()).all()
    return render_template("alunos/form.html", aluno=a, escolas=escolas, series=series, horarios=horarios)

@app.post("/alunos/<int:id>/excluir", endpoint="alunos_excluir")
@login_required
def alunos_excluir(id):
    a = Aluno.query.get_or_404(id)
    db.session.delete(a)
    db.session.commit()
    flash("Aluno excluído.", "success")
    return redirect(url_for("alunos_list"))

# =============================
# HORÁRIOS
# =============================
@app.route("/horarios/", endpoint="horarios_list")
@login_required
def horarios_list():
    items = Horario.query.order_by(Horario.hora_inicio.asc()).all()
    return render_template("horarios/listar.html", items=items)

@app.route("/horarios/listar", endpoint="horarios_listar")
@login_required
def horarios_listar_alias():
    return redirect(url_for("horarios_list"))

@app.route("/horarios/novo", methods=["GET", "POST"], endpoint="horarios_novo")
@login_required
def horarios_novo():
    if request.method == "POST":
        hi, hf = request.form["hora_inicio"], request.form["hora_fim"]
        if not _valida_horas(hi, hf):
            flash("Hora final deve ser maior que a inicial!", "warning")
            return render_template("horarios/form.html", item=None)
        db.session.add(Horario(hora_inicio=hi, hora_fim=hf))
        db.session.commit()
        flash("Horário cadastrado!", "success")
        return redirect(url_for("horarios_list"))
    return render_template("horarios/form.html", item=None)

@app.route("/horarios/<int:id>/editar", methods=["GET", "POST"], endpoint="horarios_editar")
@login_required
def horarios_editar(id):
    h = Horario.query.get_or_404(id)
    if request.method == "POST":
        hi, hf = request.form["hora_inicio"], request.form["hora_fim"]
        if not _valida_horas(hi, hf):
            flash("Hora final deve ser maior que a inicial!", "warning")
            return render_template("horarios/form.html", item=h)
        h.hora_inicio, h.hora_fim = hi, hf
        db.session.commit()
        flash("Horário atualizado!", "success")
        return redirect(url_for("horarios_list"))
    return render_template("horarios/form.html", item=h)

@app.post("/horarios/<int:id>/excluir", endpoint="horarios_excluir")
@login_required
def horarios_excluir(id):
    h = Horario.query.get_or_404(id)
    db.session.delete(h)
    db.session.commit()
    flash("Horário excluído!", "success")
    return redirect(url_for("horarios_list"))

# =============================
# ESCOLAS
# =============================
@app.route("/escolas/", endpoint="escolas_list")
@login_required
def escolas_list():
    items = Escola.query.order_by(Escola.nome.asc()).all()
    return render_template("escolas/listar.html", items=items)

@app.route("/escolas/listar", endpoint="escolas_listar")
@login_required
def escolas_listar_alias():
    return redirect(url_for("escolas_list"))

@app.route("/escolas/nova", methods=["GET", "POST"], endpoint="escolas_nova")
@login_required
def escolas_nova():
    if request.method == "POST":
        nome = request.form["nome"].strip()
        if not nome:
            flash("Informe o nome da escola.", "warning")
            return render_template("escolas/form.html", item=None)
        if Escola.query.filter_by(nome=nome).first():
            flash("Essa escola já existe.", "warning")
            return render_template("escolas/form.html", item=None)
        db.session.add(Escola(nome=nome))
        db.session.commit()
        flash("Escola cadastrada!", "success")
        return redirect(url_for("escolas_list"))
    return render_template("escolas/form.html", item=None)

@app.route("/escolas/<int:id>/editar", methods=["GET", "POST"], endpoint="escolas_editar")
@login_required
def escolas_editar(id):
    e = Escola.query.get_or_404(id)
    if request.method == "POST":
        nome = request.form["nome"].strip()
        if not nome:
            flash("Informe o nome da escola.", "warning")
            return render_template("escolas/form.html", item=e)
        existe = Escola.query.filter(Escola.id != e.id, Escola.nome == nome).first()
        if existe:
            flash("Já existe outra escola com esse nome.", "warning")
            return render_template("escolas/form.html", item=e)
        e.nome = nome
        db.session.commit()
        flash("Escola atualizada!", "success")
        return redirect(url_for("escolas_list"))
    return render_template("escolas/form.html", item=e)

@app.post("/escolas/<int:id>/excluir", endpoint="escolas_excluir")
@login_required
def escolas_excluir(id):
    e = Escola.query.get_or_404(id)
    db.session.delete(e)
    db.session.commit()
    flash("Escola excluída!", "success")
    return redirect(url_for("escolas_list"))

# =============================
# SÉRIES
# =============================
@app.route("/series/", endpoint="series_list")
@login_required
def series_list():
    items = Serie.query.order_by(Serie.nome.asc()).all()
    return render_template("series/listar.html", items=items)

@app.route("/series/listar", endpoint="series_listar")
@login_required
def series_listar_alias():
    return redirect(url_for("series_list"))

# Alias para corrigir o BuildError: series_novo → series_nova
@app.route("/series/novo", endpoint="series_novo")
@login_required
def series_novo_alias():
    return redirect(url_for("series_nova"))

@app.route("/series/nova", methods=["GET", "POST"], endpoint="series_nova")
@login_required
def series_nova():
    if request.method == "POST":
        nome = request.form["nome"].strip()
        if not nome:
            flash("Informe o nome da série.", "warning")
            return render_template("series/form.html", item=None)
        if Serie.query.filter_by(nome=nome).first():
            flash("Essa série já existe.", "warning")
            return render_template("series/form.html", item=None)
        db.session.add(Serie(nome=nome))
        db.session.commit()
        flash("Série cadastrada!", "success")
        return redirect(url_for("series_list"))
    return render_template("series/form.html", item=None)

@app.route("/series/<int:id>/editar", methods=["GET", "POST"], endpoint="series_editar")
@login_required
def series_editar(id):
    s = Serie.query.get_or_404(id)
    if request.method == "POST":
        nome = request.form["nome"].strip()
        if not nome:
            flash("Informe o nome da série.", "warning")
            return render_template("series/form.html", item=s)
        existe = Serie.query.filter(Serie.id != s.id, Serie.nome == nome).first()
        if existe:
            flash("Já existe outra série com esse nome.", "warning")
            return render_template("series/form.html", item=s)
        s.nome = nome
        db.session.commit()
        flash("Série atualizada!", "success")
        return redirect(url_for("series_list"))
    return render_template("series/form.html", item=s)

@app.post("/series/<int:id>/excluir", endpoint="series_excluir")
@login_required
def series_excluir(id):
    s = Serie.query.get_or_404(id)
    db.session.delete(s)
    db.session.commit()
    flash("Série excluída!", "success")
    return redirect(url_for("series_list"))

# =============================
# ATIVIDADES
# =============================
@app.route("/atividades/", endpoint="atividades_list")
@login_required
def atividades_list():
    itens = Atividade.query.order_by(Atividade.data.desc(), Atividade.id.desc()).all()
    return render_template("atividades/listar.html", items=itens)

@app.route("/atividades/listar", endpoint="atividades_listar")
@login_required
def atividades_listar_alias():
    return redirect(url_for("atividades_list"))

@app.route("/atividades/nova", methods=["GET", "POST"], endpoint="atividades_nova")
@login_required
def atividades_nova():
    if request.method == "POST":
        aluno_id = int(request.form["aluno_id"])
        data_str = request.form.get("data") or date.today().isoformat()
        conteudo = request.form.get("conteudo")
        observacao = request.form.get("observacao")
        try:
            dt = datetime.strptime(data_str, "%Y-%m-%d").date()
        except Exception:
            dt = date.today()
        at = Atividade(aluno_id=aluno_id, data=dt, conteudo=conteudo, observacao=observacao)
        db.session.add(at)
        db.session.commit()
        flash("Atividade lançada!", "success")
        return redirect(url_for("atividades_list"))
    alunos = Aluno.query.order_by(Aluno.nome.asc()).all()
    return render_template("atividades/form.html", item=None, alunos=alunos)

@app.route("/atividades/<int:id>/editar", methods=["GET", "POST"], endpoint="atividades_editar")
@login_required
def atividades_editar(id):
    at = Atividade.query.get_or_404(id)
    if request.method == "POST":
        at.aluno_id = int(request.form["aluno_id"])
        data_str = request.form.get("data") or date.today().isoformat()
        try:
            at.data = datetime.strptime(data_str, "%Y-%m-%d").date()
        except Exception:
            at.data = date.today()
        at.conteudo = request.form.get("conteudo")
        at.observacao = request.form.get("observacao")
        db.session.commit()
        flash("Atividade atualizada!", "success")
        return redirect(url_for("atividades_list"))
    alunos = Aluno.query.order_by(Aluno.nome.asc()).all()
    return render_template("atividades/form.html", item=at, alunos=alunos)

@app.post("/atividades/<int:id>/excluir", endpoint="atividades_excluir")
@login_required
def atividades_excluir(id):
    at = Atividade.query.get_or_404(id)
    db.session.delete(at)
    db.session.commit()
    flash("Atividade excluída!", "success")
    return redirect(url_for("atividades_list"))

# =============================
# USUÁRIOS
# =============================
@app.route("/usuarios/", endpoint="usuarios_list")
@login_required
def usuarios_list():
    if current_user.papel != "DIRETORIA":
        flash("Você não possui permissão para esta tarefa.", "warning")
        return redirect(url_for("index"))
    usuarios = Usuario.query.order_by(Usuario.email.asc()).all()
    return render_template("usuarios/listar.html", usuarios=usuarios)

@app.route("/usuarios/novo", methods=["GET", "POST"], endpoint="usuarios_novo")
@login_required
def usuarios_novo():
    if current_user.papel != "DIRETORIA":
        flash("Você não possui permissão para esta tarefa.", "warning")
        return redirect(url_for("index"))
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        senha = request.form.get("senha", "")
        papel = request.form.get("papel", "RESPONSAVEL")
        if not email or not senha:
            flash("Preencha email e senha.", "warning")
            return render_template("usuarios/form.html", user=None)
        if len(senha) < 8 or not any(ch.isdigit() for ch in senha):
            flash("Senha deve ter ao menos 8 caracteres e 1 dígito.", "warning")
            return render_template("usuarios/form.html", user=None)
        if Usuario.query.filter_by(email=email).first():
            flash("E-mail já cadastrado.", "warning")
            return render_template("usuarios/form.html", user=None)
        u = Usuario(email=email, papel=papel, ativo=True)
        u.set_password(senha)
        db.session.add(u)
        db.session.commit()
        flash("Usuário criado.", "success")
        return redirect(url_for("usuarios_list"))
    return render_template("usuarios/form.html", user=None)

@app.route("/usuarios/<int:id>/editar", methods=["GET", "POST"], endpoint="usuarios_editar")
@login_required
def usuarios_editar(id):
    if current_user.papel != "DIRETORIA":
        flash("Você não possui permissão para esta tarefa.", "warning")
        return redirect(url_for("index"))
    u = Usuario.query.get_or_404(id)
    if request.method == "POST":
        novo_papel = request.form.get("papel", u.papel)
        ativo = bool(request.form.get("ativo"))
        u.papel = novo_papel
        u.ativo = ativo
        if request.form.get("senha"):
            s = request.form["senha"]
            if len(s) < 8 or not any(ch.isdigit() for ch in s):
                flash("Senha deve ter ao menos 8 caracteres e 1 dígito.", "warning")
                return render_template("usuarios/form.html", user=u)
            u.set_password(s)
        db.session.commit()
        flash("Usuário atualizado.", "success")
        return redirect(url_for("usuarios_list"))
    return render_template("usuarios/form.html", user=u)

# =============================
# SEEDS E BOOT
# =============================
def seed_admin():
    if Usuario.query.count() == 0:
        admin = Usuario(email=os.environ.get("ADMIN_EMAIL", "admin@escola.com"),
                        papel="DIRETORIA", ativo=True)
        admin.set_password(os.environ.get("ADMIN_PASS", "Trocar123"))
        db.session.add(admin)
        db.session.commit()
        print("Usuário DIRETORIA criado: admin@escola.com / Trocar123")

with app.app_context():
    db.create_all()
    seed_admin()

if __name__ == "__main__":
    app.run(debug=True)
