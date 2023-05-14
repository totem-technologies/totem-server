import pytest
from django.test import TestCase
from django.urls import reverse


@pytest.mark.django_db
class TestCourseListView(TestCase):
    fixtures = ["users.yaml", "course.yaml"]

    def test_course(self):
        url = reverse("course:list")
        response = self.client.get(url)
        assert response.status_code == 200
        assert response.context["course"].title == "My Course"
        assert '<h1 id="this-is-a-course">this is a course</h1>' in response.context["course"].content_html
        assert '<a href="#this-is-a-course">' in response.context["course"].toc
