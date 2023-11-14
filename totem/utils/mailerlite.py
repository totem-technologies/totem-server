import typing
from dataclasses import asdict, dataclass, field
from urllib.parse import urljoin

import requests
from django.conf import settings

if typing.TYPE_CHECKING:
    from totem.users.models import User

MAILERLITE_BATCH_SIZE = 50
MAILERLITE_BASE_URL = "https://connect.mailerlite.com/"
MAILERLITE_BATCH_URL = "/api/batch"
MAILERLITE_SUBSCRIBERS_URL = "/api/subscribers"
TEST_GROUP_ID = 104854140233974821

session = requests.Session()


@dataclass
class Request:
    method: str
    path: str
    body: "InsertRequest"


@dataclass
class InsertRequest:
    """
    Parameter	Type	Required	Limitations
    email	string	yes	Valid email address as per RFC 2821
    fields	object	no	Object keys must correspond to default or custom field name. Values can only be added this way and will not be removed by omission.
    groups	array	no	array must contain existing group ids. Subscriber can only be added to groups this way and will not be removed by omission
    status	string	no	Can be one of the following: active, unsubscribed, unconfirmed, bounced, junk
    subscribed_at	string	no	Must be a valid date in the format yyyy-MM-dd HH:mm:ss
    ip_address	string	no	Must be a valid ip address
    opted_in_at	string	no	Must be a valid date in the format yyyy-MM-dd HH:mm:ss
    optin_ip	string	no	Must be a valid ip address
    unsubscribed_at	string	no	Must be a valid date in the format yyyy-MM-dd HH:mm:ss
    """

    email: str
    fields: dict | None = None
    groups: list[str] = field(default_factory=list)
    status: str | None = None
    subscribed_at: str | None = None
    ip_address: str | None = None
    opted_in_at: str | None = None
    optin_ip: str | None = None
    unsubscribed_at: str | None = None


def chunked_users(users: "list[User]", chunk_size=50):
    """
    Yields successive chunks from users.
    """
    for i in range(0, len(users), chunk_size):
        yield users[i : i + chunk_size]


def create_batch_request(chunk):
    """
    Creates a batch request for a chunk of users.
    """
    batch_data = []
    groups = []
    status = None
    prepend = ""
    if settings.SENTRY_ENVIRONMENT != "production":
        groups.append(TEST_GROUP_ID)
        status = "unsubscribed"
        prepend = "totemtest-"
    for user in chunk:
        batch_data.append(
            Request(
                method="POST",
                path=MAILERLITE_SUBSCRIBERS_URL,
                body=InsertRequest(
                    email=f"{prepend}{user.email}",
                    fields={"name": user.name},
                    groups=groups,
                    status=status,
                ),
            )
        )
    return batch_data


def send_batch_request(api_key, batch_data):
    """
    Sends a batch request to MailerLite.
    """
    url = urljoin(MAILERLITE_BASE_URL, MAILERLITE_BATCH_URL)
    dict_batch = [asdict(request) for request in batch_data]
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
    response = session.post(url, headers=headers, json={"requests": dict_batch})
    return response.json()


def upload_users_to_mailerlite_batch(users: "list[User]", api_key=settings.MAILERLITE_API_KEY):
    """
    Uploads users to MailerLite using batch operation with chunks.
    """
    if not api_key:
        raise Exception("MailerLite API key not set.")
    errors = []
    for chunk in chunked_users(users):
        batch_data = create_batch_request(chunk)
        responses = send_batch_request(api_key, batch_data)
        for response in responses.get("responses", []):
            if response.get("code", 400) > 299:
                print("Failed to add user.")
                print(response)
                errors.append(response)
    if errors:
        raise Exception(f"Failed to add users to MailerLite: {errors}")
