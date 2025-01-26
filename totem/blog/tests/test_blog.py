from django.test import TestCase
from django.urls import reverse
from django.core.exceptions import ValidationError
from datetime import timedelta

from totem.users.tests.factories import UserFactory
from .factories import BlogPostFactory

class BlogPostModelTests(TestCase):
    def test_default_publish_status(self):
        post = BlogPostFactory()
        self.assertFalse(post.publish)
    
    def test_string_representation(self):
        post = BlogPostFactory(title="Test Post")
        self.assertEqual(str(post), "Test Post")

    def test_get_absolute_url(self):
        post = BlogPostFactory()
        self.assertEqual(
            post.get_absolute_url(),
            f"/blog/{post.slug}/"
        )

    def test_markdown_validation(self):
        post = BlogPostFactory(content="# Invalid H1")
        with self.assertRaises(ValidationError):
            post.full_clean()

class BlogViewTests(TestCase):
    def setUp(self):
        self.staff = UserFactory(is_staff=True)
        self.user = UserFactory()
        self.published_post = BlogPostFactory(publish=True)
        self.unpublished_post = BlogPostFactory(publish=False)

    def test_list_view_staff(self):
        self.client.force_login(self.staff)
        response = self.client.get(reverse("blog:list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.published_post.title)
        self.assertContains(response, self.unpublished_post.title)

    def test_list_view_regular_user(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("blog:list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.published_post.title)
        self.assertNotContains(response, self.unpublished_post.title)

    def test_detail_view_staff(self):
        self.client.force_login(self.staff)
        response = self.client.get(self.unpublished_post.get_absolute_url())
        self.assertEqual(response.status_code, 200)

    def test_detail_view_regular_user(self):
        self.client.force_login(self.user)
        response = self.client.get(self.unpublished_post.get_absolute_url())
        self.assertEqual(response.status_code, 404)

    def test_ordering(self):
        older_post = BlogPostFactory(date_published=self.published_post.date_published - timedelta(days=1))
        response = self.client.get(reverse("blog:list"))
        posts = response.context["posts"]
        self.assertEqual(posts[0], self.published_post)
        self.assertEqual(posts[1], older_post)
