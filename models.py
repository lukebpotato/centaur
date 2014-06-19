import sys
import traceback
import json
import os
import logging
from hashlib import md5

from django.utils import timezone
from django.db.models import Model
from django.db import models
from django.http import HttpResponse
from django.core.cache import cache
from django.core.exceptions import MultipleObjectsReturned
from google.appengine.ext import db

from .utils import construct_request_json

EVENT_LEVEL_WARNING = "WARNING"
EVENT_LEVEL_INFO = "INFO"
EVENT_LEVEL_ERROR = "ERROR"

EVENT_LEVEL_CHOICES = [
    (EVENT_LEVEL_ERROR, "Error"),
    (EVENT_LEVEL_WARNING, "Warning"),
    (EVENT_LEVEL_INFO, "Info")
]

class Error(Model):
    exception_class_name = models.CharField(max_length=255)
    summary = models.CharField(max_length=500)
    file_path = models.TextField()
    hashed_file_path = models.CharField(max_length=32)

    line_number = models.PositiveIntegerField()
    is_resolved = models.BooleanField()
    event_count = models.PositiveIntegerField(default=0)
    last_event = models.DateTimeField(auto_now_add=True)
    level = models.CharField(max_length=100, choices=EVENT_LEVEL_CHOICES, default=EVENT_LEVEL_ERROR)

    class Meta:
        unique_together = [
            ('exception_class_name', 'hashed_file_path', 'line_number')
        ]

    @staticmethod
    def hash_for_file_path(file_path):
        return md5(file_path).hexdigest()

    def save(self, *args, **kwargs):
        self.hashed_file_path = Error.hash_for_file_path(self.file_path)
        super(Error, self).save(*args, **kwargs)

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

            stack = traceback.extract_stack(exc_traceback.tb_frame)
            path = stack[0][0]

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
            summary = "{0} at {1}".format(response.status_code, request.path)
            lineno = 0
            path = "?".join([request.path, request.META.get('QUERY_STRING')])
            exception = HttpResponse()
            level = EVENT_LEVEL_WARNING if response.status_code == 404 else EVENT_LEVEL_INFO

        exception_name = exception.__class__.__name__
        path_hash = Error.hash_for_file_path(path)

        #We try to get from the cache first because on the App Engine datastore
        #we'll get screwed by eventual consistency otherwise
        CACHE_KEY = "|".join([exception_name, path_hash, str(lineno)])
        error = cache.get(CACHE_KEY)
        if error:
            created = False
        else:
            try:
                error, created = Error.objects.get_or_create(
                    exception_class_name=exception_name,
                    hashed_file_path=path_hash,
                    line_number=lineno,
                    defaults={
                        'file_path': path,
                        'level': level,
                        'summary': summary,
                        'exception_class_name': exception.__class__.__name__ if exception else ""
                    }
                )
            except MultipleObjectsReturned:
                #FIXME: Temporary hack for App Engine If we created dupes, this de-dupes them
                errors = Error.objects.filter(exception_class_name=exception_name, hashed_file_path=path_hash, line_number=lineno).all()

                max_errors = 0
                to_keep = None
                to_remove = []
                for error in errors:
                    num_events = error.events.count()
                    if max_errors < num_events:
                        # Store the error with the most events
                        to_keep = error
                        max_errors = num_events
                    else:
                        #this error doesn't have the most events, so mark it for removal
                        to_remove.append(error)

                assert to_keep

                logging.warning("Removing {} duplicate errors".format(len(to_remove)))
                for error in to_remove:
                    error.events.all().update(error=to_keep)
                    error.delete()

                error = to_keep

            cache.set(CACHE_KEY, error)

        @db.transactional(xg=True)
        def txn(_error):
            _error = Error.objects.get(pk=_error.pk)

            Event.objects.create(
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

        txn(error)
