"""
This file demonstrates writing tests using the unittest module. These will pass
when you run "manage.py test".

Replace this with more appropriate tests for your application.
"""

import mock
from datetime import timedelta
from django.utils import timezone
from django.test import TestCase
from django.test.client import RequestFactory
from django.contrib.auth.decorators import user_passes_test
from django.contrib.auth.models import User

from centaur.models import Error, Event
from centaur.middleware import CentaurMiddleware
from centaur.views import get_permission_decorator

from djangae.db.transaction import TransactionFailedError

class ErrorTests(TestCase):
    def test_that_saving_an_error_stores_a_hashed_filename(self):
        error = Error.objects.create(file_path="bananas", line_number=1)
        self.assertEqual(Error.hash_for_file_path("bananas"), error.hashed_file_path)

    def test_that_errors_are_cached(self):
        middleware = CentaurMiddleware()

        request = RequestFactory().get("/")

        try:
            raise TypeError() #Generate an exception with a traceback - genius eh?
        except TypeError, e:
            exception = e

        self.assertFalse(Error.objects.exists())

        self.assertEqual(0, Event.objects.count())
        middleware.process_exception(request, exception)
        self.assertTrue(Error.objects.exists())
        self.assertEqual(1, Event.objects.count())

        with mock.patch('centaur.models.Error.objects.get_or_create') as get_patch:
            middleware.process_exception(request, exception)
            self.assertFalse(get_patch.called)
            self.assertEqual(2, Event.objects.count())


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


custom_decorator = user_passes_test(lambda u: u.email.endswith('@example.com'))

class ViewsTests(TestCase):

    def test_custom_permission_decorator(self):
        with self.settings(CENTAUR_PERMISSION_DECORATOR='centaur.tests.custom_decorator'):
            self.assertEqual(get_permission_decorator(), custom_decorator)

        self.assertNotEqual(get_permission_decorator(), custom_decorator)
