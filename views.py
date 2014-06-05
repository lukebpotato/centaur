from datetime import date, timedelta
from collections import OrderedDict

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
def error(request, error_id):
    error = get_object_or_404(Error, pk=error_id)
    events = error.events.all().order_by("-created")

    ## Time magic
    series = list(events.values_list("created", flat=True))
    timebins = OrderedDict()
    # Specify the inteval to work with
    interval = datetime.timedelta(hours=1)
    # Work out start date and end date
    start_date = series[0].replace(minute=0, second=0, microsecond=0) - interval
    end_date = series[-1].replace(minute=0, second=0, microsecond=0) + interval
    # HighCharts intervals and starts
    pointinterval = int(interval.total_seconds() * 1000)
    pointstart = tuple([start_date.year, start_date.month - 1, start_date.day, start_date.hour - 1])

    # Add the data to the correct intervals
    for k, g in groupby(series, lambda x: int(timestamp(x.replace(minute=0, second=0, microsecond=0)))):
        group = list(g)
        timebins[k] = len(group) # The count
    # Flatten into a list
    bins = [(k, v) for k, v in timebins.iteritems()]
    ## End of magic

    page = request.GET.get('page', 0)
    paginator = Paginator(events.order_by("-created"), 1)
    try:
        events = paginator.page(page)
    except PageNotAnInteger:
        events = paginator.page(1)
    except EmptyPage:
        events = paginator.page(paginator.num_pages)

    return render(request, "centaur/error.html", {
        "error": error,
        "events": events,
        "bins": bins,
        'pointstart': pointstart,
        'pointinterval': pointinterval,
        "start_date": timestamp(date.today() - timedelta(days=7)),
    })
