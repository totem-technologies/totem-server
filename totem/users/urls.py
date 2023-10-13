from django.urls import path

from totem.users.views import (
    LogInView,
    user_dashboard_view,
    user_detail_view,
    user_index_view,
    user_profile_delete_view,
    user_profile_image_view,
    user_profile_view,
    user_redirect_view,
    user_update_view,
)

app_name = "users"
urlpatterns = [
    path("~redirect/", view=user_redirect_view, name="redirect"),
    path("~update/", view=user_update_view, name="update"),
    path("login/", LogInView.as_view(), name="login"),
    path("dashboard/", user_dashboard_view, name="dashboard"),
    path("profile/", user_profile_view, name="profile"),
    path("profile/delete", user_profile_delete_view, name="profile-delete"),
    path("profile/image", user_profile_image_view, name="profile-image"),
    path("", user_index_view, name="index"),
    path("u/<str:slug>/", view=user_detail_view, name="detail"),
]
