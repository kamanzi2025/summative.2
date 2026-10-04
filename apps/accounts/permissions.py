from typing import TYPE_CHECKING

from rest_framework.permissions import SAFE_METHODS, BasePermission
from rest_framework.request import Request

from .policies import Action, can

if TYPE_CHECKING:
    # DRF imports DEFAULT_PERMISSION_CLASSES while rest_framework.views is still loading.
    from rest_framework.views import APIView


class RolePolicyPermission(BasePermission):
    """Applies ROLE_POLICIES to a view. Deny by default: a view that does not name its
    `policy_resource` is refused for everyone, so a new endpoint cannot ship open by accident.

    Safe methods (GET, HEAD, OPTIONS) need READ on the resource; anything else needs WRITE. Which
    rows the user then sees is decided by visible_to() in the view's queryset, not here.
    """

    message = "Your role does not allow this."

    def has_permission(self, request: Request, view: "APIView") -> bool:
        resource = getattr(view, "policy_resource", None)
        if resource is None:
            return False
        action = Action.READ if request.method in SAFE_METHODS else Action.WRITE
        return can(request.user, resource, action)
