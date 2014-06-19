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
