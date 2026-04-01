import csv
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Callable

from django import forms
from django.contrib.admin.views.decorators import staff_member_required
from django.http import HttpRequest, HttpResponse
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils import timezone


@dataclass
class Export:
    slug: str
    name: str
    description: str
    query: Callable[..., HttpResponse]
    form_class: type[forms.Form] | None = None


_registry: list[Export] = []


def register_export(export: Export):
    _registry.append(export)


def get_exports() -> list[Export]:
    return list(_registry)


def get_export(slug: str) -> Export | None:
    for export in _registry:
        if export.slug == slug:
            return export
    return None


@staff_member_required
def export_list_view(request: HttpRequest) -> HttpResponse:
    exports = [
        {
            "name": e.name,
            "description": e.description,
            "url": reverse("admin:exports_download", args=[e.slug]),
            "has_options": e.form_class is not None,
        }
        for e in get_exports()
    ]
    context = {
        "title": "Data Exports",
        "exports": exports,
        **_admin_context(),
    }
    return TemplateResponse(request, "admin/exports/export_list.html", context)


@staff_member_required
def export_download_view(request: HttpRequest, slug: str) -> HttpResponse:
    export = get_export(slug)
    if export is None:
        return HttpResponse("Export not found", status=404)

    if export.form_class is not None:
        form = export.form_class(request.GET or None)
        if not request.GET or not form.is_valid():
            context = {
                "title": export.name,
                "export": export,
                "form": form,
                **_admin_context(),
            }
            return TemplateResponse(request, "admin/exports/export_form.html", context)
        return export.query(**form.cleaned_data)

    return export.query()


def _admin_context() -> dict:
    from django.contrib import admin

    return {
        "site_header": admin.site.site_header,
        "site_title": admin.site.site_title,
        "has_permission": True,
    }


def get_url_patterns():
    return [
        path("exports/", export_list_view, name="exports_index"),
        path("exports/<slug:slug>/", export_download_view, name="exports_download"),
    ]


# --- Helpers ---


def csv_response(filename: str, columns: list[str], rows: list[list[Any]]) -> HttpResponse:
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="{filename}.csv"'
    writer = csv.writer(response)
    writer.writerow(columns)
    for row in rows:
        writer.writerow(row)
    return response


def text_response(filename: str, content: str) -> HttpResponse:
    response = HttpResponse(content, content_type="text/plain")
    response["Content-Disposition"] = f'attachment; filename="{filename}.txt"'
    return response


# --- Registered exports ---


def _onboarded_no_session_90_days() -> HttpResponse:
    from totem.users.models import User

    cutoff = timezone.now() - timedelta(days=90)
    users = (
        User.objects.filter(onboard__onboarded=True)
        .exclude(sessions_joined__start__gte=cutoff)
        .distinct()
        .order_by("email")
        .values_list("email", "name", "date_joined")
    )
    rows = [[email, name, date_joined.isoformat()] for email, name, date_joined in users]
    return csv_response("onboarded-no-session-90-days", ["email", "name", "date_joined"], rows)


register_export(
    Export(
        slug="onboarded-no-session-90-days",
        name="Onboarded, no session in 90 days",
        description="Users who completed onboarding but have not attended a session in the last 90 days.",
        query=_onboarded_no_session_90_days,
    )
)


# --- Session stats ---

PERIOD_CHOICES = [
    ("last_week", "Last week"),
    ("last_month", "Last month"),
    ("last_quarter", "Last quarter"),
    ("all_time", "All time"),
]


class SessionStatsForm(forms.Form):
    period = forms.ChoiceField(choices=PERIOD_CHOICES, initial="last_quarter")


def _session_stats_export(period: str) -> HttpResponse:
    from totem.utils.stats import compute_session_stats, get_date_range

    date_range = get_date_range(period)
    stats = compute_session_stats(date_range=date_range)

    lines = [
        f"Session Stats: {stats.date_range.label()}",
        f"{'=' * 40}",
        f"Total sessions:                {stats.total_sessions}",
        f"Sessions with signups:         {stats.sessions_with_signups}",
        f"Sessions without signups:      {stats.sessions_no_signups}",
        f"Total signups:                 {stats.total_signups}",
        f"Unique signups:                {stats.unique_signups}",
        f"Avg signups/session:           {stats.avg_signups_per_session or 'N/A'}",
        "",
        f"Sessions with participants:    {stats.sessions_with_participants}",
        f"Sessions without participants: {stats.sessions_no_participants}",
        f"Total participants:            {stats.total_participants}",
        f"Unique participants:           {stats.unique_participants}",
        f"Avg participants/session:      {stats.avg_participants_per_session or 'N/A'}",
    ]

    if stats.top_sessions:
        lines += ["", "Top sessions:"]
        for i, s in enumerate(stats.top_sessions, 1):
            lines.append(
                f"  {i}. {s['space_title']} ({s['session_slug']}) "
                f"- {s['signups']} signups, {s['participants']} participants"
            )

    return text_response(f"session-stats-{period}", "\n".join(lines))


register_export(
    Export(
        slug="session-stats",
        name="Session stats summary",
        description="Summary statistics for sessions in a given time period.",
        query=_session_stats_export,
        form_class=SessionStatsForm,
    )
)


# --- Grant metrics ---

CURRENT_YEAR = timezone.now().year
YEAR_CHOICES = [(str(y), str(y)) for y in range(CURRENT_YEAR, CURRENT_YEAR - 5, -1)]


class GrantMetricsForm(forms.Form):
    year = forms.ChoiceField(choices=YEAR_CHOICES, initial=str(CURRENT_YEAR))


def _grant_metrics_export(year: str) -> HttpResponse:
    from totem.utils.grant_metrics import compute_grant_metrics

    return text_response(f"grant-metrics-{year}", compute_grant_metrics(int(year)))


register_export(
    Export(
        slug="grant-metrics",
        name="Grant metrics report",
        description="Comprehensive metrics for funding & grant applications: growth, engagement, retention, and demographic data.",
        query=_grant_metrics_export,
        form_class=GrantMetricsForm,
    )
)
