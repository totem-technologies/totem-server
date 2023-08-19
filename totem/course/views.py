from typing import Any

from django.views.generic import TemplateView

from .models import CoursePage


class CoursePageView(TemplateView):
    template_name = "course/page.html"

    def get_context_data(self, slug="index", **kwargs: Any) -> dict[str, Any]:
        ctx = super().get_context_data(**kwargs)
        ctx["page"] = CoursePage.objects.get(slug=slug)
        return ctx
