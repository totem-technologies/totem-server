from typing import Any, Dict

from django.shortcuts import render
from django.views.generic import TemplateView, View

from .models import CircleScript, Course


class CourseListView(View):
    def get(self, request):
        course = Course.objects.first()
        return render(request, "course/list.html", {"course": course})


class CircleScriptView(TemplateView):
    template_name = "course/script.html"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        ctx = super().get_context_data(**kwargs)
        ctx["script"] = CircleScript.objects.first()
        return ctx
