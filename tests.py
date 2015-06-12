"""
This file demonstrates writing tests using the unittest module. These will pass
when you run "manage.py test".

Replace this with more appropriate tests for your application.
"""

import mock
import json

from datetime import timedelta
from django.utils import timezone
from djangae.test import TestCase, inconsistent_db
from djangae.db.caching import disable_cache
from django.test.client import RequestFactory
from centaur.models import Error, Event
from centaur.middleware import CentaurMiddleware

from djangae.db.transaction import TransactionFailedError

class ErrorTests(TestCase):

    def test_errors_are_hrd_safe(self):
        middleware = CentaurMiddleware()
        request = RequestFactory().get("/")

        try:
            raise TypeError() #Generate an exception with a traceback
        except TypeError, e:
            exception = e

        # Process the same exception 3 times while inconsistent
        with inconsistent_db():
            middleware.process_exception(request, exception)
            with disable_cache():
                middleware.process_exception(request, exception)
                middleware.process_exception(request, exception)

        self.assertEqual(1, Error.objects.count())
        self.assertEqual(3, Event.objects.count())


    def test_transactions_are_retried(self):
        middleware = CentaurMiddleware()

        request = RequestFactory().get("/")

        try:
            raise TypeError() #Generate an exception with a traceback - genius eh?
        except TypeError, e:
            exception = e

        original_func = Event.objects.create
        try:
            def create_replace(func):
                create_replace.call_count = 0
                def wrapper(*args, **kwargs):
                    if create_replace.call_count < 2:
                        create_replace.call_count += 1
                        raise TransactionFailedError()
                    else:
                        return func(*args, **kwargs)
                return wrapper
            create_replace.call_count = 0

            Event.objects.create = create_replace(Event.objects.create)

            self.assertEqual(0, Event.objects.count())
            middleware.process_exception(request, exception)

            self.assertTrue(create_replace.call_count)
            self.assertTrue(Error.objects.exists())
            self.assertEqual(1, Event.objects.count())
            self.assertEqual(1, Error.objects.get().event_count)

        finally:
            Event.objects.create = original_func

    def test_cleanup_task(self):
        from .views import _clear_old_events

        basedate = timezone.now()

        with mock.patch('django.db.models.fields.timezone.now') as mock_now:
            mock_now.return_value = basedate - timedelta(days=20)

            e1 = Error.objects.create(exception_class_name='TestException1', line_number=1, event_count=5)
            e2 = Error.objects.create(exception_class_name='TestException2', line_number=1, event_count=5)

            for i in range(5):
                mock_now.return_value = basedate - timedelta(days=27+i)
                Event.objects.create(error=e1)
                mock_now.return_value = basedate - timedelta(days=27+i+1)
                Event.objects.create(error=e2)

        def mock_defer(f, *a, **kw):
            kw.pop('_queue', None)
            f(*a, **kw)
        with mock.patch('centaur.views.defer', new=mock_defer):
            _clear_old_events()
        self.assertEqual(5, Event.objects.all().count())
        e1 = Error.objects.get(pk=e1.pk)
        e2 = Error.objects.get(pk=e2.pk)
        self.assertEqual(3, e1.event_count)
        self.assertEqual(2, e2.event_count)


    def test_that_blacklisted_cookies_arent_stored(self):
        middleware = CentaurMiddleware()

        request = RequestFactory().get("/")
        request.COOKIES["sessionid"] = "12345"
        request.COOKIES["bananas"] = "yummy"

        try:
            raise TypeError() #Generate an exception with a traceback
        except TypeError, e:
            exception = e

        middleware.process_exception(request, exception)

        event = Event.objects.get()

        data = json.loads(event.request_json)

        self.assertTrue("bananas" in data["COOKIES"])
        self.assertFalse("sessionid" in data["COOKIES"])
