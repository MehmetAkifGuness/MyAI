import unittest
from v170_runtime_value import VALUE

class RuntimeValueTests(unittest.TestCase):
    def test_value(self):
        self.assertEqual(VALUE, 2)