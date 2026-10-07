"""Session authentication and nutrition goals for the Next.js frontend.

The frontend reaches these through its same-origin `/api` rewrite, so the
browser holds Django's own `sessionid` and `csrftoken` cookies and no CORS or
token scheme is needed (see docs/adr/0003)."""

from typing import Annotated

from django.contrib.auth import authenticate, login, logout
from django.middleware.csrf import get_token
from ninja import Field, Router, Schema
from ninja.security import django_auth
from ninja.utils import check_csrf

from accounts.models import Profile

auth_router = Router(tags=["auth"])
profile_router = Router(tags=["profile"], auth=django_auth)


class Credentials(Schema):
    username: Annotated[str, Field(min_length=1, max_length=150)]
    password: Annotated[str, Field(min_length=1, max_length=256)]


class Me(Schema):
    username: str
    is_staff: bool


class Message(Schema):
    detail: str


def _me(user) -> Me:
    # `is_staff` comes from AbstractUser, not AbstractBaseUser (what authenticate() is typed to return).
    return Me(username=user.get_username(), is_staff=bool(getattr(user, "is_staff", False)))


@auth_router.get("/csrf", response={204: None})
def csrf(request):
    """Sets the `csrftoken` cookie; call once before the first unsafe request."""
    get_token(request)
    return 204, None


@auth_router.post("/login", response={200: Me, 401: Message, 403: Message})
def login_view(request, credentials: Credentials):
    # Unauthenticated endpoints skip ninja's CSRF check; login needs it anyway (login CSRF).
    if check_csrf(request) is not None:
        return 403, {"detail": "CSRF verification failed."}
    user = authenticate(request, username=credentials.username, password=credentials.password)
    if user is None:
        return 401, {"detail": "Invalid username or password."}
    login(request, user)
    return 200, _me(user)


@auth_router.post("/logout", auth=django_auth, response={204: None})
def logout_view(request):
    logout(request)
    return 204, None


@auth_router.get("/me", auth=django_auth, response=Me)
def me(request):
    return _me(request.user)


# Daily targets; the bounds only reject typos and nonsense, not unusual diets.
Target = Annotated[float | None, Field(default=None, ge=0, le=20_000)]


class Goals(Schema):
    daily_calorie_target: Target
    protein_target_g: Target
    carbs_target_g: Target
    fat_target_g: Target
    fiber_target_g: Target


@profile_router.get("", response=Goals)
def get_goals(request):
    profile, _ = Profile.objects.get_or_create(user=request.user)
    return profile


@profile_router.put("", response=Goals)
def update_goals(request, goals: Goals):
    profile, _ = Profile.objects.get_or_create(user=request.user)
    for field, value in goals.dict().items():
        setattr(profile, field, value)
    profile.save()
    return profile
