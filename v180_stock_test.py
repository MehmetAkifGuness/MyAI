import unittest
from v180_stock import MIN_STOCK

class StockTests(unittest.TestCase):
    def test_minimum_stock(self):
        self.assertEqual(MIN_STOCK, 1)