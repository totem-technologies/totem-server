from django.apps import AppConfig


class NotificationsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "totem.notifications"

    def ready(self):
        # Initialize Firebase when Django starts
        from totem.notifications.services import initialize_firebase

        initialize_firebase()
