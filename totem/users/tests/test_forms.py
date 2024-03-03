"""
Module for all Form Tests.
"""

from django.contrib.messages import get_messages
from django.test import TestCase
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from totem.users.forms import UserAdminCreationForm
from totem.users.models import Feedback, User
from totem.users.tests.factories import UserFactory
from totem.users.views import FeedbackForm


class TestUserAdminCreationForm:
    """
    Test class for all tests related to the UserAdminCreationForm
    """

    def test_username_validation_error_msg(self, user: User):
        """
        Tests UserAdminCreation Form's unique validator functions correctly by testing:
            1) A new user with an existing username cannot be added.
            2) Only 1 error is raised by the UserCreation Form
            3) The desired error message is raised
        """

        # The user already exists,
        # hence cannot be created.
        form = UserAdminCreationForm(
            {
                "email": user.email,
                "password1": user.password,
                "password2": user.password,
            }
        )

        assert not form.is_valid()
        assert len(form.errors) == 1
        assert "email" in form.errors
        assert form.errors["email"][0] == _("This email has already been taken.")


class TestUserFeedbackView(TestCase):
    def test_feedback_form_display(self):
        response = self.client.get(reverse("users:feedback"))
        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(response.context["form"], FeedbackForm)

    def test_feedback_form_submission_authenticated(self):
        user = UserFactory()
        self.client.force_login(user)
        response = self.client.post(
            reverse("users:feedback"),
            data={
                "message": "value2",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Feedback.objects.count(), 1)
        feedback = Feedback.objects.first()
        assert feedback
        self.assertEqual(feedback.user, user)
        self.assertEqual(feedback.email, None)
        self.assertEqual(feedback.message, "value2")
        messages = list(get_messages(response.wsgi_request))
        self.assertEqual(len(messages), 1)
        self.assertEqual(str(messages[0]), "Feedback successfully submitted. Thank you!")

    def test_feedback_form_submission_unauthenticated(self):
        response = self.client.post(
            reverse("users:feedback"),
            data={
                "email": "dfgsdg@sdfjsd.com",
                "message": "value3",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Feedback.objects.count(), 1)
        feedback = Feedback.objects.first()
        assert feedback
        self.assertIsNone(feedback.user)
        self.assertEqual(feedback.email, "dfgsdg@sdfjsd.com")
        self.assertEqual(feedback.message, "value3")
        messages = list(get_messages(response.wsgi_request))
        self.assertEqual(len(messages), 1)
        self.assertEqual(str(messages[0]), "Feedback successfully submitted. Thank you!")
