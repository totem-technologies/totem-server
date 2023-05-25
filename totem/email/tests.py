from django.core import mail
from django.test import TestCase
from django.urls import reverse

from totem.email.models import WaitList


class WaitListFlowTestCase(TestCase):
    def test_waitlist_flow(self):
        # Submit the form with name and email
        response = self.client.post(reverse("email:waitlist"), {"name": "John Doe", "email": "johndoe@example.com"})

        # Check that the response is a redirect to the email sent page
        self.assertRedirects(response, reverse("email:waitlist_sent"))

        # Check that an email was sent
        self.assertEqual(len(mail.outbox), 1)

        # Get the URL from the email
        email_body = mail.outbox[0].body
        url_start = email_body.find("http")
        url_end = email_body.find("\n", url_start)
        url = email_body[url_start:url_end]

        # get path from url
        url = url.replace("http://testserver", "")
        assert url

        # Follow the URL from the email
        response = self.client.get(url)
        print(response.content)

        # Check that the response is a redirect to the success page
        waitlist = WaitList.objects.get(email="johndoe@example.com")
        print(waitlist.subscribed)
        self.assertContains(response, "subscribed", status_code=200)

        # Check that the WaitList model was updated
        waitlist.refresh_from_db()
        self.assertTrue(waitlist.subscribed)
