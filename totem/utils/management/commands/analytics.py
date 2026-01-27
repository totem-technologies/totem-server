from django.core.management.base import BaseCommand

from totem.utils.stats import compute_session_stats, get_date_range


class Command(BaseCommand):
    help = "Generate analytics for spaces and sessions"

    def add_arguments(self, parser):
        parser.add_argument(
            "--timeframe",
            default="last_quarter",
            help="Timeframe for analytics: all_time, last_quarter, last_month, last_week, or specific dates (YYYY-MM-DD,YYYY-MM-DD)",
        )
        parser.add_argument("--space-slug", type=int, help="Filter by specific space id")
        parser.add_argument("--event-slug", type=int, help="Filter by specific event id")
        parser.add_argument("--author-slug", type=str, help="Filter by author slug")

    def handle(self, *args, **options):
        date_range = get_date_range(options["timeframe"])
        stats = compute_session_stats(
            date_range=date_range,
            space_id=options["space_slug"],
            event_id=options["event_slug"],
            author_slug=options["author_slug"],
            top_events=5,
        )

        # Print results
        self.stdout.write("\n=== Totem Analytics ===")
        self.stdout.write(f"Period: {stats.date_range.label()}")
        self.stdout.write(f"Total sessions: {stats.total_events}")
        self.stdout.write(f"Sessions with attendees: {stats.events_with_attendees}")
        self.stdout.write(f"Sessions with no attendees: {stats.events_no_attendees}")
        self.stdout.write(f"Total attendees (including duplicates): {stats.total_attendees}")
        self.stdout.write(f"Unique attendees: {stats.unique_attendees}")
        self.stdout.write(f"Sessions with joins: {stats.events_with_joins}")
        self.stdout.write(f"Sessions with no joins: {stats.events_no_joins}")
        self.stdout.write(f"Total joins (including duplicates): {stats.total_joins}")
        self.stdout.write(f"Unique joins: {stats.unique_joins}")

        if stats.avg_attendees_per_event is not None:
            self.stdout.write(f"Average attendees per session: {stats.avg_attendees_per_event:.1f}")
        if stats.avg_joins_per_event is not None:
            self.stdout.write(f"Average joins per session: {stats.avg_joins_per_event:.1f}")

        if stats.top_events:
            self.stdout.write("\nTop 5 Most Popular Sessions:")
            for session in stats.top_events:
                self.stdout.write(
                    f"- {session['space_title']} [{session['event_slug']}] ({session['start'][:10]}) - "
                    f"{session['attendees']} attendees, {session['joined']} joined"
                )
