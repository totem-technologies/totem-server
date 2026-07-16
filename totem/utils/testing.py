from django.core.mail import EmailMessage, EmailMultiAlternatives


def email_text(email: EmailMessage) -> str:
    """The email's authored text: plain body plus alternatives (e.g. HTML).

    Assert against this rather than str(email.message()): the serialized
    MIME form is quoted-printable encoded, which soft-wraps lines at 76
    chars and can split a URL mid-word depending on surrounding content.
    """
    parts = [email.body]
    if isinstance(email, EmailMultiAlternatives):
        parts += [str(alternative.content) for alternative in email.alternatives]
    return "\n".join(parts)
