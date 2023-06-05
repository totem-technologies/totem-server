from django.urls import reverse


class TestPages:
    def test_tos(self, client):
        url = reverse("pages:tos")
        response = client.get(url)
        assert response.status_code == 200

    def test_privacy(self, client):
        url = reverse("pages:privacy")
        response = client.get(url)
        assert response.status_code == 200

    def test_add(self, client):
        url = reverse("pages:about")
        response = client.get(url)
        assert response.status_code == 200

    def test_view_user(self, client):
        url = reverse("pages:how-it-works")
        response = client.get(url)
        assert response.status_code == 200

    def test_team(self, client):
        url = reverse("pages:team")
        response = client.get(url)
        assert response.status_code == 200
