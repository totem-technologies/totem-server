import pytest
from django.test import Client
from django.urls import reverse

from totem.blog.tests.factories import BlogPostFactory
from totem.users.tests.factories import UserFactory

pytestmark = pytest.mark.django_db


class TestBlogAPI:
    def test_list_posts_unauthenticated(self):
        """
        Unauthenticated users should only see published posts in a paginated format.
        """
        # Create one published and one unpublished post
        BlogPostFactory(publish=True)
        BlogPostFactory(publish=False)

        client = Client()
        url = reverse("api-1:list_posts")
        response = client.get(url)

        assert response.status_code == 200
        data = response.json()

        # Check for pagination keys
        assert "items" in data
        assert "count" in data

        # Verify that only the published post is returned
        assert data["count"] == 1
        assert len(data["items"]) == 1


    def test_get_published_post_detail(self):
        """
        Any user should be able to retrieve a single published blog post.
        The response should use the full schema.
        """
        published_post = BlogPostFactory(publish=True, content="Test content")
        client = Client()
        url = reverse("api-1:get_post", kwargs={"slug": published_post.slug})
        response = client.get(url)

        assert response.status_code == 200
        data = response.json()

        # Verify the correct post is returned
        assert data["slug"] == published_post.slug
        assert data["title"] == published_post.title

        # Verify the full schema is used
        assert "content" in data
        assert "content_html" in data
        assert data["content_html"] == "\n<p>Test content</p>"

    def test_get_unpublished_post_fails_for_unauthenticated_user(self):
        """
        An unauthenticated user should receive a 404 error when requesting
        an unpublished post.
        """
        unpublished_post = BlogPostFactory(publish=False)
        client = Client()
        url = reverse("api-1:get_post", kwargs={"slug": unpublished_post.slug})
        response = client.get(url)

        assert response.status_code == 404

    def test_get_nonexistent_post_fails(self):
        """
        Requesting a slug that does not exist should return a 404 error.
        """
        client = Client()
        url = reverse("api-1:get_post", kwargs={"slug": "this-slug-does-not-exist"})
        response = client.get(url)
        assert response.status_code == 404