import unittest
from v200_first import FIRST

class FirstTests(unittest.TestCase):
    def test_first(self):
        self.assertEqual(FIRST, 2)