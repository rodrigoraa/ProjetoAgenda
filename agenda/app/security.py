import secrets

from flask import request, session
from werkzeug.exceptions import BadRequest


CSRF_SESSION_KEY = "_csrf_token"
UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


class CSRFValidationError(BadRequest):
    description = "O token de segurança da sessão expirou ou é inválido."


def get_csrf_token():
    token = session.get(CSRF_SESSION_KEY)
    if not token:
        token = secrets.token_urlsafe(32)
        session[CSRF_SESSION_KEY] = token
    return token


def validate_csrf():
    if request.method not in UNSAFE_METHODS:
        return

    expected = session.get(CSRF_SESSION_KEY)
    provided = (
        request.headers.get("X-CSRFToken")
        or request.headers.get("X-CSRF-Token")
        or request.form.get("_csrf_token")
    )

    if not expected or not provided or not secrets.compare_digest(expected, provided):
        # O próximo GET recebe um token novo. A ação solicitada continua
        # bloqueada, sem reaproveitar um token potencialmente obsoleto.
        session.pop(CSRF_SESSION_KEY, None)
        raise CSRFValidationError()
