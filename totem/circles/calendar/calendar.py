import json

import caldav
import googleapiclient.discovery
from django.conf import settings
from google.auth.transport.requests import Request
from google.oauth2 import service_account
from requests.auth import AuthBase


class OAuth(AuthBase):
    def __init__(self, credentials):
        self.credentials = credentials

    def __call__(self, r):
        self.credentials.apply(r.headers)
        return r


SCOPES = ["https://www.googleapis.com/auth/calendar"]
calid = settings.GOOGLE_CALENDAR_ID
caldavurl = "https://apidata.googleusercontent.com/caldav/v2/" + calid + "/events"
credentials = service_account.Credentials.from_service_account_info(settings.GOOGLE_SERVICE_JSON, scopes=SCOPES)
service = googleapiclient.discovery.build("calendar", "v3", credentials=credentials)
client = caldav.DAVClient(caldavurl, auth=OAuth(credentials))

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


def get_calendar_event(id: str):
    events_result = service.events().get(calendarId=calid, eventId="51h15rb48o1ighm3rn79dn6vhi").execute()


def get_event_ical(event_id: str):
    if credentials.expired or credentials.token is None:
        credentials.refresh(Request())
    calendar = client.principal().calendars()[0]
    event = calendar.event(event_id)
    return event.data
