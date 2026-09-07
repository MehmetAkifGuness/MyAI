import unittest
from v400_verified_value import VALUE

class VerifiedValueTests(unittest.TestCase):
    def test_value(self):
        self.assertEqual(VALUE, 2)