from django.urls import path

from totem.users.views import LogInView, user_detail_view, user_index_view, user_redirect_view, user_update_view

app_name = "users"
urlpatterns = [
    path("~redirect/", view=user_redirect_view, name="redirect"),
    path("~update/", view=user_update_view, name="update"),
    path("login/", LogInView.as_view(), name="login"),
    path("", user_index_view, name="index"),
    path("<str:slug>/", view=user_detail_view, name="detail"),
]
