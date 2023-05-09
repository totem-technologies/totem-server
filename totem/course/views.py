from django.shortcuts import render
from django.views.generic import View

from .models import Course


class CourseListView(View):
    def get(self, request):
        course = Course.objects.first()
        return render(request, "course/list.html", {"course": course})
