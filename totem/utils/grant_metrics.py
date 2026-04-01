"""
Grant metrics report for funding & grant applications.

Computes aggregate metrics across these categories:
- Growth & Reach (participants, sessions, capacity)
- Engagement & Retention (repeat attendance, conversion)
- Accessibility & Inclusion (timezone/geographic diversity, demographics)
"""

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta
from datetime import timezone as dttz

from django.db.models import Count
from django.db.models.functions import TruncMonth
from django.utils import timezone

from totem.onboard.models import OnboardModel, ReferralChoices
from totem.spaces.models import Session
from totem.users.models import User

UTC = dttz.utc


def _pct(numerator: int, denominator: int) -> str:
    if denominator == 0:
        return "N/A"
    return f"{numerator / denominator * 100:.1f}%"


def _year_range(year: int) -> tuple[datetime, datetime]:
    """Return (start, end) datetimes for a calendar year. End is exclusive."""
    return (
        datetime(year, 1, 1, tzinfo=UTC),
        datetime(year + 1, 1, 1, tzinfo=UTC),
    )


@dataclass
class _SessionData:
    """Pre-materialized data for a single session, avoiding repeated M2M queries."""

    start: datetime
    seats: int
    joined_ids: set[int]
    attendee_ids: set[int]

    @property
    def joined_count(self) -> int:
        return len(self.joined_ids)

    @property
    def attendee_count(self) -> int:
        return len(self.attendee_ids)


def _load_sessions() -> list[_SessionData]:
    """Load all completed, non-cancelled sessions with M2M data materialized once."""
    now = timezone.now()
    sessions = list(Session.objects.filter(cancelled=False, start__lt=now).prefetch_related("attendees", "joined"))
    result: list[_SessionData] = []
    for s in sessions:
        if s.start + timedelta(minutes=s.duration_minutes) > now:
            continue
        result.append(
            _SessionData(
                start=s.start,
                seats=s.seats,
                joined_ids={u.id for u in s.joined.all()},
                attendee_ids={u.id for u in s.attendees.all()},
            )
        )
    return result


