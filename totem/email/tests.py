from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase
from django.urls import reverse

from totem.email.models import SubscribedModel

User = get_user_model()


class SubscribeTestCase(TestCase):
    fixtures = ["users.yaml"]

    def test_subscribe(self):
        user = User.objects.get(pk=1)
        subscribed = SubscribedModel.objects.create(user=user)
        assert subscribed.subscribed is False
        subscribed.subscribe()
        assert subscribed.subscribed is True
        subscribed.unsubscribe()
        assert subscribed.subscribed is False

    def test_subscribe_email(self):
        user = User.objects.get(pk=1)
        subscribed = SubscribedModel.objects.create(user=user)
        subscribed.send_subscribe_email()
        assert len(mail.outbox) == 1


# class WaitListFlowTestCase(TestCase):
#     def test_waitlist_flow(self):
#         # Submit the form with name and email
#         response = self.client.post(reverse("email:waitlist"), {"name": "John Doe", "email": "johndoe@example.com"})

#         # Check that the response is a redirect to the email sent page
#         self.assertRedirects(response, reverse("email:waitlist_survey"))

#         # Check that an email was sent
#         self.assertEqual(len(mail.outbox), 1)

#         # Check that we can resend the email
#         response = self.client.post(reverse("email:waitlist"), {"name": "Jane Doe", "email": "johndoe@example.com"})
#         print(response.content)
#         self.assertRedirects(response, reverse("email:waitlist_survey"))
#         self.assertEqual(len(mail.outbox), 2)

#         # Get the URL from the email
#         email_body = mail.outbox[1].body
#         url_start = email_body.find("http")
#         url_end = email_body.find("\n", url_start)
#         url = email_body[url_start:url_end]

#         # get path from url
#         url = url.replace("http://testserver", "")
#         assert url

#         # Follow the URL from the email
#         response = self.client.get(url)

#         # Check that the response is a redirect to the success page
#         waitlist = WaitList.objects.get(email="johndoe@example.com")
#         assert waitlist.name == "John Doe"
#         self.assertContains(response, "subscribed", status_code=200)

#         # Check that the WaitList model was updated
#         waitlist.refresh_from_db()
#         self.assertTrue(waitlist.subscribed)

#         # Now unsubscribe
#         response = self.client.get(reverse("email:unsubscribe", kwargs={"id": waitlist.id}))
#         self.assertContains(response, "unsubscribed", status_code=200)

#         # Check that the WaitList model was updated
#         waitlist.refresh_from_db()
#         self.assertFalse(waitlist.subscribed)
