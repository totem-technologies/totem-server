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
            top_sessions=5,
        )

        # Print results
        self.stdout.write("\n=== Totem Analytics ===")
        self.stdout.write(f"Period: {stats.date_range.label()}")
        self.stdout.write(f"Total sessions: {stats.total_sessions}")
        self.stdout.write(f"Sessions with signups: {stats.sessions_with_signups}")
        self.stdout.write(f"Sessions with no signups: {stats.sessions_no_signups}")
        self.stdout.write(f"Total signups (including duplicates): {stats.total_signups}")
        self.stdout.write(f"Unique signups: {stats.unique_signups}")
        self.stdout.write(f"Sessions with participants: {stats.sessions_with_participants}")
        self.stdout.write(f"Sessions with no participants: {stats.sessions_no_participants}")
        self.stdout.write(f"Total participants (including duplicates): {stats.total_participants}")
        self.stdout.write(f"Unique participants: {stats.unique_participants}")

        if stats.avg_signups_per_session is not None:
            self.stdout.write(f"Average signups per session: {stats.avg_signups_per_session:.1f}")
        if stats.avg_participants_per_session is not None:
            self.stdout.write(f"Average participants per session: {stats.avg_participants_per_session:.1f}")

        if stats.top_sessions:
            self.stdout.write("\nTop 5 Most Popular Sessions:")
            for s in stats.top_sessions:
                self.stdout.write(
                    f"- {s['space_title']} [{s['session_slug']}] ({s['start'][:10]}) - "
                    f"{s['signups']} signups, {s['participants']} participants"
                )
