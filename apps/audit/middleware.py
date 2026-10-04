"""Write one AuditLog row for every request to a view that names a ROLE_POLICIES resource.

Middleware rather than a view mixin, so no protected view can forget to log: whatever has a
`policy_resource` is audited, including requests refused with 401, 403 or 404. Public views
(status, price schedule, login) have no resource and are not logged.
"""

from collections.abc import Callable
from typing import Any

from django.http import HttpRequest, HttpResponse

from apps.accounts.policies import policy_for, profile_for

from .models import AuditLog


def policy_resource_of(request: HttpRequest) -> str | None:
    match = request.resolver_match
    view_class = getattr(match.func, "cls", None) if match else None
    resource = getattr(view_class, "policy_resource", None)
    return str(resource) if resource else None


def returned_ids(data: Any, kwargs: dict[str, Any]) -> list[int]:
    """Ids of the records in the response (a page, or one record); else the record in the URL."""
    rows = data.get("results", [data]) if isinstance(data, dict) else data if isinstance(data, list) else []
    ids = [row["id"] for row in rows if isinstance(row, dict) and isinstance(row.get("id"), int)]
    if not ids and str(kwargs.get("pk", "")).isdigit():
        ids = [int(kwargs["pk"])]
    return ids


class AuditLogMiddleware:
    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        response = self.get_response(request)
        resource = policy_resource_of(request)
        if resource is not None:
            self.record(request, response, resource)
        return response

    def record(self, request: HttpRequest, response: HttpResponse, resource: str) -> None:
        # DRF copies the user it authenticated (session or token) onto the Django request.
        user = getattr(request, "user", None)
        authenticated = bool(user is not None and user.is_authenticated)
        profile = profile_for(user)
        policy = policy_for(user)
        match = request.resolver_match
        # Not wrapped in try/except: if the trail cannot be written, the request fails (500)
        # rather than serving data that leaves no record.
        AuditLog.objects.create(
            user=user if authenticated else None,
            username=user.get_username() if authenticated and user is not None else "",
            role=profile.role if profile else "",
            method=request.method or "",
            path=request.path[:255],
            endpoint=(match.view_name if match else "")[:100],
            status_code=response.status_code,
            resource=resource,
            object_ids=returned_ids(getattr(response, "data", None), match.kwargs if match else {}),
            coordinate_precision=policy.coordinates.value if policy else "",
            national_id=policy.national_id.value if policy else "",
            commercial_terms=policy.commercial_terms if policy else None,
        )
