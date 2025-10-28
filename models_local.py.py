from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

from app import db


# --------- Usuários / Permissões / Sessões ----------
class Usuario(db.Model, UserMixin):
    __tablename__ = "usuario"
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(180), unique=True, nullable=False)
    senha_hash = db.Column(db.String(255), nullable=False)
    papel = db.Column(db.String(20), nullable=False, default="RESPONSAVEL")
    ativo = db.Column(db.Boolean, nullable=False, default=True)
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

class UserSession(db.Model):
    __tablename__ = "user_session"
    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey("usuario.id", ondelete="CASCADE"), nullable=False)
    session_id = db.Column(db.String(60), unique=True, nullable=False)
    login_em = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    ultimo_seen = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True, nullable=False)

# ------------------- Catálogos ---------------------
class Escola(db.Model):
    __tablename__ = "escola"
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(180), unique=True, nullable=False)
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)

class Serie(db.Model):
    __tablename__ = "serie"
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(120), unique=True, nullable=False)
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)

class Horario(db.Model):
    __tablename__ = "horario"
    id = db.Column(db.Integer, primary_key=True)

    # NOVOS: apenas hora início/fim
    hora_inicio = db.Column(db.String(5))  # "HH:MM"
    hora_fim    = db.Column(db.String(5))  # "HH:MM"

    # LEGACY (existem em alguns bancos, às vezes NOT NULL)
    inicio = db.Column(db.String(5))  # "HH:MM"
    fim    = db.Column(db.String(5))  # "HH:MM"

    # Compatibilidade (usados por telas de aluno)
    nome = db.Column(db.String(120), unique=True)  # "07:30 - 11:30"
    periodo = db.Column(db.String(20))
    hora_texto = db.Column(db.String(20))

    criado_em = db.Column(db.DateTime, default=datetime.utcnow)

class Mensalidade(db.Model):
    __tablename__ = "mensalidade"
    id = db.Column(db.Integer, primary_key=True)
    faixa = db.Column(db.String(40), unique=True, nullable=False)
    label = db.Column(db.String(120), nullable=False)
    valor = db.Column(db.Float, nullable=False)
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)

# ------------------- Aluno ------------------------
class Aluno(db.Model):
    __tablename__ = "aluno"
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(180), nullable=False)
    naturalidade = db.Column(db.String(120))
    nacionalidade = db.Column(db.String(120))
    data_nascimento = db.Column(db.Date)
    idade = db.Column(db.Integer)
    anos = db.Column(db.String(20))
    sexo = db.Column(db.String(1))

    nome_pai = db.Column(db.String(180))
    nome_mae = db.Column(db.String(180))
    endereco = db.Column(db.String(240))
    numero = db.Column(db.String(30))
    bairro = db.Column(db.String(120))
    telefone_celular = db.Column(db.String(40))
    telefone_fixo = db.Column(db.String(40))

    escola = db.Column(db.String(180))
    serie = db.Column(db.String(80))
    turma = db.Column(db.String(40))

    dificuldade = db.Column(db.Boolean)
    dificuldade_qual = db.Column(db.String(240))
    medicamento_controlado = db.Column(db.Boolean)
    medicamento_qual = db.Column(db.String(240))

    matutino = db.Column(db.Boolean)
    horario_matutino = db.Column(db.String(40))
    vespertino = db.Column(db.Boolean)
    horario_vespertino = db.Column(db.String(40))

    inicio_aulas = db.Column(db.Date)
    mensalidade = db.Column(db.Float)
    faixa_mensalidade = db.Column(db.String(40))

    horario_resumo = db.Column(db.String(80))  # compatível com Horario.nome
    telefone_mae = db.Column(db.String(40))
    foto_path = db.Column(db.String(240))

    criado_em = db.Column(db.DateTime, default=datetime.utcnow)
    atualizado_em = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

# ------------------- Atividade --------------------
class Atividade(db.Model):
    __tablename__ = "atividade"
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(180), nullable=False)  # título
    aluno_id = db.Column(db.Integer)
    aluno_nome = db.Column(db.String(180))
    data_atividade = db.Column(db.Date)
    conteudo = db.Column(db.Text)
    observacao = db.Column(db.Text)
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)
