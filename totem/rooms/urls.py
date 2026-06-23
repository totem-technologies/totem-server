from django.urls import path
from django.views.generic import RedirectView

from .proxy import room_app_proxy

app_name = "rooms"

urlpatterns = [
    path("", RedirectView.as_view(pattern_name="pages:home", permanent=False), name="room_app"),
    path("<path:path>", room_app_proxy, name="room_app_path"),
]
