from django.urls import path
from . import views

app_name = "blog"

urlpatterns = [
    path("<slug:slug>/", views.BlogPostDetailView.as_view(), name="detail"),
]
