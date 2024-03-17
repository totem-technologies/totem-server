import json

import requests
from django.conf import settings

from .pool import global_pool

requests_session = requests.Session()


def notify_slack(message):
    if settings.SLACK_WEBHOOK_URL is None:
        print("SLACK MESSAGE:", message)
        return
    global_pool.add_task(_notify_task, message)


def _notify_task(message):
    headers = {
        "Content-type": "application/json",
    }
    json_data = {
        "text": message,
    }
    requests_session.post(settings.SLACK_WEBHOOK_URL, headers=headers, data=json.dumps(json_data), timeout=10)
