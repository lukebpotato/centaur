"""
This file demonstrates writing tests using the unittest module. These will pass
when you run "manage.py test".

Replace this with more appropriate tests for your application.
"""

from django.test import TestCase
from centaur.models import Error

class ErrorTests(TestCase):
    def test_that_saving_an_error_stores_a_hashed_filename(self):
        error = Error.objects.create(file_path="bananas")
        self.assertEqual(Error.hash_for_file_path("bananas"), error.hashed_file_path)
