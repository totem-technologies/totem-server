import urllib.parse

from django import template
from django.conf import settings
from django.urls import reverse

register = template.Library()


@register.simple_tag(takes_context=True)
def absurl(context, view_name, *args, **kwargs):
    # Could add except for KeyError, if rendering the template
    # without a request available.
    return (
        context["request"]
        .build_absolute_uri(reverse(view_name, args=args, kwargs=kwargs))
        .replace("http://", "https://")
    )


@register.simple_tag
def sharelink(platform, path, message=""):
    """create share links for various social media platforms"""
    # support  for facebook, messanger, whatsapp, bluesky, linkedin, email, sms
    path = urllib.parse.urljoin(settings.SITE_BASE_URL, path)
    with_utm = f"{path}?utm_source={platform}"
    encoded_path = urllib.parse.quote_plus(with_utm)
    encoded_message = urllib.parse.quote_plus(message)
    encoded_both = urllib.parse.quote_plus(f"{message} {with_utm}")

    if platform == "facebook":
        return f"https://www.facebook.com/sharer/sharer.php?u={encoded_path}"
    if platform == "messenger":
        return f"https://www.facebook.com/dialog/send?link={encoded_path}"
    if platform == "whatsapp":
        return f"https://api.whatsapp.com/send?text={encoded_both}"
    if platform == "bluesky":
        return f"https://bsky.app/intent/compose?text={encoded_both}"
    if platform == "twitter":
        return f"https://twitter.com/share/?text={encoded_message}&url={encoded_path}"
    if platform == "linkedin":
        return f"https://www.linkedin.com/sharing/share-offsite/?url={encoded_path}"
    if platform == "email":
        return f"mailto:?subject={encoded_message}&body={encoded_path}"
    if platform == "sms":
        return f"sms:?body={encoded_both}"
    if platform == "link":
        return with_utm

    raise ValueError("Invalid platform")


@register.filter
def as_absurl(path):
    return urllib.parse.urljoin(settings.SITE_BASE_URL, path)
