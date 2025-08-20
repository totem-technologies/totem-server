import pytest
from django.test import Client
from django.urls import reverse

from totem.blog.tests.factories import BlogPostFactory
from totem.users.models import User
from totem.api.auth import generate_jwt_token


@pytest.mark.django_db
class TestBlogAPI:
    def test_list_posts(self, client: Client, auth_token):
        """
        Users should only see published posts in a paginated format.
        """
        # Create one published and one unpublished post
        BlogPostFactory(publish=True)
        BlogPostFactory(publish=False)

        url = reverse("mobile-api:list_posts")
        response = client.get(url, headers={"Authorization": f"Bearer {auth_token}"})

        assert response.status_code == 200
        data = response.json()

        # Check for pagination keys
        assert "items" in data
        assert "count" in data

        # Verify that only the published post is returned
        assert data["count"] == 1
        assert len(data["items"]) == 1

    def test_get_published_post_detail(self, client: Client, auth_token):
        """
        An user should be able to retrieve a single published blog post.
        The response should use the full schema.
        """
        content = "Test content"
        published_post = BlogPostFactory(publish=True, content=content)
        url = reverse("mobile-api:get_post", kwargs={"slug": published_post.slug})
        response = client.get(url, headers={"Authorization": f"Bearer {auth_token}"})

        assert response.status_code == 200
        data = response.json()

        # Verify the correct post is returned
        assert data["slug"] == published_post.slug
        assert data["title"] == published_post.title
        assert data["read_time"]

        # Verify the full schema is used
        # assert "content" in data
        assert "content_html" in data
        assert content in data["content_html"]
        assert data["content_html"] == "\n<p>Test content</p>"

    def test_get_unpublished_post_fails(self, client: Client, auth_token):
        """
        An user should receive a 404 error when requesting an unpublished post.
        """
        unpublished_post = BlogPostFactory(publish=False)
        url = reverse("mobile-api:get_post", kwargs={"slug": unpublished_post.slug})
        response = client.get(url, headers={"Authorization": f"Bearer {auth_token}"})

        assert response.status_code == 404

    def test_get_unpublished_post_as_staff(self, client: Client, auth_user: User):
        """
        An user should receive a 404 error when requesting an unpublished post.
        """
        auth_user.is_staff = True
        auth_user.save()
        token = generate_jwt_token(auth_user)
        unpublished_post = BlogPostFactory(publish=False)
        url = reverse("mobile-api:get_post", kwargs={"slug": unpublished_post.slug})
        response = client.get(url, headers={"Authorization": f"Bearer {token}"})

        assert response.status_code == 200
        data = response.json()
        assert "content_html" in data

    def test_get_nonexistent_post_fails(self, client: Client, auth_token):
        """
        Requesting a slug that does not exist should return a 404 error.
        """
        url = reverse("mobile-api:get_post", kwargs={"slug": "this-slug-does-not-exist"})
        response = client.get(url, headers={"Authorization": f"Bearer {auth_token}"})
        assert response.status_code == 404
