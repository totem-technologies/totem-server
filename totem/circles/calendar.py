import json

import googleapiclient.discovery
from django.conf import settings
from google.oauth2 import service_account

SCOPES = ["https://www.googleapis.com/auth/calendar"]
SERVICE_ACCOUNT_FILE = "service.json"
CAL_ID = "c_ddf4458b375a1d28389aee93ed234ac1b51ee98ed37d09a8a22509a950bac115@group.calendar.google.com"

credentials = service_account.Credentials.from_service_account_info(settings.GOOGLE_SERVICE_JSON, scopes=SCOPES)
service = googleapiclient.discovery.build("calendar", "v3", credentials=credentials)

# events_result = service.events().list(calendarId=CAL_ID, singleEvents=True).execute()
events_result = service.events().get(calendarId=CAL_ID, eventId="51h15rb48o1ighm3rn79dn6vhi").execute()
print(events_result)
for event in events_result["items"]:
    print(event)
    print()
# print(events_result)
events = events_result.get("items", [])
event_id = events[0]["id"]
event = events[0]
# service.events().update(
#     calendarId=CAL_ID, eventId=event_id,
#     body={"end":{"date":"2023-07-15"},"start":{"date":"2023-07-15"},"summary":"Kilroy was here?","extendedProperties": {
#     "private": {
#       "petsAllowed": "yes"
#     }
#   }
#  }).execute()
