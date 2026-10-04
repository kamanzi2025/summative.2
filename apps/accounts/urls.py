from django.urls import path

from .views import ApiTokenView, StaffLoginView

urlpatterns = [
    path("auth/staff-login/", StaffLoginView.as_view(), name="staff-login"),
    path("auth/api-token/", ApiTokenView.as_view(), name="api-token"),
]
