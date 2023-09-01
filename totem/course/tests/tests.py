import pytest
from django.test import TestCase
from django.urls import reverse

from .factories import CoursePageFactory


@pytest.mark.django_db
class TestCourseListView(TestCase):
    def test_course(self):
        course = CoursePageFactory(slug="index", content="## Introduction")
        url = reverse("course:index")
        response = self.client.get(url)
        assert response.status_code == 200
        assert response.context["page"].title == course.title
        assert '<h2 id="introduction">Introduction</h2>' in response.context["page"].content_html
        assert '<a href="#introduction">' in response.context["page"].toc

    def test_script(self):
        CoursePageFactory(slug="script", content="## Introduction")
        url = reverse("course:page", kwargs={"slug": "script"})
        response = self.client.get(url)
        assert response.status_code == 200
