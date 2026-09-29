from django.urls import path

from .views import PriceScheduleView

urlpatterns = [
    path("price-schedule/", PriceScheduleView.as_view(), name="price-schedule"),
]
