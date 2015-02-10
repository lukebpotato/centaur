import sys
import traceback
import json
import os
import logging
import time
from hashlib import md5

from django.utils import timezone
from django.db import models
from django.http import HttpResponse
from django.core.cache import cache
from django.utils.encoding import smart_str

from djangae.db.transaction import atomic, TransactionFailedError

from .utils import construct_request_json

EVENT_LEVEL_WARNING = "WARNING"
EVENT_LEVEL_INFO = "INFO"
EVENT_LEVEL_ERROR = "ERROR"

EVENT_LEVEL_CHOICES = [
    (EVENT_LEVEL_ERROR, "Error"),
    (EVENT_LEVEL_WARNING, "Warning"),
    (EVENT_LEVEL_INFO, "Info")
]

class Error(models.Model):
    exception_class_name = models.CharField(max_length=255)
    summary = models.TextField()
    file_path = models.TextField()
    hashed_file_path = models.CharField(max_length=32)

    line_number = models.PositiveIntegerField()
    is_resolved = models.BooleanField(default=False)
    event_count = models.PositiveIntegerField(default=0)
    last_event = models.DateTimeField(auto_now_add=True)
    level = models.CharField(max_length=100, choices=EVENT_LEVEL_CHOICES, default=EVENT_LEVEL_ERROR)

    class Meta:
        unique_together = [
            ('exception_class_name', 'hashed_file_path', 'line_number')
        ]

    @staticmethod
    def hash_for_file_path(file_path):
        return md5(smart_str(file_path)).hexdigest()


class Event(models.Model):
    error = models.ForeignKey(Error, related_name="events")
    created = models.DateTimeField(auto_now_add=True)
    logged_in_user_email = models.EmailField()

    request_method = models.CharField(max_length=10)
    request_url = models.TextField()
    request_querystring = models.TextField()
    request_repr = models.TextField()
    request_json = models.TextField()

    stack_info_json = models.TextField() #JSON representation of the stack, [{ 'locals' : {}, 'source': '' }]

    app_version = models.CharField(max_length=64, default='Unknown')

    @property
    def stack_info(self):
        if self.stack_info_json:
            return json.loads(self.stack_info_json)
        else:
            return {}

    @property
    def request(self):
        if self.request_json:
            return json.loads(self.request_json)
        else:
            return {}

    @classmethod
    def log_event(cls, request, response=None, exception=None):
        from django.views.debug import ExceptionReporter

        stack_info = {}
        if exception:
            exc_type, exc_value, exc_traceback = sys.exc_info()
            summary = "{0}: {1}".format(exception.__class__.__name__, unicode(exception))
            lineno = traceback.tb_lineno(exc_traceback)

            stack = traceback.extract_tb(exc_traceback)
            unique_path = "|".join(line[0] for line in stack)
            path = stack[-1][0]

            try:
                reporter = ExceptionReporter(request, is_email=False, *(exc_type, exc_value, exc_traceback))
                django_data = reporter.get_traceback_data()

                stack_info["frames"] = django_data.get("frames", [])

                #Traceback objects aren't JSON serializable, so delete them
                for frame in stack_info["frames"]:
                    if "tb" in frame:
                        del frame["tb"]

                stack_info["lastframe"] = django_data.get("lastframe", {})
            except Exception:
                logging.exception("Unable to get html traceback info for some reason")
            level = EVENT_LEVEL_ERROR

        else:
            summary = u"{0} at {1}".format(response.status_code, request.path)
            lineno = 0
            path = "?".join([request.path, request.META.get('QUERY_STRING')])
            unique_path = path
            exception = HttpResponse()
            level = EVENT_LEVEL_WARNING if response.status_code == 404 else EVENT_LEVEL_INFO

        exception_name = exception.__class__.__name__

        # unique_path is either the full URL or the combined paths from the
        # entire stack trace.
        path_hash = Error.hash_for_file_path(unique_path)

        #We try to get from the cache first because on the App Engine datastore
        #we'll get screwed by eventual consistency otherwise
        CACHE_KEY = "|".join([exception_name, path_hash, str(lineno)])
        error = cache.get(CACHE_KEY)
        if error:
            created = False
        else:
            error, created = Error.objects.get_or_create(
                exception_class_name=exception_name,
                hashed_file_path=path_hash,
                line_number=lineno,
                defaults={
                    'file_path': path,
                    'level': level,
                    'summary': summary
                }
            )

            cache.set(CACHE_KEY, error)

        @atomic(xg=True)
        def txn(_error):
            _error = Error.objects.get(pk=_error.pk)

            event = Event.objects.create(
                error=_error,
                request_repr=repr(request).strip(),
                request_method=request.method,
                request_url=request.build_absolute_uri(),
                request_querystring=request.META['QUERY_STRING'],
                logged_in_user_email=getattr(getattr(request, "user", None), "email", ""),
                stack_info_json=json.dumps(stack_info),
                app_version=os.environ.get('CURRENT_VERSION_ID', 'Unknown'),
                request_json=construct_request_json(request)
            )

            _error.last_event = timezone.now()
            _error.event_count += 1
            _error.save()
            return event

        to_sleep = 1
        while True:
            try:
                return txn(error)
            except TransactionFailedError:
                time.sleep(to_sleep)
                to_sleep *= 2
                to_sleep = min(to_sleep, 8)
                continue
