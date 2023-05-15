from typing import Any, Dict

from django.views.generic import ListView, TemplateView

from .models import Prompt


class PromptListView(ListView):
    model = Prompt

    def get_queryset(self):
        return Prompt.objects.prefetch_related("tags")
