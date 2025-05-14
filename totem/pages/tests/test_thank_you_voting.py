from django.urls import reverse


class TestThankYouVotingPage:
    """Tests for the Thank You Voting page."""

    def test_thank_you_voting_page_loads(self, client):
        """Test that the thank you voting page loads successfully."""
        url = reverse("pages:thank-you-voting")
        response = client.get(url)
        assert response.status_code == 200

    def test_thank_you_voting_page_content(self, client):
        """Test that the thank you voting page contains expected content."""
        url = reverse("pages:thank-you-voting")
        response = client.get(url)

        # Check that the response contains the expected content
        content = response.content.decode("utf-8")
        assert "Thank You for Voting" in content
        assert "Your vote has been recorded" in content
        assert "Your voice matters" in content

        # Check that the page contains the return home button
        assert "Return Home" in content
        assert reverse("pages:home") in content

    def test_noindex(self, client):
        """Test that the thank you voting page is not indexed by search engines."""
        url = reverse("pages:thank-you-voting")
        response = client.get(url)
        assert "noindex" in response.content.decode("utf-8")
