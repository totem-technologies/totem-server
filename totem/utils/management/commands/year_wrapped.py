import csv
import json
from io import StringIO

from django.core.management.base import BaseCommand
from django.utils import timezone

from totem.utils.stats import compute_circle_event_stats, get_month_range, get_year_range


def _pct_change(current: int | float, previous: int | float) -> float | None:
    if previous == 0:
        return None
    return (float(current) - float(previous)) / float(previous) * 100.0


class Command(BaseCommand):
    help = "Generate a year-end recap (monthly + yearly) for the whole company"

    def add_arguments(self, parser):
        parser.add_argument(
            "--year",
            type=int,
            default=None,
            help="Primary year for the recap (defaults to last calendar year).",
        )
        parser.add_argument(
            "--compare-year",
            type=int,
            default=None,
            help="Year to compare against (defaults to --year - 1).",
        )
        parser.add_argument(
            "--format",
            choices=["json", "text", "csv"],
            default="json",
            help="Output format (default: json).",
        )
        parser.add_argument(
            "--output",
            type=str,
            default=None,
            help="Optional filepath to write output instead of stdout.",
        )
        parser.add_argument(
            "--top-events",
            type=int,
            default=5,
            help="Number of top events to include in yearly totals (default: 5).",
        )
        parser.add_argument("--circle-slug", type=int, help="Filter by specific circle id")
        parser.add_argument("--event-slug", type=int, help="Filter by specific event id")
        parser.add_argument("--author-slug", type=str, help="Filter by author slug")

    def handle(self, *args, **options):
        now = timezone.now()
        year = options["year"] or (now.year - 1)
        compare_year = options["compare_year"] or (year - 1)

        circle_id = options["circle_slug"]
        event_id = options["event_slug"]
        author_slug = options["author_slug"]

        years = [compare_year, year]
        recap: dict[str, object] = {
            "generated_at": now.isoformat(),
            "year": year,
            "compare_year": compare_year,
            "filters": {"circle_id": circle_id, "event_id": event_id, "author_slug": author_slug},
            "years": {},
        }

        for y in years:
            year_stats = compute_circle_event_stats(
                date_range=get_year_range(y),
                circle_id=circle_id,
                event_id=event_id,
                author_slug=author_slug,
                top_events=options["top_events"],
            )

            months: list[dict[str, object]] = []
            for month in range(1, 13):
                month_range = get_month_range(y, month)
                month_stats = compute_circle_event_stats(
                    date_range=month_range,
                    circle_id=circle_id,
                    event_id=event_id,
                    author_slug=author_slug,
                    top_events=0,
                )
                months.append(
                    {
                        "month": f"{y}-{month:02d}",
                        **month_stats.asdict(),
                    }
                )

            recap["years"][str(y)] = {
                "year_total": year_stats.asdict(),
                "months": months,
            }

        # Add some precomputed comparisons for convenience.
        this_year = recap["years"][str(year)]["year_total"]
        prev_year = recap["years"][str(compare_year)]["year_total"]
        recap["comparison"] = {
            "year_total": {
                "total_events_pct_change": _pct_change(this_year["total_events"], prev_year["total_events"]),
                "unique_attendees_pct_change": _pct_change(
                    this_year["unique_attendees"], prev_year["unique_attendees"]
                ),
                "unique_joins_pct_change": _pct_change(this_year["unique_joins"], prev_year["unique_joins"]),
            }
        }

        output_format = options["format"]
        if output_format == "json":
            payload = json.dumps(recap, indent=2, sort_keys=True)
            self._write_output(payload, options["output"])
            return

        if output_format == "csv":
            payload = self._to_csv(recap)
            self._write_output(payload, options["output"])
            return

        # text
        lines: list[str] = []
        lines.append("=== Totem Year Wrapped ===")
        lines.append(f"Years: {year} vs {compare_year}")
        if circle_id or event_id or author_slug:
            lines.append(f"Filters: circle_id={circle_id} event_id={event_id} author_slug={author_slug}")

        def _year_line(y: int, label: str) -> None:
            stats = recap["years"][str(y)]["year_total"]
            lines.append(
                f"{label} {y}: "
                f"{stats['total_events']} events, "
                f"{stats['unique_attendees']} unique attendees, "
                f"{stats['unique_joins']} unique joins"
            )

        _year_line(year, "This year")
        _year_line(compare_year, "Last year")

        pct = recap["comparison"]["year_total"]["total_events_pct_change"]
        pct_text = "n/a" if pct is None else f"{pct:+.1f}%"
        lines.append(f"YoY total events change: {pct_text}")

        for y in years:
            top_events = recap["years"][str(y)]["year_total"]["top_events"]
            if top_events:
                lines.append("")
                lines.append(f"Top events ({y}):")
                for event in top_events:
                    lines.append(
                        f"- {event['circle_title']} [{event['event_slug']}] ({event['start'][:10]}) - "
                        f"{event['attendees']} attendees, {event['joined']} joined"
                    )

        self._write_output("\n".join(lines), options["output"])

    def _write_output(self, payload: str, output_path: str | None) -> None:
        if output_path:
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(payload)
                if not payload.endswith("\n"):
                    f.write("\n")
            return
        self.stdout.write(payload)

    def _to_csv(self, recap: dict[str, object]) -> str:
        out = StringIO()
        writer = csv.DictWriter(
            out,
            fieldnames=[
                "year",
                "month",
                "total_events",
                "events_with_attendees",
                "events_no_attendees",
                "total_attendees",
                "unique_attendees",
                "events_with_joins",
                "events_no_joins",
                "total_joins",
                "unique_joins",
                "avg_attendees_per_event",
                "avg_joins_per_event",
            ],
        )
        writer.writeheader()

        for year_str, year_data in recap["years"].items():
            for row in year_data["months"]:
                stats = row
                writer.writerow(
                    {
                        "year": int(year_str),
                        "month": stats["month"],
                        "total_events": stats["total_events"],
                        "events_with_attendees": stats["events_with_attendees"],
                        "events_no_attendees": stats["events_no_attendees"],
                        "total_attendees": stats["total_attendees"],
                        "unique_attendees": stats["unique_attendees"],
                        "events_with_joins": stats["events_with_joins"],
                        "events_no_joins": stats["events_no_joins"],
                        "total_joins": stats["total_joins"],
                        "unique_joins": stats["unique_joins"],
                        "avg_attendees_per_event": stats["avg_attendees_per_event"],
                        "avg_joins_per_event": stats["avg_joins_per_event"],
                    }
                )

            year_total = year_data["year_total"]
            writer.writerow(
                {
                    "year": int(year_str),
                    "month": "year_total",
                    "total_events": year_total["total_events"],
                    "events_with_attendees": year_total["events_with_attendees"],
                    "events_no_attendees": year_total["events_no_attendees"],
                    "total_attendees": year_total["total_attendees"],
                    "unique_attendees": year_total["unique_attendees"],
                    "events_with_joins": year_total["events_with_joins"],
                    "events_no_joins": year_total["events_no_joins"],
                    "total_joins": year_total["total_joins"],
                    "unique_joins": year_total["unique_joins"],
                    "avg_attendees_per_event": year_total["avg_attendees_per_event"],
                    "avg_joins_per_event": year_total["avg_joins_per_event"],
                }
            )

        return out.getvalue()
