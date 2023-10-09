from django.urls import path

from .views import onboard_view

app_name = "onboard"
urlpatterns = [
    path("", view=onboard_view, name="index"),
]
