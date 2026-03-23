from django.test import TestCase, override_settings


class TestAppleAppSiteAssociation(TestCase):
    def test_returns_valid_json(self):
        response = self.client.get("/.well-known/apple-app-site-association")
        assert response.status_code == 200
        data = response.json()
        assert "applinks" in data
        assert data["applinks"]["apps"] == []
        details = data["applinks"]["details"]
        assert len(details) == 1
        assert details[0]["appID"] == "LNLXP4VK97.org.totem.ios"
        assert "/spaces/*" in details[0]["paths"]

    @override_settings(IOS_TEAM_ID="TESTTEAM", IOS_BUNDLE_ID="org.totem.ios.dev")
    def test_uses_settings(self):
        response = self.client.get("/.well-known/apple-app-site-association")
        data = response.json()
        assert data["applinks"]["details"][0]["appID"] == "TESTTEAM.org.totem.ios.dev"


class TestAssetLinks(TestCase):
    def test_returns_valid_json(self):
        response = self.client.get("/.well-known/assetlinks.json")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 1
        target = data[0]["target"]
        assert target["namespace"] == "android_app"
        assert target["package_name"] == "org.totem.app"

    @override_settings(ANDROID_PACKAGE_NAME="org.totem.app.dev", ANDROID_CERT_FINGERPRINT="AA:BB:CC")
    def test_uses_settings(self):
        response = self.client.get("/.well-known/assetlinks.json")
        data = response.json()
        target = data[0]["target"]
        assert target["package_name"] == "org.totem.app.dev"
        assert target["sha256_cert_fingerprints"] == ["AA:BB:CC"]
