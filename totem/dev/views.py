import calendar

from dateutil import rrule as _rrule
from django.shortcuts import render

freqs = [
    {"name": "Yearly", "option": _rrule.YEARLY},
    {"name": "Monthly", "option": _rrule.MONTHLY},
    {"name": "Weekly", "option": _rrule.WEEKLY},
    {"name": "Daily", "option": _rrule.DAILY},
]
rrule_data = {
    "days": [d for d in calendar.day_name],
    "months": [m for m in calendar.month_name],
    "freqs": freqs,
    "bydays": [d for d in calendar.day_name],
    "bymonths": [m for m in calendar.month_name],
    "bymonthdays": [d for d in range(1, 32)],
    "byyeardays": [d for d in range(1, 367)],
    "byweeks": [d for d in range(1, 54)],
    "byhours": [d for d in range(0, 24)],
    "byminutes": [d for d in range(0, 60)],
    "byseconds": [d for d in range(0, 60)],
    "wkst": [d for d in calendar.day_name],
}


# Create your views here.
def rrule(request):
    if request.method == "POST":
        rrule_data["rrule"] = request.POST.get("rrule")
    return render(request, "dev/rrule.html", context={"rrule_data": rrule_data})


def healthcheck(request):
    return render(request, "dev/healthcheck.html")
