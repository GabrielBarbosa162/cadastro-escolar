from flask import Blueprint
bp = Blueprint('alunos', __name__, url_prefix='/alunos')
from . import routes  # noqa
