from flask import Blueprint

bp = Blueprint("escolas", __name__, url_prefix="/escolas")
from . import routes  # noqa
