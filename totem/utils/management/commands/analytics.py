from datetime import datetime, timedelta
from datetime import timezone as dttz

from django.core.management.base import BaseCommand
from django.db.models import Count, Q
from django.utils import timezone

from totem.circles.models import CircleEvent


def get_date_range(period="last_quarter"):
    now = timezone.now()

    if period == "last_quarter":
        # Calculate the start of the previous quarter
        current_quarter = (now.month - 1) // 3 + 1  # 1-4 for quarters
        previous_quarter = current_quarter - 1 if current_quarter > 1 else 4
        year = now.year if current_quarter > 1 else now.year - 1

        # Calculate first month of the quarter (Q1=1, Q2=4, Q3=7, Q4=10)
        start_month = 3 * (previous_quarter - 1) + 1

        start_date = datetime(year, start_month, 1, tzinfo=dttz.utc)
        # End date is 3 months after start date
        if start_month > 9:  # Handle year boundary for Q4
            end_date = datetime(year + 1, (start_month + 2) % 12 + 1, 1, tzinfo=dttz.utc)
        else:
            end_date = datetime(year, start_month + 3, 1, tzinfo=dttz.utc)
    elif period == "last_month":
        # First day of current month
        first_day = now.replace(day=1)
        # Last day of previous month
        start_date = (first_day - timedelta(days=1)).replace(day=1)
        end_date = first_day
    elif period == "last_week":
        start_date = now - timedelta(days=7)
        end_date = now
    else:
        try:
            start_date, end_date = period.split(",")
            start_date = datetime.strptime(start_date.strip(), "%Y-%m-%d").replace(tzinfo=dttz.utc)
            end_date = datetime.strptime(end_date.strip(), "%Y-%m-%d").replace(tzinfo=dttz.utc)
        except ValueError:
            raise ValueError("Invalid date range format. Use 'YYYY-MM-DD,YYYY-MM-DD'")

    return start_date, end_date


class Command(BaseCommand):
    help = "Generate analytics for circles and events"

    def add_arguments(self, parser):
        parser.add_argument(
            "--timeframe",
            default="last_quarter",
            help="Timeframe for analytics: last_quarter, last_month, last_week, or specific dates (YYYY-MM-DD,YYYY-MM-DD)",
        )
        parser.add_argument("--circle-slug", type=int, help="Filter by specific circle slug")
        parser.add_argument("--event-slug", type=int, help="Filter by specific event slug")
        parser.add_argument("--author-slug", type=str, help="Filter by author slug")

    def handle(self, *args, **options):
        start_date, end_date = get_date_range(options["timeframe"])

        # Base queryset filters
        event_filters = Q(start__gte=start_date) & Q(start__lte=end_date)

        # Apply additional filters if provided
        if options["circle_slug"]:
            event_filters &= Q(circle_id=options["circle_slug"])
        if options["event_slug"]:
            event_filters &= Q(id=options["event_slug"])
        if options["author_slug"]:
            event_filters &= Q(circle__author__slug=options["author_slug"])

        # Get all events in the time period
        events = CircleEvent.objects.filter(event_filters)

        # Calculate metrics
        total_events = events.count()
        events_with_attendees = events.annotate(attendee_count=Count("attendees")).filter(attendee_count__gt=1).count()
        events_no_attendees = events.annotate(attendee_count=Count("attendees")).filter(attendee_count__lt=2).count()
        events_with_joins = events.annotate(joined_count=Count("joined")).filter(joined_count__gt=1).count()
        events_no_joins = events.annotate(joined_count=Count("joined")).filter(joined_count__lt=2).count()

        total_attendees = sum([event.attendees.count() for event in events])
        total_joins = sum([event.joined.count() for event in events])

        unique_attendees = set()
        for event in events:
            unique_attendees.update(event.attendees.values_list("id", flat=True))

        unique_joins = set()
        for event in events:
            unique_joins.update(event.joined.values_list("id", flat=True))

        # Print results
        self.stdout.write("\n=== Circle Analytics ===")
        self.stdout.write(f"Period: {start_date.date()} to {end_date.date()}")
        self.stdout.write(f"Total events: {total_events}")
        self.stdout.write(f"Events with attendees: {events_with_attendees}")
        self.stdout.write(f"Events with no attendees: {events_no_attendees}")
        self.stdout.write(f"Total attendees (including duplicates): {total_attendees}")
        self.stdout.write(f"Unique attendees: {len(unique_attendees)}")
        self.stdout.write(f"Events with joins: {events_with_joins}")
        self.stdout.write(f"Events with no joins: {events_no_joins}")
        self.stdout.write(f"Total joins (including duplicates): {total_joins}")
        self.stdout.write(f"Unique joins: {len(unique_joins)}")

        # Average attendees per event (excluding events with no attendees)
        if events_with_attendees > 0:
            avg_attendees = total_attendees / events_with_attendees
            self.stdout.write(f"Average attendees per event: {avg_attendees:.1f}")

        # Most popular events
        popular_events = (
            events.annotate(attendee_count=Count("attendees"))
            .filter(attendee_count__gt=0)
            .order_by("-attendee_count")[:5]
        )

        if popular_events:
            self.stdout.write("\nTop 5 Most Popular Events:")
            for event in popular_events:
                self.stdout.write(
                    f"- {event.circle.title} [{event.slug}] ({event.start.date()}) - {event.joined.count()} joined"
                )
