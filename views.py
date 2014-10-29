from datetime import timedelta

from django.conf import settings
from django.utils import timezone
from django.shortcuts import render, get_object_or_404
from django.http import HttpResponse
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.contrib.auth.decorators import user_passes_test

from google.appengine.ext import db
from google.appengine.ext.deferred import defer

from .models import Error, Event

import calendar


def timestamp(datetime):
    """ Returns UTC timestamp, this is included in python3 but not 2"""
    return calendar.timegm(datetime.timetuple())


@user_passes_test(lambda u: u.is_superuser)
def index(request):

    errors = Error.objects.all()

    # Filter by user email
    if request.GET.get('user', None):
        errors_pks = [e.error.pk for e in Event.objects.filter(logged_in_user_email=request.GET.get('user'))]
        errors = errors.filter(pk__in=errors_pks)

    errors = errors.order_by("-last_event")

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


CLEANUP_QUEUE = getattr(settings, 'QUEUE_FOR_EVENT_CLEANUP', 'default')

@user_passes_test(lambda u: u.is_superuser)
def clear_old_events(request):
    defer(_clear_old_events, _queue=CLEANUP_QUEUE)
    return HttpResponse("OK. Cleaning task deferred.")


EVENT_BATCH_SIZE = 400
ERROR_UPDATE_BATCH_SIZE = 50

def _update_error_count(error_id, events_removed):
    @db.transactional(xg=True)
    def txn():
        _error = Error.objects.get(pk=error_id)
        _error.event_count -= events_removed
        _error.save()
    txn()


def _clear_old_events():
    from google.appengine.api.datastore import Query, Delete, Get

    query = Query("centaur_event", keys_only=True)
    query["created <= "] = timezone.now() - timedelta(days=30)
    old_event_keys = list(query.Run(limit=EVENT_BATCH_SIZE))
    old_events = filter(None, Get(old_event_keys))

    errors = {}
    for event in old_events:
        data = errors.setdefault(event['error_id'], {'count': 0, 'event_keys':[]})
        data['count'] += 1
        data['event_keys'].append(event.key())

    to_delete = []
    for error_id, data in errors.items()[:ERROR_UPDATE_BATCH_SIZE]:
        # Each event might be for a different error and while we can delete hundreds of events, we
        # probably don't want to defer hundreds of tasks, so we'll only delete events from a handful of distinct events.
        defer(_update_error_count, error_id, data['count'], _queue=CLEANUP_QUEUE)
        to_delete.extend(data['event_keys'])

    Delete(to_delete)

    if len(old_event_keys) == EVENT_BATCH_SIZE or len(to_delete) < len(old_events):
        # In case we didn't clear everything, run again to find more old events.
        defer(_clear_old_events, _queue=CLEANUP_QUEUE)
