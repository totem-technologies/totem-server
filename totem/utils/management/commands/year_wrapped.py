import csv
import json
from io import StringIO

from django.core.management.base import BaseCommand
from django.utils import timezone

from totem.utils.stats import compute_session_stats, get_month_range, get_year_range


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
            "--top-sessions",
            type=int,
            default=5,
            help="Number of top sessions to include in yearly totals (default: 5).",
        )
        parser.add_argument("--space-slug", type=int, help="Filter by specific space id")
        parser.add_argument("--event-slug", type=int, help="Filter by specific event id")
        parser.add_argument("--author-slug", type=str, help="Filter by author slug")

    def handle(self, *args, **options):
        now = timezone.now()
        year = options["year"] or (now.year - 1)
        compare_year = options["compare_year"] or (year - 1)

        space_id = options["space_slug"]
        event_id = options["event_slug"]
        author_slug = options["author_slug"]

        years = [compare_year, year]
        recap: dict[str, object] = {
            "generated_at": now.isoformat(),
            "year": year,
            "compare_year": compare_year,
            "filters": {"space_id": space_id, "event_id": event_id, "author_slug": author_slug},
            "years": {},
        }

        for y in years:
            year_stats = compute_session_stats(
                date_range=get_year_range(y),
                space_id=space_id,
                event_id=event_id,
                author_slug=author_slug,
                top_sessions=options["top_sessions"],
            )

            months: list[dict[str, object]] = []
            for month in range(1, 13):
                month_range = get_month_range(y, month)
                month_stats = compute_session_stats(
                    date_range=month_range,
                    space_id=space_id,
                    event_id=event_id,
                    author_slug=author_slug,
                    top_sessions=0,
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
                "total_sessions_pct_change": _pct_change(this_year["total_sessions"], prev_year["total_sessions"]),
                "unique_signups_pct_change": _pct_change(this_year["unique_signups"], prev_year["unique_signups"]),
                "unique_participants_pct_change": _pct_change(
                    this_year["unique_participants"], prev_year["unique_participants"]
                ),
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
        if space_id or event_id or author_slug:
            lines.append(f"Filters: space_id={space_id} event_id={event_id} author_slug={author_slug}")

        def _year_line(y: int, label: str) -> None:
            stats = recap["years"][str(y)]["year_total"]
            lines.append(
                f"{label} {y}: "
                f"{stats['total_sessions']} sessions, "
                f"{stats['unique_signups']} unique signups, "
                f"{stats['unique_participants']} unique participants"
            )

        _year_line(year, "This year")
        _year_line(compare_year, "Last year")

        pct = recap["comparison"]["year_total"]["total_sessions_pct_change"]
        pct_text = "n/a" if pct is None else f"{pct:+.1f}%"
        lines.append(f"YoY total sessions change: {pct_text}")

        for y in years:
            top_sessions = recap["years"][str(y)]["year_total"]["top_sessions"]
            if top_sessions:
                lines.append("")
                lines.append(f"Top sessions ({y}):")
                for s in top_sessions:
                    lines.append(
                        f"- {s['space_title']} [{s['session_slug']}] ({s['start'][:10]}) - "
                        f"{s['signups']} signups, {s['participants']} participants"
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
                "total_sessions",
                "sessions_with_signups",
                "sessions_no_signups",
                "total_signups",
                "unique_signups",
                "sessions_with_participants",
                "sessions_no_participants",
                "total_participants",
                "unique_participants",
                "avg_signups_per_session",
                "avg_participants_per_session",
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
                        "total_sessions": stats["total_sessions"],
                        "sessions_with_signups": stats["sessions_with_signups"],
                        "sessions_no_signups": stats["sessions_no_signups"],
                        "total_signups": stats["total_signups"],
                        "unique_signups": stats["unique_signups"],
                        "sessions_with_participants": stats["sessions_with_participants"],
                        "sessions_no_participants": stats["sessions_no_participants"],
                        "total_participants": stats["total_participants"],
                        "unique_participants": stats["unique_participants"],
                        "avg_signups_per_session": stats["avg_signups_per_session"],
                        "avg_participants_per_session": stats["avg_participants_per_session"],
                    }
                )

            year_total = year_data["year_total"]
            writer.writerow(
                {
                    "year": int(year_str),
                    "month": "year_total",
                    "total_sessions": year_total["total_sessions"],
                    "sessions_with_signups": year_total["sessions_with_signups"],
                    "sessions_no_signups": year_total["sessions_no_signups"],
                    "total_signups": year_total["total_signups"],
                    "unique_signups": year_total["unique_signups"],
                    "sessions_with_participants": year_total["sessions_with_participants"],
                    "sessions_no_participants": year_total["sessions_no_participants"],
                    "total_participants": year_total["total_participants"],
                    "unique_participants": year_total["unique_participants"],
                    "avg_signups_per_session": year_total["avg_signups_per_session"],
                    "avg_participants_per_session": year_total["avg_participants_per_session"],
                }
            )

        return out.getvalue()
