from django.core.mail import EmailMessage


def decoded_email_text(email: EmailMessage) -> str:
    """Every text part of an email, decoded.

    Asserting substrings against the raw MIME message (str(email.message()))
    is flaky: quoted-printable encoding soft-wraps lines at 76 chars, so a
    URL can be split mid-word depending on the surrounding content length.
    """
    parts: list[str] = []
    for part in email.message().walk():
        if part.get_content_maintype() != "text":
            continue
        payload = part.get_payload(decode=True)
        if payload:
            parts.append(payload.decode(part.get_content_charset() or "utf-8"))
    return "\n".join(parts)
