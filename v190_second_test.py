import unittest
from v190_second import SECOND

class SecondTests(unittest.TestCase):
    def test_second(self):
        self.assertEqual(SECOND, 3)