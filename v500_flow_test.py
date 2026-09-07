import unittest
from v500_flow import VALUE

class FlowTests(unittest.TestCase):
    def test_value(self):
        self.assertEqual(VALUE, 2)