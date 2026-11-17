from auditlog.context import disable_auditlog
from auditlog.models import LogEntry
from django.conf import settings
from django.db import transaction
from django.db.models import PROTECT, ProtectedError

from .models import User

ACCOUNT_NOT_DELETABLE_MESSAGE = (
    "Keeper accounts, and accounts that created Spaces, circle plans, course pages or prompts, "
    "can't be deleted here. "
    f"Please email {settings.EMAIL_SUPPORT_ADDRESS} and we'll take care of it."
)


def can_delete_account(user: User) -> bool:
    """Whether the user may delete their own account, or has to go through staff.

    Keepers can't, and neither can anyone who owns content that must outlive them:
    every on_delete=PROTECT relation to the user (spaces, plans, course pages, prompts).
    """
    if user.is_keeper():
        return False
    return not any(
        rel.related_model._base_manager.filter(**{rel.field.name: user}).exists()
        for rel in User._meta.related_objects
        if rel.on_delete is PROTECT
    )


def delete_account(user: User) -> bool:
    """Delete a user's own account. Returns False if it has to go through staff."""
    if not can_delete_account(user):
        return False
    try:
        with transaction.atomic():
            # A single entry recording the deletion, instead of one per cascaded row.
            LogEntry.objects.log_create(user, force_log=True, action=LogEntry.Action.DELETE)
            with disable_auditlog():
                user.delete()
    except ProtectedError:
        # Protected content assigned to the user after the check above.
        return False
    return True
