"""
Keeper Metrics Report - Rolling 90 Day Analysis

Generates performance metrics for Keepers including:
- Sessions hosted
- Spaces hosted
- Participant sign-ups (total and unique)
- Attendance (total and unique)
- Attendance rate
- Keeper hours with participants present
- Average participants per session
- Repeat attendance indicator
"""

import csv
from collections import defaultdict
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db.models import Q
from django.utils import timezone

from totem.spaces.models import CircleEvent
from totem.users.models import User


class Command(BaseCommand):
    help = "Generate keeper metrics report for the last 90 days"

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=int,
            default=90,
            help="Number of days to look back (default: 90)",
        )
        parser.add_argument(
            "--keeper",
            type=str,
            help="Filter by specific keeper email or slug",
        )
        parser.add_argument(
            "--output",
            type=str,
            help="Output CSV file path (default: stdout)",
        )

    def handle(self, *args, **options):
        days = options["days"]
        keeper_filter = options.get("keeper")
        output_file = options.get("output")

        # Fixed date range for consistency
        end_date = timezone.now()
        start_date = end_date - timedelta(days=days)

        self.stdout.write(
            self.style.NOTICE(f"Generating metrics for {days} days: {start_date.date()} to {end_date.date()}")
        )

        # Get all keepers (users who have authored spaces)
        keepers = User.objects.filter(created_spaces__isnull=False).distinct()

        if keeper_filter:
            keepers = keepers.filter(Q(email__icontains=keeper_filter) | Q(slug__icontains=keeper_filter))

        if not keepers.exists():
            self.stdout.write(self.style.WARNING("No keepers found"))
            return

        metrics_data = []

        for keeper in keepers:
            metrics = self.calculate_keeper_metrics(keeper, start_date, end_date)
            if metrics["sessions_hosted"] > 0:  # Only include keepers with activity
                metrics_data.append(metrics)

        # Sort by sessions hosted descending
        metrics_data.sort(key=lambda x: x["sessions_hosted"], reverse=True)

        # Output results
        if output_file:
            self.write_csv(metrics_data, output_file)
            self.stdout.write(self.style.SUCCESS(f"Report saved to {output_file}"))
        else:
            self.print_report(metrics_data, start_date, end_date)

    def calculate_keeper_metrics(self, keeper: User, start_date, end_date) -> dict:
        """Calculate all metrics for a single keeper."""

        # Get all completed (not cancelled, ended) sessions for this keeper
        # A session is "completed" if it has ended and wasn't cancelled
        sessions = (
            CircleEvent.objects.filter(
                space__author=keeper,
                start__gte=start_date,
                start__lte=end_date,
                cancelled=False,
            )
            .filter(
                # Session has ended (start + duration is in the past)
                start__lte=timezone.now() - timedelta(minutes=1)
            )
            .prefetch_related("attendees", "joined", "circle")
        )

        # Filter to only truly completed sessions (ended)
        completed_sessions = [s for s in sessions if s.start + timedelta(minutes=s.duration_minutes) <= timezone.now()]

        # 1. Sessions Hosted
        sessions_hosted = len(completed_sessions)

        # 2. Spaces Hosted (unique)
        spaces_hosted = len(set(s.circle_id for s in completed_sessions))

        # 3a. Total Sign-Ups
        total_signups = sum(s.attendees.count() for s in completed_sessions)

        # 3b. Unique Participants Signed Up
        all_signup_user_ids = set()
        for s in completed_sessions:
            all_signup_user_ids.update(s.attendees.values_list("id", flat=True))
        unique_signups = len(all_signup_user_ids)

        # 4a. Total Attended Seats
        total_attended = sum(s.joined.count() for s in completed_sessions)

        # 4b. Unique Attendees
        all_joined_user_ids = set()
        for s in completed_sessions:
            all_joined_user_ids.update(s.joined.values_list("id", flat=True))
        unique_attendees = len(all_joined_user_ids)

        # 5. Attendance Rate
        attendance_rate = (total_attended / total_signups * 100) if total_signups > 0 else 0

        # 6. Keeper Hours With Participants Present
        hours_with_participants = 0
        for s in completed_sessions:
            if s.joined.count() >= 1:
                hours_with_participants += s.duration_minutes / 60

        # 7. Average Participants per Session
        avg_participants = total_attended / sessions_hosted if sessions_hosted > 0 else 0

        # 8. Repeat Attendance Indicator
        # Count participants who attended more than one session with this keeper
        participant_session_counts = defaultdict(int)
        for s in completed_sessions:
            for user_id in s.joined.values_list("id", flat=True):
                participant_session_counts[user_id] += 1

        repeat_attendees = sum(1 for count in participant_session_counts.values() if count > 1)

        return {
            "keeper_name": keeper.name or keeper.email,
            "keeper_email": keeper.email,
            "keeper_slug": keeper.slug,
            "sessions_hosted": sessions_hosted,
            "spaces_hosted": spaces_hosted,
            "total_signups": total_signups,
            "unique_signups": unique_signups,
            "total_attended": total_attended,
            "unique_attendees": unique_attendees,
            "attendance_rate": round(attendance_rate, 1),
            "hours_with_participants": round(hours_with_participants, 1),
            "avg_participants_per_session": round(avg_participants, 2),
            "repeat_attendees": repeat_attendees,
        }

    def print_report(self, metrics_data: list, start_date, end_date):
        """Print a formatted report to stdout."""
        self.stdout.write("\n" + "=" * 80)
        self.stdout.write("KEEPER METRICS REPORT")
        self.stdout.write(f"Period: {start_date.date()} to {end_date.date()}")
        self.stdout.write("=" * 80 + "\n")

        for m in metrics_data:
            self.stdout.write(f"\n{m['keeper_name']} ({m['keeper_email']})")
            self.stdout.write("-" * 60)
            self.stdout.write(f"  Sessions Hosted:              {m['sessions_hosted']}")
            self.stdout.write(f"  Spaces Hosted:                {m['spaces_hosted']}")
            self.stdout.write(f"  Total Sign-Ups:               {m['total_signups']}")
            self.stdout.write(f"  Unique Participants:          {m['unique_signups']}")
            self.stdout.write(f"  Total Attended Seats:         {m['total_attended']}")
            self.stdout.write(f"  Unique Attendees:             {m['unique_attendees']}")
            self.stdout.write(f"  Attendance Rate:              {m['attendance_rate']}%")
            self.stdout.write(f"  Hours w/ Participants:        {m['hours_with_participants']} hrs")
            self.stdout.write(f"  Avg Participants/Session:     {m['avg_participants_per_session']}")
            self.stdout.write(f"  Repeat Attendees:             {m['repeat_attendees']}")

        self.stdout.write("\n" + "=" * 80)
        self.stdout.write(f"Total Keepers with Activity: {len(metrics_data)}")
        self.stdout.write("=" * 80 + "\n")

    def write_csv(self, metrics_data: list, filepath: str):
        """Write metrics to a CSV file."""
        fieldnames = [
            "keeper_name",
            "keeper_email",
            "keeper_slug",
            "sessions_hosted",
            "spaces_hosted",
            "total_signups",
            "unique_signups",
            "total_attended",
            "unique_attendees",
            "attendance_rate",
            "hours_with_participants",
            "avg_participants_per_session",
            "repeat_attendees",
        ]

        with open(filepath, "w", newline="") as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(metrics_data)
