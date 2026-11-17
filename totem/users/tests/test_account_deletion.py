import pytest
from auditlog.models import LogEntry
from django.contrib.contenttypes.models import ContentType
from django.contrib.messages import get_messages
from django.db.models import ProtectedError
from django.test import Client
from django.urls import reverse

from totem.blog.tests.factories import BlogPostFactory
from totem.course.tests.factories import CoursePageFactory
from totem.plans.models import CirclePlan
from totem.repos.models import Prompt
from totem.spaces.models import Space
from totem.spaces.tests.factories import SessionFactory, SpaceFactory
from totem.users.account import can_delete_account
from totem.users.models import User
from totem.users.tests.factories import KeeperProfileFactory, UserFactory

pytestmark = pytest.mark.django_db


class TestKeepersCannotDeleteTheirAccount:
    def test_web(self, client: Client):
        user = KeeperProfileFactory().user
        client.force_login(user)
        response = client.post(reverse("users:profile-delete"))
        assert response.status_code == 302
        assert response.url == reverse("users:profile")
        assert User.objects.filter(pk=user.pk).exists()
        assert any("help@totem.org" in str(m) for m in get_messages(response.wsgi_request))

    def test_mobile(self, client_with_user: tuple[Client, User]):
        client, user = client_with_user
        KeeperProfileFactory(user=user)
        response = client.delete(reverse("mobile-api:user_delete"))
        assert response.status_code == 403
        assert "help@totem.org" in response.json()["detail"]
        assert User.objects.filter(pk=user.pk).exists()

    def test_profile_page_hides_delete_form(self, client: Client):
        user = KeeperProfileFactory().user
        client.force_login(user)
        content = client.get(reverse("users:profile")).content.decode()
        assert reverse("users:profile-delete") not in content

    def test_profile_page_shows_delete_form_to_members(self, client: Client):
        client.force_login(UserFactory())
        content = client.get(reverse("users:profile")).content.decode()
        assert reverse("users:profile-delete") in content


class TestDeletingAUserWhoOwnsContent:
    def test_space_author_is_protected(self):
        space = SpaceFactory()
        SessionFactory(space=space)
        with pytest.raises(ProtectedError):
            space.author.delete()
        assert Space.objects.filter(pk=space.pk).exists()

    @pytest.mark.parametrize(
        "make_content",
        [
            lambda user: CirclePlan.objects.create(name="p", description="d", content="c", created_by=user),
            lambda user: CoursePageFactory(created_by=user, slug="t"),
            lambda user: Prompt.objects.create(prompt="p", created_by=user),
        ],
        ids=["circle_plan", "course_page", "prompt"],
    )
    def test_staff_content_is_protected(self, make_content):
        user = UserFactory(is_staff=True)
        make_content(user)
        with pytest.raises(ProtectedError):
            user.delete()

    def test_web_delete_refuses_instead_of_erroring(self, client: Client):
        # A space author without a keeper profile still can't take their spaces with them.
        user = SpaceFactory().author
        client.force_login(user)
        response = client.post(reverse("users:profile-delete"))
        assert response.status_code == 302
        assert response.url == reverse("users:profile")
        assert User.objects.filter(pk=user.pk).exists()

    def test_mobile_delete_refuses_instead_of_erroring(self, client_with_user: tuple[Client, User]):
        client, user = client_with_user
        SpaceFactory(author=user)
        response = client.delete(reverse("mobile-api:user_delete"))
        assert response.status_code == 403
        assert User.objects.filter(pk=user.pk).exists()

    def test_blog_author_can_delete_and_post_is_kept(self, client: Client):
        post = BlogPostFactory()
        author = post.author
        client.force_login(author)
        response = client.post(reverse("users:profile-delete"))
        assert response.status_code == 302
        assert response.url == reverse("pages:home")
        assert not User.objects.filter(pk=author.pk).exists()
        post.refresh_from_db()
        assert post.author is None


class TestDeletionAuditLog:
    def test_successful_deletion_logs_one_entry(self, client: Client):
        user = UserFactory()
        client.force_login(user)
        client.post(reverse("users:profile-delete"))
        assert not User.objects.filter(pk=user.pk).exists()
        entries = LogEntry.objects.filter(
            content_type=ContentType.objects.get_for_model(User), object_pk=str(user.pk), action=LogEntry.Action.DELETE
        )
        assert entries.count() == 1

    def test_refused_deletion_logs_nothing(self, client: Client):
        user = SpaceFactory().author
        client.force_login(user)
        client.post(reverse("users:profile-delete"))
        assert not LogEntry.objects.filter(
            content_type=ContentType.objects.get_for_model(User), action=LogEntry.Action.DELETE
        ).exists()


class TestProfilePageMatchesDeletionRules:
    @pytest.mark.parametrize(
        "make_owner",
        [
            lambda: SpaceFactory().author,
            lambda: CirclePlan.objects.create(name="p", description="d", content="c", created_by=UserFactory()).created_by,
            lambda: Prompt.objects.create(prompt="p", created_by=UserFactory()).created_by,
        ],
        ids=["space_author", "circle_plan", "prompt"],
    )
    def test_owners_of_protected_content_do_not_see_the_delete_form(self, client: Client, make_owner):
        user = make_owner()
        assert not can_delete_account(user)
        client.force_login(user)
        content = client.get(reverse("users:profile")).content.decode()
        assert reverse("users:profile-delete") not in content

    def test_members_can_delete(self):
        assert can_delete_account(UserFactory())

    def test_keepers_cannot_delete(self):
        assert not can_delete_account(KeeperProfileFactory().user)
