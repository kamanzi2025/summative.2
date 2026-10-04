from typing import Any

from rest_framework.authentication import TokenAuthentication, get_authorization_header
from rest_framework.request import Request


class TokenOrBearerAuthentication(TokenAuthentication):
    """DRF token authentication that also accepts the standard `Bearer` scheme (RFC 6750).

    `Authorization: Token <key>` and `Authorization: Bearer <key>` are the same token; clients
    written for OAuth/JWT-style APIs send `Bearer`. The 401 challenge still advertises `Token`.
    """

    def authenticate(self, request: Request) -> Any:
        auth = get_authorization_header(request).split()
        if len(auth) == 2 and auth[0].lower() == b"bearer":
            try:
                key = auth[1].decode()
            except UnicodeError:
                return None
            return self.authenticate_credentials(key)
        return super().authenticate(request)
