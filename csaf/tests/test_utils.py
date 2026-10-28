"""Testcases for utility functions"""
from django.test import TestCase
from csaf.tables import compress
from csaf.views import decompress, is_compressed

class UtilitiesTestCase(TestCase):
    """Check the utility functions in tables and views."""

    def test_compress_and_decompress(self):
        """Check if compress and then decompress leads to same values."""
        status = "O"
        pk = 3
        self.assertEqual(decompress(compress(status, pk)), (status, pk))

    def test_compress(self):
        """Check interna of compress, and a compressed is_compressed"""
        status = "O"
        pk = 3
        self.assertEqual(compress(status, pk), f"{status}:{pk}")
        self.assertTrue(is_compressed(compress(status, pk)))

    def test_is_compressed(self):
        """Check is_compressed: both cases"""
        self.assertTrue(is_compressed("N:4"))
        self.assertFalse(is_compressed("N"))
