import re
from pathlib import Path
from zoneinfo import ZoneInfoNotFoundError

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from totem.reporting.export import write_metric_csv
from totem.reporting.metrics import session_metrics
from totem.reporting.periods import ReportPeriod
from totem.reporting.types import ReportFilters

QUARTER_PATTERN = re.compile(r"(?P<year>\d{4})-Q(?P<quarter>[1-4])")


class Command(BaseCommand):
    help = "Export aggregate, database-backed analytics as CSV"

    def add_arguments(self, parser):
        period = parser.add_mutually_exclusive_group(required=True)
        period.add_argument("--year", type=int, help="Calendar year, for example 2025")
        period.add_argument("--quarter", help="Calendar quarter in YYYY-QN form, for example 2026-Q2")
        parser.add_argument(
            "--timezone",
            required=True,
            help="IANA timezone used for calendar boundaries, for example America/Los_Angeles",
        )
        parser.add_argument("--session", action="append", default=[], help="Session slug; may be repeated")
        parser.add_argument("--space", action="append", default=[], help="Space slug; may be repeated")
        parser.add_argument("--keeper", action="append", default=[], help="Keeper slug; may be repeated")
        parser.add_argument("--category", action="append", default=[], help="Category slug; may be repeated")
        parser.add_argument("--output", type=Path, help="Write CSV to this path instead of stdout")

    def handle(self, *args, **options):
        period = self._period(options)
        filters = ReportFilters(
            session_slugs=tuple(options["session"]),
            space_slugs=tuple(options["space"]),
            keeper_slugs=tuple(options["keeper"]),
            category_slugs=tuple(options["category"]),
        )
        metrics = session_metrics(period=period, as_of=timezone.now(), filters=filters)

        output_path = options["output"]
        if output_path is None:
            write_metric_csv(metrics, self.stdout)
            return

        try:
            with output_path.open("w", encoding="utf-8", newline="") as stream:
                write_metric_csv(metrics, stream)
        except OSError as exc:
            raise CommandError(f"Could not write CSV to {output_path}: {exc}") from exc
        self.stdout.write(self.style.SUCCESS(f"Analytics exported to {output_path}"))

    def _period(self, options) -> ReportPeriod:
        reporting_timezone = options["timezone"]
        try:
            if options["year"] is not None:
                return ReportPeriod.calendar_year(options["year"], reporting_timezone)

            match = QUARTER_PATTERN.fullmatch(options["quarter"])
            if match is None:
                raise CommandError("Quarter must use YYYY-QN format, with N between 1 and 4")
            return ReportPeriod.calendar_quarter(
                int(match.group("year")),
                int(match.group("quarter")),
                reporting_timezone,
            )
        except ZoneInfoNotFoundError as exc:
            raise CommandError(f"Unknown timezone: {reporting_timezone}") from exc
