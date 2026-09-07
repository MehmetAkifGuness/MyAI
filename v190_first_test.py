import unittest
from v190_first import FIRST

class FirstTests(unittest.TestCase):
    def test_first(self):
        self.assertEqual(FIRST, 2)