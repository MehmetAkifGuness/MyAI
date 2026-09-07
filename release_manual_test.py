import unittest

VALUE = 1

class ValueTests(unittest.TestCase):
    def test_value(self):
        self.assertEqual(VALUE, 2)