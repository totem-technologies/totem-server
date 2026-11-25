from typing import Any

from django.core.management.base import BaseCommand

from totem.rooms.admission.permissions import reconcile_session_permissions


class Command(BaseCommand):
    help = "Reconcile server-owned Session admission permissions with LiveKit."

    def handle(self, *args: Any, **options: Any) -> None:
        count = reconcile_session_permissions()
        self.stdout.write(f"Checked {count} admission permission records.")
