from flask import Blueprint

bp = Blueprint("atividades", __name__, url_prefix="/atividades")
from . import routes  # noqa
