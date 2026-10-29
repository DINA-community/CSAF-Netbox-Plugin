"""Testcases for utility functions"""
from django.test import TestCase
from csaf.tables import encode_acceptance_status
from csaf.views import decode_acceptance_status, is_encoded_acceptance_status

class UtilitiesTestCase(TestCase):
    """Check the utility functions in tables and views."""

    def test_encode_and_decode_acceptance_status(self):
        """Check if encode and then decode leads to same values."""
        status = "O"
        pk = 3
        self.assertEqual(decode_acceptance_status(encode_acceptance_status(status, pk)), (status, pk))

    def test_encode_acceptance_status(self):
        """Check interna of encode, and a encoded is_encoded"""
        status = "O"
        pk = 3
        self.assertEqual(encode_acceptance_status(status, pk), f"{status}:{pk}")
        self.assertTrue(is_encoded_acceptance_status(encode_acceptance_status(status, pk)))

    def test_is_encoded_acceptance_status(self):
        """Check is_encoded_acceptance_status: both cases"""
        self.assertTrue(is_encoded_acceptance_status("N:4"))
        self.assertFalse(is_encoded_acceptance_status("N"))
