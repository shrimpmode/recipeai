"""Project-wide Django REST Framework pieces shared by every app's `api.py`."""

from django.contrib.auth.models import User
from drf_spectacular.authentication import SessionScheme
from rest_framework import authentication
from rest_framework.exceptions import NotAuthenticated
from rest_framework.request import Request


class SessionAuthentication(authentication.SessionAuthentication):
    """Django session auth that answers anonymous requests with 401, not 403.

    DRF only sends 401 when the auth class names a `WWW-Authenticate` scheme;
    stock session auth names none, so "not logged in" would look like
    "forbidden". The frontend sends people to /login on a 401
    (frontend/src/lib/api/client.ts), and 403 stays reserved for CSRF failures.
    """

    def authenticate_header(self, request: Request) -> str:
        return 'Session realm="api"'


def enforce_csrf(request: Request) -> None:
    """CSRF-check an anonymous request (raises PermissionDenied → 403).

    DRF's session auth only checks CSRF once a user is logged in; the login
    endpoint needs the check too, or another site could log a visitor into
    the attacker's account (login CSRF)."""
    SessionAuthentication().enforce_csrf(request)


def request_user(request: Request) -> User:
    """The logged-in user of a request that passed IsAuthenticated, typed as a real User."""
    user = request.user
    if not isinstance(user, User):
        raise NotAuthenticated()
    return user


class SessionAuthenticationScheme(SessionScheme):
    """Documents the subclass above as cookie session auth in the OpenAPI schema."""

    target_class = "config.rest.SessionAuthentication"
