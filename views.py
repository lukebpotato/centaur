from django.shortcuts import render, get_object_or_404
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.contrib.auth.decorators import user_passes_test

from .models import Error

import calendar
from itertools import groupby
import datetime


def timestamp(datetime):
    """ Returns UTC timestamp, this is included in python3 but not 2"""
    return calendar.timegm(datetime.timetuple())


@user_passes_test(lambda u: u.is_superuser)
def index(request):
    errors = Error.objects.all().order_by("-last_event")
    return render(request, "centaur/index.html", {"errors": errors})


@user_passes_test(lambda u: u.is_superuser)
def error(request, error_id, limit=200):
    error = get_object_or_404(Error, pk=error_id)
    events = error.events.all().order_by("-created")[:limit]

    series = [
        timestamp(event.created.replace(minute=0, second=0, microsecond=0))
        for event in events
    ]

    page = request.GET.get('page', 0)
    paginator = Paginator(events, 1)
    try:
        events = paginator.page(page)
    except PageNotAnInteger:
        events = paginator.page(1)
    except EmptyPage:
        events = paginator.page(paginator.num_pages)

    return render(request, "centaur/error.html", {
        "error": error,
        "events": events,
        "series": series,
    })


@user_passes_test(lambda u: u.is_superuser)
def clear_old_events(request):
    _clear_old_events()


def _clear_old_events():
    pass
    # 1 chainability
    #event. created

    # delete batch of events

    # collect number of events per error

    #defer transactions to adjust number of events.
