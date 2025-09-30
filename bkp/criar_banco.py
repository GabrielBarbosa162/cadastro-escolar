import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DB_PATH = os.path.join(BASE_DIR, "alunos.db")

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{DB_PATH}"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

class Escola(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(200), nullable=False, unique=True)

class Serie(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False, unique=True)

class Aluno(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    # Dados pessoais
    nome_completo = db.Column(db.String(200), nullable=False)
    data_nascimento = db.Column(db.Date, nullable=False)
    estado = db.Column(db.String(2), nullable=False)
    cidade = db.Column(db.String(100), nullable=False)
    bairro = db.Column(db.String(100), nullable=False)
    complemento = db.Column(db.String(200))

    # Telefones
    tel_aluno = db.Column(db.String(30))
    tel_pai = db.Column(db.String(30))
    tel_mae = db.Column(db.String(30))

    # Foto
    foto = db.Column(db.String(255))

    # Dados escolares
    escola_id = db.Column(db.Integer, db.ForeignKey("escola.id"))
    serie_id = db.Column(db.Integer, db.ForeignKey("serie.id"))
    professora = db.Column(db.String(150))

    escola = db.relationship("Escola", backref="alunos")
    serie = db.relationship("Serie", backref="alunos")

with app.app_context():
    db.create_all()

print(f"Banco criado com sucesso em: {DB_PATH}")
