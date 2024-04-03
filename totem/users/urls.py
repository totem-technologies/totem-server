from django.urls import path

from totem.users.views import (
    login_view,
    signup_view,
    user_dashboard_view,
    user_detail_view,
    user_feedback_view,
    user_index_view,
    user_profile_delete_view,
    user_profile_image_view,
    user_profile_view,
    user_redirect_view,
)

app_name = "users"
urlpatterns = [
    path("~redirect/", view=user_redirect_view, name="redirect"),
    path("login/", login_view, name="login"),
    path("signup/", signup_view, name="signup"),
    path("dashboard/", user_dashboard_view, name="dashboard"),
    path("profile/", user_profile_view, name="profile"),
    path("profile/delete", user_profile_delete_view, name="profile-delete"),
    path("profile/image", user_profile_image_view, name="profile-image"),
    path("feedback/", user_feedback_view, name="feedback"),
    path("", user_index_view, name="index"),
    path("u/<str:slug>/", view=user_detail_view, name="detail"),
]
