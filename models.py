import sys
import traceback
import json
import os
import logging

from django.utils import timezone
from django.db import models
from django.http import HttpRequest, HttpResponse

from google.appengine.ext import db

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
    summary = models.CharField(max_length=500)
    file_path = models.CharField(max_length=500)
    line_number = models.PositiveIntegerField()
    is_resolved = models.BooleanField()
    event_count = models.PositiveIntegerField(default=0)
    last_event = models.DateTimeField(auto_now_add=True)
    level = models.CharField(max_length=100, choices=EVENT_LEVEL_CHOICES, default=EVENT_LEVEL_ERROR)

    class Meta:
        unique_together = [
            ('exception_class_name', 'file_path', 'line_number')
        ]

class Event(models.Model):
    error = models.ForeignKey(Error, related_name="events")
    created = models.DateTimeField(auto_now_add=True)
    logged_in_user_email = models.EmailField()

    request_method = models.CharField(max_length=10)
    request_url = models.TextField()
    request_querystring = models.TextField()
    request_repr = models.TextField()

    html_traceback = models.TextField()

    stack_info = models.TextField() #JSON representation of the stack, [{ 'locals' : {}, 'source': '' }]

    app_version = models.CharField(max_length=64, default='Unknown')

    @classmethod
    def log_event(cls, request, response=None, exception=None):
        from django.views.debug import ExceptionReporter

        html_traceback = ""
        if exception:
            exc_type, exc_value, exc_traceback = sys.exc_info()
            summary = "{0}: {1}".format(exception.__class__.__name__, unicode(exception))
            lineno = traceback.tb_lineno(exc_traceback)

            stack = traceback.extract_stack(exc_traceback.tb_frame)
            path = stack[0][0]

            stack_info = []

            frame = exc_traceback
            while frame:
                this_frame = {}
                for k, v in frame.tb_frame.f_locals.iteritems():
                    if isinstance(v, HttpRequest):
                        continue #Ignore the request for purposes of locals

                    local = this_frame.setdefault('locals', {})
                    local[k] = unicode(v) #Store a string representation of the value
                stack_info.append(this_frame)
                frame = frame.tb_next

            level = EVENT_LEVEL_ERROR

            #Get the stacktrace.
            try:
                reporter = ExceptionReporter(request, is_email=False, *(exc_type, exc_value, exc_traceback))
                html_traceback = reporter.get_traceback_html()[:1000000]
            except:
                logging.exception("Unable to get html traceback for some reason")
        else:
            summary = "{0} at {1}".format(response.status_code, request.path)
            lineno = 0
            path = "?".join([request.path, request.META.get('QUERY_STRING')])
            stack_info = {}
            exception = HttpResponse()
            level = EVENT_LEVEL_WARNING if response.status_code == 404 else EVENT_LEVEL_INFO

        error, created = Error.objects.get_or_create(
            exception_class_name=exception.__class__.__name__,
            file_path=path,
            line_number=lineno,
            defaults={
                'level': level,
                'summary': summary,
                'exception_class_name': exception.__class__.__name__ if exception else ""
            }
        )

        @db.transactional(xg=True)
        def txn(_error, _stack_info):
            _error = Error.objects.get(pk=_error.pk)

            Event.objects.create(
                error=_error,
                request_repr=repr(request).strip(),
                request_method=request.method,
                request_url=request.path,
                request_querystring=request.META['QUERY_STRING'],
                logged_in_user_email=getattr(getattr(request, "user", None), "email", ""),
                stack_info=json.dumps(_stack_info),
                app_version=os.environ.get('CURRENT_VERSION_ID', 'Unknown'),
                html_traceback=html_traceback
            )

            _error.last_event = timezone.now()
            _error.event_count += 1
            _error.save()

        txn(error, stack_info)
