from typing import Any, Dict

from django.views.generic import ListView, TemplateView

from .models import Prompt


class PromptListView(ListView):
    model = Prompt

    def get_queryset(self):
        return Prompt.objects.prefetch_related("tags")

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        json = []
        for prompt in context["object_list"]:
            json.append(
                {
                    "prompt": prompt.prompt,
                    "tags": [tag.name for tag in prompt.tags.all()],
                }
            )
        context["search_data"] = json
        return context
