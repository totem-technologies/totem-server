import base64
import os
from dataclasses import dataclass

from django.conf import settings
from google.auth.credentials import Credentials
from google.auth.transport.requests import Request
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.discovery_cache.base import Cache
from googleapiclient.errors import HttpError
from requests.auth import AuthBase


@dataclass
class EntryPoint:
    entryPointType: str
    uri: str
    label: str | None = None
    pin: str | None = None
    regionCode: str | None = None


@dataclass
class ConferenceSolutionKey:
    type: str


@dataclass
class ConferenceSolution:
    key: ConferenceSolutionKey
    name: str
    iconUri: str


@dataclass
class CreateRequest:
    requestId: str
    conferenceSolutionKey: ConferenceSolutionKey
    status: dict


@dataclass
class ConferenceData:
    createRequest: CreateRequest
    entryPoints: list[EntryPoint]
    conferenceSolution: ConferenceSolution
    conferenceId: str


@dataclass
class Organizer:
    email: str
    displayName: str
    self: bool


@dataclass
class Creator:
    email: str


@dataclass
class DateTimeZone:
    dateTime: str
    timeZone: str


@dataclass
class CalendarEvent:
    kind: str
    etag: str
    id: str
    status: str
    htmlLink: str
    created: str
    updated: str
    summary: str
    description: str
    creator: Creator
    organizer: Organizer
    start: DateTimeZone
    end: DateTimeZone
    iCalUID: str
    sequence: int
    hangoutLink: str
    conferenceData: ConferenceData
    reminders: dict
    eventType: str


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
cal_id = settings.GOOGLE_CALENDAR_ID
service = None


def _init(service_json=settings.GOOGLE_SERVICE_JSON):
    global credentials, service
    if credentials is None:
        SCOPES = ["https://www.googleapis.com/auth/calendar"]
        credentials = service_account.Credentials.from_service_account_info(service_json, scopes=SCOPES)
        credentials = credentials.with_subject("bo@totem.org")
        service = build("calendar", "v3", credentials=credentials, cache=MemoryCache())
    if credentials.expired or credentials.token is None:
        credentials.refresh(Request())
    return service


def get_service_client():
    service = _init()
    if service is None:
        raise Exception("Service is None")
    return service


def _to_gcal_id(s: str) -> str:
    return base64.b32hexencode(s.encode()).strip(b"=").lower().decode()


def save_event(event_id: str, start: str, end: str, summary: str, description: str) -> "CalendarEvent | None":
    if not settings.SAVE_TO_GOOGLE_CALENDAR:
        return
    service = get_service_client()
    event_id = _to_gcal_id(event_id)
    random_string = _to_gcal_id(os.urandom(10).hex())
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
        event = (
            service.events().update(eventId=event_id, calendarId=cal_id, body=event, conferenceDataVersion=1).execute()
        )
    except HttpError:
        event = service.events().insert(calendarId=cal_id, body=event, conferenceDataVersion=1).execute()
    return CalendarEvent(**event)


def delete_event(event_id: str):
    if not settings.SAVE_TO_GOOGLE_CALENDAR:
        return
    service = get_service_client()
    event_id = _to_gcal_id(event_id)
    try:
        service.events().delete(calendarId=cal_id, eventId=event_id).execute()
    except HttpError as e:
        if e.status_code == 410:
            # It's OK if the event is already deleted
            pass
        else:
            raise e
