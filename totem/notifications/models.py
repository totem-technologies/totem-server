from django.db import models
from totem.users.models import User


class FCMDevice(models.Model):
    """
    Model to store FCM tokens for mobile devices.
    """

    DEVICE_TYPE_IOS = "ios"
    DEVICE_TYPE_ANDROID = "android"

    DEVICE_TYPE_CHOICES = [
        (DEVICE_TYPE_IOS, "iOS"),
        (DEVICE_TYPE_ANDROID, "Android"),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="fcm_devices")
    token = models.TextField(verbose_name="FCM Registration Token")
    device_id = models.CharField(max_length=255, blank=True, null=True)
    device_type = models.CharField(max_length=50, choices=DEVICE_TYPE_CHOICES)
    active = models.BooleanField(default=True)
    last_used = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "FCM Device"
        verbose_name_plural = "FCM Devices"
        unique_together = ("token", "user")

    def __str__(self):
        return f"{self.user.username} - {self.device_type} ({self.token[:10]}...)"
