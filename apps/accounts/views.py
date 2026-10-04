"""Login endpoints. They only prove who the caller is (authentication). What that user may then
see is decided per request by apps/accounts/policies.py (authorization), so any valid user can
log in here, including one with no role profile."""

from django.contrib.auth import login
from django.contrib.auth.models import User
from drf_spectacular.utils import OpenApiResponse, extend_schema, inline_serializer
from rest_framework import serializers
from rest_framework.authtoken.models import Token
from rest_framework.authtoken.serializers import AuthTokenSerializer
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

TokenResponse = inline_serializer("AuthToken", {"token": serializers.CharField()})
LOGIN_SCHEMA = extend_schema(
    request=AuthTokenSerializer,
    responses={200: TokenResponse, 400: OpenApiResponse(description="Wrong username or password.")},
)


class _CredentialsView(APIView):
    # No authentication on the login views themselves: a stale cookie or a bad Authorization
    # header must not stop someone from logging in again.
    authentication_classes: list = []
    permission_classes = [AllowAny]

    def authenticated_user(self, request: Request) -> User:
        serializer = AuthTokenSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        return serializer.validated_data["user"]


class StaffLoginView(_CredentialsView):
    """Staff in the browser: starts a Django session (cookie) and also returns the user's token."""

    @LOGIN_SCHEMA
    def post(self, request: Request) -> Response:
        user = self.authenticated_user(request)
        login(request._request, user)
        token, _ = Token.objects.get_or_create(user=user)
        return Response({"token": token.key})


class ApiTokenView(_CredentialsView):
    """System integrations: exchange credentials for a token sent as `Authorization: Token <key>`.
    No session is created."""

    @LOGIN_SCHEMA
    def post(self, request: Request) -> Response:
        user = self.authenticated_user(request)
        token, _ = Token.objects.get_or_create(user=user)
        return Response({"token": token.key})
