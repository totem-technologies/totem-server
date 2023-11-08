import json

import requests
from django.conf import settings

from .pool import ThreadPool

requests_session = requests.Session()
pool = ThreadPool()


def notify_slack(message):
    if settings.SLACK_WEBHOOK_URL is None:
        return
    pool.add_task(_notify_task, message)


def _notify_task(message):
    headers = {
        "Content-type": "application/json",
    }
    json_data = {
        "text": message,
    }
    requests_session.post(settings.SLACK_WEBHOOK_URL, headers=headers, data=json.dumps(json_data), timeout=10)
