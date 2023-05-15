from django.urls import path

from .views import PromptListView

app_name = "repos"
urlpatterns = [
    path("prompts/", view=PromptListView.as_view(), name="prompt-list"),
]
