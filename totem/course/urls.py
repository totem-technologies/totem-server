from django.urls import path

from . import views

app_name = "courses"

urlpatterns = [
    path("", views.CoursePageView.as_view(), name="index"),
    path("<slug:slug>", views.CoursePageView.as_view(), name="page"),
]
