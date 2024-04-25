from totem.users.models import User
from totem.utils.templatetags.avatar import avatar


class TestAvatar:
    def test_avatar(self, db):
        user = User.objects.create(name="Test User")
        tpl = avatar(user)
        assert tpl["name"] == "Test User"
        assert tpl["size"] == 120
        assert tpl["padding"] == "0.12rem"
        assert tpl["seed"] == user.profile_avatar_seed
        assert tpl["type"] == "TD"
        assert "src" not in tpl
