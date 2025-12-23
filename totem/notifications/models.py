from django.db import models

from totem.users.models import User


class FCMDevice(models.Model):
    """
    Model to store FCM tokens for mobile devices.
    """

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="fcm_devices")
    token = models.TextField(verbose_name="FCM Registration Token")
    active = models.BooleanField(default=True)
    last_used = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "FCM Device"
        verbose_name_plural = "FCM Devices"
        unique_together = ("token", "user")

    def __str__(self):
        return f"{self.user.email} - ({self.token[:10]}...)"
