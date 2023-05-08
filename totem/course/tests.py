from django.test import TestCase
from django.urls import reverse
import pytest


@pytest.mark.django_db
class TestCourseListView(TestCase):
    fixtures = ["users.yaml", "course.yaml"]

    def test_course(self):
        url = reverse("course:list")
        response = self.client.get(url)
        assert response.status_code == 200
        assert response.context["course"].title == "My Course"
