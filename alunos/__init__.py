from flask import Blueprint

bp = Blueprint("alunos", __name__, url_prefix="/alunos")

# importa as rotas para ligar ao blueprint
from . import routes  # noqa
