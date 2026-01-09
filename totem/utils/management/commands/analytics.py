from django.core.management.base import BaseCommand

from totem.utils.stats import compute_circle_event_stats, get_date_range


class Command(BaseCommand):
    help = "Generate analytics for circles and events"

    def add_arguments(self, parser):
        parser.add_argument(
            "--timeframe",
            default="last_quarter",
            help="Timeframe for analytics: all_time, last_quarter, last_month, last_week, or specific dates (YYYY-MM-DD,YYYY-MM-DD)",
        )
        parser.add_argument("--circle-slug", type=int, help="Filter by specific circle id")
        parser.add_argument("--event-slug", type=int, help="Filter by specific event id")
        parser.add_argument("--author-slug", type=str, help="Filter by author slug")

    def handle(self, *args, **options):
        date_range = get_date_range(options["timeframe"])
        stats = compute_circle_event_stats(
            date_range=date_range,
            circle_id=options["circle_slug"],
            event_id=options["event_slug"],
            author_slug=options["author_slug"],
            top_events=5,
        )

        # Print results
        self.stdout.write("\n=== Totem Analytics ===")
        self.stdout.write(f"Period: {stats.date_range.label()}")
        self.stdout.write(f"Total events: {stats.total_events}")
        self.stdout.write(f"Events with attendees: {stats.events_with_attendees}")
        self.stdout.write(f"Events with no attendees: {stats.events_no_attendees}")
        self.stdout.write(f"Total attendees (including duplicates): {stats.total_attendees}")
        self.stdout.write(f"Unique attendees: {stats.unique_attendees}")
        self.stdout.write(f"Events with joins: {stats.events_with_joins}")
        self.stdout.write(f"Events with no joins: {stats.events_no_joins}")
        self.stdout.write(f"Total joins (including duplicates): {stats.total_joins}")
        self.stdout.write(f"Unique joins: {stats.unique_joins}")

        if stats.avg_attendees_per_event is not None:
            self.stdout.write(f"Average attendees per event: {stats.avg_attendees_per_event:.1f}")
        if stats.avg_joins_per_event is not None:
            self.stdout.write(f"Average joins per event: {stats.avg_joins_per_event:.1f}")

        if stats.top_events:
            self.stdout.write("\nTop 5 Most Popular Events:")
            for event in stats.top_events:
                self.stdout.write(
                    f"- {event['circle_title']} [{event['event_slug']}] ({event['start'][:10]}) - "
                    f"{event['attendees']} attendees, {event['joined']} joined"
                )
