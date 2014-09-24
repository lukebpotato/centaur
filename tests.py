"""
This file demonstrates writing tests using the unittest module. These will pass
when you run "manage.py test".

Replace this with more appropriate tests for your application.
"""

import mock
from django.test import TestCase
from django.test.client import RequestFactory
from django.core.cache import cache

from centaur.models import Error, Event
from centaur.middleware import CentaurMiddleware

from google.appengine.api.datastore_errors import TransactionFailedError

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

    def test_that_errors_are_deduped(self):
        middleware = CentaurMiddleware()

        try:
            raise TypeError() #Generate an exception with a traceback - genius eh?
        except TypeError, e:
            exception = e

        request = RequestFactory().get("/")
        middleware.process_exception(request, exception)

        def side_effect(**kwargs):
            default = kwargs.pop("defaults", {})
            kwargs.update(default)
            return Error.objects.create(**kwargs), True

        with mock.patch('centaur.models.cache.get') as cache_get:
            cache_get.return_value = None
            with mock.patch('centaur.models.Error.objects.get_or_create', side_effect=side_effect) as get_patch:
                middleware.process_exception(request, exception)
                self.assertTrue(get_patch.called)
                self.assertEqual(2, Error.objects.count())

            middleware.process_exception(request, exception)

        self.assertEqual(1, Error.objects.count())
        self.assertEqual(3, Event.objects.count())
