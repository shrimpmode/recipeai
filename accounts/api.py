"""Session authentication and nutrition goals for the Next.js frontend.

The frontend reaches these through its same-origin `/api` rewrite, so the
browser holds Django's own `sessionid` and `csrftoken` cookies and no CORS or
token scheme is needed (see docs/adr/0003, docs/adr/0004)."""

from django.contrib.auth import authenticate, login, logout
from django.middleware.csrf import get_token
from django.urls import path
from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import Profile
from config.rest import enforce_csrf, request_user


class CredentialsSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=150)
    password = serializers.CharField(max_length=256, trim_whitespace=False)


class MeSerializer(serializers.Serializer):
    username = serializers.CharField()
    is_staff = serializers.BooleanField()


class MessageSerializer(serializers.Serializer):
    detail = serializers.CharField()


# Daily targets; the bounds only reject typos and nonsense, not unusual diets.
_TARGET = {"min_value": 0, "max_value": 20_000, "allow_null": True, "default": None}


class GoalsSerializer(serializers.ModelSerializer):
    """PUT replaces every goal: a field left out is cleared (default None)."""

    class Meta:
        model = Profile
        fields = ["daily_calorie_target", "protein_target_g", "carbs_target_g", "fat_target_g", "fiber_target_g"]
        extra_kwargs = dict.fromkeys(fields, _TARGET)


def _me(user) -> dict:
    # `is_staff` comes from AbstractUser, not AbstractBaseUser (what authenticate() is typed to return).
    return MeSerializer({"username": user.get_username(), "is_staff": bool(getattr(user, "is_staff", False))}).data


class CsrfView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(operation_id="auth_csrf", responses={204: None})
    def get(self, request: Request) -> Response:
        """Sets the `csrftoken` cookie; call once before the first unsafe request."""
        get_token(request._request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class LoginView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        operation_id="auth_login",
        request=CredentialsSerializer,
        responses={200: MeSerializer, 400: None, 401: MessageSerializer, 403: MessageSerializer},
    )
    def post(self, request: Request) -> Response:
        enforce_csrf(request)
        credentials = CredentialsSerializer(data=request.data)
        credentials.is_valid(raise_exception=True)
        user = authenticate(request._request, **credentials.validated_data)
        if user is None:
            return Response({"detail": "Invalid username or password."}, status=status.HTTP_401_UNAUTHORIZED)
        login(request._request, user)
        return Response(_me(user))


class LogoutView(APIView):
    @extend_schema(operation_id="auth_logout", request=None, responses={204: None})
    def post(self, request: Request) -> Response:
        logout(request._request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeView(APIView):
    @extend_schema(operation_id="auth_me", responses=MeSerializer)
    def get(self, request: Request) -> Response:
        return Response(_me(request.user))


class GoalsView(APIView):
    def _profile(self, request: Request) -> Profile:
        profile, _ = Profile.objects.get_or_create(user=request_user(request))
        return profile

    @extend_schema(operation_id="profile_get_goals", responses=GoalsSerializer)
    def get(self, request: Request) -> Response:
        return Response(GoalsSerializer(self._profile(request)).data)

    @extend_schema(operation_id="profile_update_goals", request=GoalsSerializer, responses=GoalsSerializer)
    def put(self, request: Request) -> Response:
        goals = GoalsSerializer(self._profile(request), data=request.data)
        goals.is_valid(raise_exception=True)
        goals.save()
        return Response(goals.data)


auth_urls = [
    path("csrf", CsrfView.as_view()),
    path("login", LoginView.as_view()),
    path("logout", LogoutView.as_view()),
    path("me", MeView.as_view()),
]
