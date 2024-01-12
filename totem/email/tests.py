# import pytest
# from django.contrib.auth import get_user_model
# from django.core import mail
# from django.core.exceptions import ValidationError
# from django.test import TestCase

# from totem.email.models import SubscribedModel
# from totem.users.tests.factories import UserFactory

# from .utils import validate_email_blocked

# User = get_user_model()


# # class SubscribeTestCase(TestCase):
# #     def test_subscribe(self):
# #         user = UserFactory()
# #         subscribed = SubscribedModel.objects.create(user=user)
# #         assert subscribed.subscribed is False
# #         subscribed.subscribe()
# #         assert subscribed.subscribed is True
# #         subscribed.unsubscribe()
# #         assert subscribed.subscribed is False

# #     def test_subscribe_email(self):
# #         user = UserFactory()
# #         subscribed = SubscribedModel.objects.create(user=user)
# #         subscribed.send_subscribe_email()
# #         assert len(mail.outbox) == 1


# # def test_validate_email_blocked():
# #     assert validate_email_blocked("example@domain.com") is None
# #     assert validate_email_blocked("test@domain.com") is None
# #     assert validate_email_blocked("user@domain.com") is None
# #     with pytest.raises(ValidationError):
# #         validate_email_blocked("test@data-backup-store.com")
