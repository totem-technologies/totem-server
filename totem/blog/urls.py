from django.urls import path
from . import views

app_name = "blog"

urlpatterns = [
    path("", views.BlogPostListView.as_view(), name="list"),
    path("<slug:slug>/", views.BlogPostDetailView.as_view(), name="detail"),
]
