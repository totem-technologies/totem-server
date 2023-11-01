import base64
import os

import caldav
from django.conf import settings
from google.auth.credentials import Credentials
from google.auth.transport.requests import Request
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.discovery_cache.base import Cache
from googleapiclient.errors import HttpError
from requests.auth import AuthBase


class OAuth(AuthBase):
    def __init__(self, credentials):
        self.credentials = credentials

    def __call__(self, r):
        self.credentials.apply(r.headers)
        return r


class MemoryCache(Cache):
    _CACHE = {}

    def get(self, url):
        return MemoryCache._CACHE.get(url)

    def set(self, url, content):
        MemoryCache._CACHE[url] = content


credentials: Credentials | None = None
client: caldav.DAVClient | None = None
service = None


def _init(calendar_id=settings.GOOGLE_CALENDAR_ID, service_json=settings.GOOGLE_SERVICE_JSON):
    global credentials, client, service
    if credentials is None:
        SCOPES = ["https://www.googleapis.com/auth/calendar"]
        caldavurl = f"https://apidata.googleusercontent.com/caldav/v2/{calendar_id}/events"
        credentials = service_account.Credentials.from_service_account_info(service_json, scopes=SCOPES)
        credentials = credentials.with_subject("bo@totem.org")
        client = caldav.DAVClient(caldavurl, auth=OAuth(credentials))
        service = build("calendar", "v3", credentials=credentials, cache=MemoryCache())
    if credentials.expired or credentials.token is None:
        credentials.refresh(Request())
    return client, service


def get_caldev_client():
    client, _ = _init()
    if client is None:
        raise Exception("Client is None")
    return client


def get_service_client():
    _, service = _init()
    if service is None:
        raise Exception("Service is None")
    return service


# # events_result = service.events().list(calendarId=CAL_ID, singleEvents=True).execute()
# events_result = service.events().get(calendarId=calid, eventId="51h15rb48o1ighm3rn79dn6vhi").execute()
# print(events_result)
# for event in events_result["items"]:
#     print(event)
#     print()
# # print(events_result)
# events = events_result.get("items", [])
# event_id = events[0]["id"]
# event = events[0]
# # service.events().update(
# #     calendarId=CAL_ID, eventId=event_id,
# #     body={"end":{"date":"2023-07-15"},"start":{"date":"2023-07-15"},"summary":"Kilroy was here?","extendedProperties": {
# #     "private": {
# #       "petsAllowed": "yes"
# #     }
# #   }
# #  }).execute()


# def get_calendar_event(id: str):
#     events_result = service.events().get(calendarId=calid, eventId="51h15rb48o1ighm3rn79dn6vhi").execute()


def get_event_ical(event_id: str):
    client = get_caldev_client()
    calendar = client.principal().calendars()[0]
    event = calendar.event(event_id)
    return event.data


def save_event(event_id: str, start: str, end: str, summary: str, description: str):
    service = get_service_client()
    cal_id = settings.GOOGLE_CALENDAR_ID
    event_id = base64.b32hexencode(event_id.encode()).strip(b"=").lower().decode()
    random_string = base64.b32hexencode(os.urandom(10)).strip(b"=").lower().decode()
    event = {
        "id": event_id,
        "summary": summary,
        "description": description,
        "start": {
            "dateTime": start,
            "timeZone": "America/Los_Angeles",
        },
        "end": {
            "dateTime": end,
            "timeZone": "America/Los_Angeles",
        },
        "conferenceData": {
            "createRequest": {
                "requestId": random_string,
                "conferenceSolutionKey": {"type": "hangoutsMeet"},
            },
        },
    }
    try:
        event = service.events().update(eventId=event_id, calendarId=cal_id, body=event).execute()
    except HttpError:
        event = service.events().insert(calendarId=cal_id, body=event, conferenceDataVersion=1).execute()
    return event
