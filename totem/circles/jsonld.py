from typing import TYPE_CHECKING

from django.templatetags.static import static

if TYPE_CHECKING:
    from totem.circles.models import CircleEvent
from totem.utils.utils import full_url

# example jsonld:
# {
#       "@context": "https://schema.org",
#       "@type": "Event",
#       "name": "The Adventures of Kira and Morrison",
#       "startDate": "2025-07-21T19:00:00-05:00",
#       "endDate": "2025-07-21T23:00-05:00",
#       "eventStatus": "https://schema.org/EventScheduled",
#       "eventAttendanceMode": "https://schema.org/OnlineEventAttendanceMode",
#       "location": {
#         "@type": "VirtualLocation",
#         "url": "https://operaonline.stream5.com/"
#         },
#       "image": [
#         "https://example.com/photos/1x1/photo.jpg",
#         "https://example.com/photos/4x3/photo.jpg",
#         "https://example.com/photos/16x9/photo.jpg"
#        ],
#       "description": "The Adventures of Kira and Morrison is coming to Snickertown in a can't miss performance.",
#       "offers": {
#         "@type": "Offer",
#         "url": "https://www.example.com/event_offer/12345_202403180430",
#         "price": 30,
#         "priceCurrency": "USD",
#         "availability": "https://schema.org/InStock",
#         "validFrom": "2024-05-21T12:00"
#       },
#       "performer": {
#         "@type": "PerformingGroup",
#         "name": "Kira and Morrison"
#       },
#       "organizer": {
#         "@type": "Organization",
#         "name": "Kira and Morrison Music",
#         "url": "https://kiraandmorrisonmusic.com"
#       }
#     }


def _event_status(event: "CircleEvent"):
    if event.cancelled:
        return "https://schema.org/EventCancelled"
    return "https://schema.org/EventScheduled"


def _availability(event: "CircleEvent"):
    if event.can_attend(silent=True):
        return "https://schema.org/InStock"
    return "https://schema.org/SoldOut"


def create_jsonld(event: "CircleEvent"):
    # Create a JSON-LD object for a online virtual event
    title = event.title or event.circle.title
    description = event.content_text or event.circle.content_text
    url = full_url(event.get_absolute_url())
    jsonld = {
        "@context": "https://schema.org",
        "@type": "Event",
        "name": title,
        "startDate": event.start.isoformat(),
        "endDate": event.end().isoformat(),
        "eventStatus": _event_status(event),
        "eventAttendanceMode": "https://schema.org/OnlineEventAttendanceMode",
        "location": {
            "@type": "VirtualLocation",
            "url": url,
        },
        "description": description,
        "offers": {
            "@type": "Offer",
            "url": url,
            "price": event.circle.price,
            "priceCurrency": "USD",
            "availability": _availability(event),
        },
        "performer": {
            "@type": "Person",
            "name": event.circle.author.name,
        },
        "organizer": {
            "@type": "Organization",
            "name": "Totem",
            "url": "https://www.totem.org",
        },
    }

    if event.circle.image:
        jsonld["image"] = [full_url(event.circle.image.url)]
    else:
        jsonld["image"] = [full_url(static("images/ogimage.jpg"))]
    return jsonld
