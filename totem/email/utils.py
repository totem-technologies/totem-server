import re
from collections.abc import Iterator

import lxml.html
from anymail.exceptions import AnymailRecipientsRefused
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.mail import send_mail as django_send_mail

from totem.email.data import EMAIL_BLOCKLIST
from totem.email.exceptions import EmailBounced

# MJML elements with nothing to say in plain text: the head (styles, title,
# inbox preview), raw HTML, images, icons, and layout spacing.
_TEXT_SKIP = {"mj-head", "mj-raw", "mj-image", "mj-social", "mj-spacer", "mj-divider"}
_TEXT_BLOCKS = {"p", "div", "ul", "ol", "table", "tr", "blockquote", "h1", "h2", "h3", "h4", "h5", "h6"}


def mjml_to_text(mjml: str) -> str:
    """Plain-text version of an email, read from its MJML source rather than the
    rendered HTML, which is layout tables, hidden elements, and duplicate logos."""
    blocks = _text_blocks(lxml.html.fromstring(mjml))
    lines = (" ".join(line.split()) for line in "\n\n".join(blocks).split("\n"))
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def _text_blocks(el: lxml.html.HtmlElement) -> Iterator[str]:
    if not isinstance(el.tag, str) or el.tag in _TEXT_SKIP:
        return
    if el.tag == "mj-text":
        yield _inline_text(el)
    elif el.tag == "mj-button":
        yield f"{_inline_text(el).strip()}: {el.get('href')}"
    else:
        for child in el:
            yield from _text_blocks(child)


def _inline_text(el: lxml.html.HtmlElement) -> str:
    """Text of an element's HTML content, with "\\n" for line breaks. Source
    whitespace collapses the way a browser would collapse it."""
    parts = [_collapse(el.text)]
    for child in el:
        if isinstance(child.tag, str):
            parts.append(_inline_child(child))
        parts.append(_collapse(child.tail))
    return "".join(parts)


def _inline_child(el: lxml.html.HtmlElement) -> str:
    if el.tag == "br":
        return "\n"
    if el.tag == "img":
        return ""
    text = _inline_text(el)
    if el.tag == "a":
        text = text.strip()
        href = el.get("href", "")
        if not text or text == href.removeprefix("mailto:"):
            return text
        return f"{text} ({href})"
    if el.tag == "li":
        return f"\n- {text.strip()}"
    if el.tag in _TEXT_BLOCKS:
        return f"\n\n{text}\n\n"
    return text


def _collapse(text: str | None) -> str:
    return re.sub(r"\s+", " ", text or "")


def send_mail(
    subject: str,
    html_message: str,
    text_message: str,
    recipient_list: list[str],
    from_email: str = settings.DEFAULT_FROM_EMAIL,
) -> int:
    # remove newlines from subject
    subject = subject.replace("\n", " ")
    try:
        return django_send_mail(
            subject=subject,
            message=text_message,
            from_email=from_email,
            recipient_list=recipient_list,
            html_message=html_message,
        )
    except AnymailRecipientsRefused:
        raise EmailBounced(f"Email to {recipient_list} with subject {subject} was blocked.")


def validate_email_blocked(value):
    for blocked in EMAIL_BLOCKLIST:
        if blocked in value:
            raise ValidationError("Sorry, but your email address is not allowed.")
