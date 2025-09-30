from flask import Blueprint

bp = Blueprint('horarios', __name__, url_prefix='/horarios')

from . import routes  # noqa
