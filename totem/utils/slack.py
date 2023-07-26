import json

import requests
from django.conf import settings


def notify_slack(message):
    if settings.SLACK_WEBHOOK_URL is None:
        return

    headers = {
        "Content-type": "application/json",
    }

    json_data = {
        "text": message,
    }

    requests.post(settings.SLACK_WEBHOOK_URL, headers=headers, data=json.dumps(json_data), timeout=10)
