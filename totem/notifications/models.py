from django.db import models

from totem.users.models import User


class FCMDevice(models.Model):
    """Store a Firebase Installation ID for a mobile device."""

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="fcm_devices")
    fid = models.CharField(max_length=512, unique=True, verbose_name="Firebase Installation ID")
    active = models.BooleanField(default=True)
    last_used = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "FCM Device"
        verbose_name_plural = "FCM Devices"

    def __str__(self) -> str:
        return f"FCM device {self.pk}"
