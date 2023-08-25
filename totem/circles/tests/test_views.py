from django.urls import reverse


class TestCircleListView:
    def test_list(self, client, db):
        url = reverse("circles:list")
        response = client.get(url)
        assert response.status_code == 200
