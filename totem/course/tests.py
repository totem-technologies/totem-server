import pytest
from django.test import TestCase
from django.urls import reverse


@pytest.mark.django_db
class TestCourseListView(TestCase):
    fixtures = ["users.yaml", "course.yaml"]

    def test_course(self):
        url = reverse("course:index")
        response = self.client.get(url)
        assert response.status_code == 200
        assert response.context["page"].title == "Keeper Guide"
        assert '<h2 id="introduction">Introduction</h2>' in response.context["page"].content_html
        assert '<a href="#introduction">' in response.context["page"].toc

    def test_script(self):
        url = reverse("course:page", kwargs={"slug": "script"})
        response = self.client.get(url)
        assert response.status_code == 200