def compute_grant_metrics(year: int) -> str:
    now = timezone.now()
    prev_year = year - 1
    year_start, year_end = _year_range(year)
    prev_start, prev_end = _year_range(prev_year)

    # ── Load all session data once ──
    all_sessions = _load_sessions()
    total_sessions = len(all_sessions)

    # ── Single pass over all sessions ──
    all_joined_ids: set[int] = set()
    all_signup_ids: set[int] = set()
    this_year_joined: set[int] = set()
    prev_year_joined: set[int] = set()
    user_first_session: dict[int, datetime] = {}
    user_session_counts: Counter[int] = Counter()
    monthly_user_joins: dict[str, set[int]] = {}
    total_joins_all = 0
    total_signup_seats = 0
    total_join_seats = 0
    full_count = 0

    for s in all_sessions:
        joined = s.joined_ids
        attendees = s.attendee_ids
        joined_count = s.joined_count
        attendee_count = s.attendee_count

        # Lifetime totals
        all_joined_ids.update(joined)
        all_signup_ids.update(attendees)
        total_joins_all += joined_count

        # Conversion rate accumulators
        if attendee_count > 0:
            total_signup_seats += attendee_count
            total_join_seats += joined_count

        # Full sessions
        if attendee_count >= s.seats:
            full_count += 1

        # Year buckets
        if year_start <= s.start < year_end:
            this_year_joined.update(joined)
        elif prev_start <= s.start < prev_end:
            prev_year_joined.update(joined)

        # Per-user stats
        for uid in joined:
            user_session_counts[uid] += 1
            if uid not in user_first_session or s.start < user_first_session[uid]:
                user_first_session[uid] = s.start

        # Monthly buckets
        month_key = s.start.strftime("%Y-%m")
        if month_key not in monthly_user_joins:
            monthly_user_joins[month_key] = set()
        monthly_user_joins[month_key].update(joined)

    total_participants = len(all_joined_ids)
    unique_signups = len(all_signup_ids)
    avg_attendees = total_joins_all / total_sessions if total_sessions > 0 else 0
    conversion_rate = total_join_seats / total_signup_seats * 100 if total_signup_seats > 0 else 0

    # ── New vs returning participants ──
    new_participants = sum(1 for uid in this_year_joined if user_first_session.get(uid, now) >= year_start)
    returning_participants = len(this_year_joined) - new_participants

    # ── Repeat attendance ──
    users_with_repeat = sum(1 for count in user_session_counts.values() if count > 1)
    repeat_rate = users_with_repeat / total_participants * 100 if total_participants > 0 else 0
    if user_session_counts:
        avg_sessions_per_user = sum(user_session_counts.values()) / len(user_session_counts)
    else:
        avg_sessions_per_user = 0

    # ── Email list ──
    newsletter_count = User.objects.filter(newsletter_consent=True).count()

    newsletter_by_month = (
        User.objects.filter(newsletter_consent=True)
        .annotate(month=TruncMonth("date_created"))
        .values("month")
        .annotate(count=Count("id"))
        .order_by("month")
    )
    newsletter_monthly: list[tuple[str, int, int]] = []  # (YYYY-MM, new, cumulative)
    cumulative = 0
    for row in newsletter_by_month:
        if row["month"] is None:
            continue
        cumulative += row["count"]
        newsletter_monthly.append((row["month"].strftime("%Y-%m"), row["count"], cumulative))

    # ── Referral source breakdown (from onboarding) ──
    referral_counts = (
        OnboardModel.objects.filter(onboarded=True)
        .values("referral_source")
        .annotate(count=Count("id"))
        .order_by("-count")
    )
    friend_referrals = 0
    referral_lines: list[str] = []
    for r in referral_counts:
        source = r["referral_source"]
        try:
            label = ReferralChoices(source).label
        except ValueError:
            label = source or "Unknown"
        referral_lines.append(f"  {label}: {r['count']}")
        if r["referral_source"] == "friend":
            friend_referrals = r["count"]

    # ── Timezone / geographic diversity ──
    # Use a subquery join via sessions_joined instead of a large IN clause
    tz_counts = (
        User.objects.filter(sessions_joined__isnull=False)
        .exclude(timezone="")
        .values("timezone")
        .annotate(count=Count("id", distinct=True))
        .order_by("-count")
    )
    tz_list = [(str(r["timezone"]), r["count"]) for r in tz_counts]
    unique_timezones = len(tz_list)

    # Classify US vs international by timezone prefix
    us_tz_prefixes = (
        "US/",
        "America/New_York",
        "America/Chicago",
        "America/Denver",
        "America/Los_Angeles",
        "America/Anchorage",
        "America/Phoenix",
        "America/Boise",
        "America/Detroit",
        "America/Indiana",
        "America/Kentucky",
        "America/North_Dakota",
        "Pacific/Honolulu",
    )
    us_count = sum(c for tz, c in tz_list if any(tz.startswith(p) for p in us_tz_prefixes))
    intl_count = sum(c for tz, c in tz_list) - us_count
    tz_total = us_count + intl_count

    # ── Demographic diversity (year born) ──
    birth_years = list(
        OnboardModel.objects.filter(onboarded=True, year_born__isnull=False).values_list("year_born", flat=True)
    )
    current_year = now.year
    age_brackets: Counter[str] = Counter()
    for yb in birth_years:
        age = current_year - yb
        if age < 25:
            age_brackets["Under 25"] += 1
        elif age < 35:
            age_brackets["25-34"] += 1
        elif age < 45:
            age_brackets["35-44"] += 1
        elif age < 55:
            age_brackets["45-54"] += 1
        elif age < 65:
            age_brackets["55-64"] += 1
        else:
            age_brackets["65+"] += 1

    monthly_sorted = sorted(monthly_user_joins.items())

    # ── Build report ──
    lines: list[str] = []
    lines.append("TOTEM GRANT METRICS REPORT")
    lines.append(f"Generated: {now.strftime('%Y-%m-%d')}")
    lines.append(f"Report year: {year} (compared to {prev_year})")
    lines.append("=" * 60)

    lines.append("")
    lines.append("GROWTH & REACH")
    lines.append("-" * 40)
    lines.append(f"Total participants (lifetime):  {total_participants}")
    lines.append(f"Unique signups (lifetime):      {unique_signups}")
    lines.append(f"Total sessions hosted:          {total_sessions}")
    lines.append(f"Avg attendees per session:      {avg_attendees:.1f}")
    lines.append("")
    lines.append(f"Unique participants ({year}):    {len(this_year_joined)}")
    lines.append(f"Unique participants ({prev_year}):    {len(prev_year_joined)}")
    if prev_year_joined:
        yoy_growth = (len(this_year_joined) - len(prev_year_joined)) / len(prev_year_joined) * 100
        lines.append(f"Year-over-year growth:          {yoy_growth:+.1f}%")
    else:
        lines.append(f"Year-over-year growth:          N/A (no {prev_year} data)")
    lines.append("")
    lines.append(f"Full sessions (at capacity):    {full_count} ({_pct(full_count, total_sessions)} of sessions)")
    lines.append("")
    lines.append(f"Email list (newsletter):        {newsletter_count}")
    if newsletter_monthly:
        lines.append("Email list growth:")
        for month, new, cumul in newsletter_monthly:
            lines.append(f"  {month}: +{new:>3} (total: {cumul})")
    lines.append("")
    lines.append(f"New participants ({year}):        {new_participants}")
    lines.append(f"Returning participants ({year}):  {returning_participants}")
    lines.append(f"Attendance conversion rate:      {conversion_rate:.1f}%")

    lines.append("")
    lines.append("ENGAGEMENT & RETENTION (among joined participants)")
    lines.append("-" * 40)
    lines.append(f"Repeat attendance rate:         {repeat_rate:.1f}% ({users_with_repeat} of {total_participants})")
    lines.append(f"Avg sessions per user:          {avg_sessions_per_user:.1f}")
    lines.append("")
    lines.append("REFERRAL SOURCES (among onboarded users)")
    lines.append("-" * 40)
    lines.append(f"Friend referrals:               {friend_referrals}")
    lines.extend(referral_lines)

    lines.append("")
    lines.append("GEOGRAPHIC DIVERSITY (among joined participants)")
    lines.append("-" * 40)
    lines.append(f"Unique timezones:               {unique_timezones}")
    if tz_total > 0:
        lines.append(f"US-based participants:          {us_count} ({_pct(us_count, tz_total)})")
        lines.append(f"International participants:     {intl_count} ({_pct(intl_count, tz_total)})")
    lines.append("")
    lines.append("Top timezones:")
    for tz, count in tz_list[:10]:
        lines.append(f"  {tz}: {count}")

    if age_brackets:
        lines.append("")
        lines.append("AGE DISTRIBUTION (among onboarded users)")
        for bracket in ["Under 25", "25-34", "35-44", "45-54", "55-64", "65+"]:
            count = age_brackets.get(bracket, 0)
            lines.append(f"  {bracket}: {count}")

    if monthly_sorted:
        lines.append("")
        lines.append("MONTHLY UNIQUE PARTICIPANTS (joined sessions)")
        lines.append("-" * 40)
        prev_count = 0
        for month, uids in monthly_sorted:
            count = len(uids)
            if prev_count > 0:
                mom = (count - prev_count) / prev_count * 100
                lines.append(f"  {month}: {count:>4}  ({mom:+.0f}% MoM)")
            else:
                lines.append(f"  {month}: {count:>4}")
            prev_count = count

    lines.append("")
    lines.append("NOTES")
    lines.append("-" * 40)
    lines.append("- Two cohorts are used: 'joined participants' (users who attended a session)")
    lines.append("  and 'onboarded users' (completed onboarding, may not have attended). Each")
    lines.append("  section header indicates which cohort it describes.")
    lines.append("- 'Unique signups' = distinct users who signed up for any session")
    lines.append("- 'Attendance conversion rate' = total joined seats / total signed-up seats")
    lines.append("- Timezone is used as a proxy for geographic reach (no country data collected)")
    lines.append("- US classification is approximate based on timezone prefixes")
    lines.append("- Session completion/stay duration not currently tracked")
    lines.append("- Community referrals approximated via onboarding 'friend' referral source")

    return "\n".join(lines)
