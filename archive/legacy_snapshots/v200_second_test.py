import unittest
from v200_second import SECOND

class SecondTests(unittest.TestCase):
    def test_second(self):
        self.assertEqual(SECOND, 3)