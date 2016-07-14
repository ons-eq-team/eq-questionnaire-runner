from flask import request
from flask_login import current_user
from app.main import main_blueprint
from ua_parser import user_agent_parser
from app.metadata.metadata_store import MetaDataStore
from app.libs.utils import convert_tx_id
from flask.ext.themes2 import render_theme_template
import logging

logger = logging.getLogger(__name__)


@main_blueprint.app_errorhandler(200)
def index(error=None):
    if error:
        logger.error(error)
    return _render_error_page(200)


@main_blueprint.app_errorhandler(400)
def bad_request(error=None):
    if error:
        logger.error(error)
    return _render_error_page(400)


@main_blueprint.app_errorhandler(401)
def unauthorized(error=None):
    if error:
        logger.error(error)
    return _render_error_page(401)


@main_blueprint.app_errorhandler(403)
def forbidden(error=None):
    if error:
        logger.error(error)
    return _render_error_page(403)


@main_blueprint.app_errorhandler(404)
def page_not_found(error=None):
    if error:
        logger.error(error)
    return _render_error_page(404)


@main_blueprint.app_errorhandler(500)
def internal_server_error(error=None):
    if error:
        logger.error(error)
    return _render_error_page(500)


@main_blueprint.app_errorhandler(503)
def service_unavailable(error=None):
    if error:
        logger.error(error)
    return _render_error_page(503)


def _render_error_page(status_code):
    tx_id = None
    metadata = MetaDataStore.get_instance(current_user)
    if metadata:
        tx_id = convert_tx_id(metadata.tx_id)
    user_agent = user_agent_parser.Parse(request.headers.get('User-Agent', ''))
    return render_theme_template('default', 'errors/error.html',
                                 status_code=status_code,
                                 ua=user_agent, tx_id=tx_id), status_code
