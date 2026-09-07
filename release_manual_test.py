import unittest

VALUE = 2

class ValueTests(unittest.TestCase):
    def test_value(self):
        self.assertEqual(VALUE, 2)