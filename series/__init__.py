from flask import Blueprint

bp = Blueprint('series', __name__, url_prefix='/series')

from . import routes  # noqa
