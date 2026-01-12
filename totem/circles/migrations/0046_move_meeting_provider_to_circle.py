from django.db import migrations, models


def copy_meeting_provider_to_circle(apps, schema_editor):
    Circle = apps.get_model("circles", "Circle")
    CircleEvent = apps.get_model("circles", "CircleEvent")

    for circle in Circle.objects.all():
        event = (
            CircleEvent.objects.filter(circle_id=circle.id)
            .order_by("-start")
            .only("meeting_provider")
            .first()
        )
        if event:
            circle.meeting_provider = event.meeting_provider
            circle.save(update_fields=["meeting_provider"])


def copy_meeting_provider_to_events(apps, schema_editor):
    Circle = apps.get_model("circles", "Circle")
    CircleEvent = apps.get_model("circles", "CircleEvent")

    for circle in Circle.objects.all().only("id", "meeting_provider"):
        CircleEvent.objects.filter(circle_id=circle.id).update(meeting_provider=circle.meeting_provider)


class Migration(migrations.Migration):
    dependencies = [
        ("circles", "0045_sessionfeedback"),
    ]

    operations = [
        migrations.AddField(
            model_name="circle",
            name="meeting_provider",
            field=models.CharField(
                choices=[("google_meet", "Google Meet"), ("livekit", "LiveKit")],
                default="google_meet",
                help_text="The video conferencing provider for this circle.",
                max_length=20,
            ),
        ),
        migrations.RunPython(copy_meeting_provider_to_circle, copy_meeting_provider_to_events),
        migrations.RemoveField(
            model_name="circleevent",
            name="meeting_provider",
        ),
    ]
