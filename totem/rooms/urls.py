from django.urls import path

from .proxy import room_app_proxy

app_name = "rooms"

urlpatterns = [
    path("", room_app_proxy, name="room_app"),
    path("<path:path>", room_app_proxy, name="room_app_path"),
]
