import csv
from collections.abc import Iterable
from typing import TextIO

from totem.reporting.types import MetricResult

CSV_COLUMNS = (
    "metric_name",
    "value",
    "unit",
    "numerator",
    "denominator",
    "period_start",
    "period_end",
    "reporting_timezone",
    "period_kind",
    "period_label",
    "cohort",
    "generated_at",
    "definition_version",
)


def write_metric_csv(metrics: Iterable[MetricResult], stream: TextIO):
    writer = csv.DictWriter(stream, fieldnames=CSV_COLUMNS)
    writer.writeheader()
    for metric in metrics:
        writer.writerow(
            {
                "metric_name": metric.metric_name,
                "value": "" if metric.value is None else str(metric.value),
                "unit": metric.unit,
                "numerator": "" if metric.numerator is None else str(metric.numerator),
                "denominator": "" if metric.denominator is None else str(metric.denominator),
                "period_start": metric.period_start.isoformat(),
                "period_end": metric.period_end.isoformat(),
                "reporting_timezone": metric.reporting_timezone,
                "period_kind": metric.period_kind,
                "period_label": metric.period_label,
                "cohort": metric.cohort,
                "generated_at": metric.generated_at.isoformat(),
                "definition_version": metric.definition_version,
            }
        )
