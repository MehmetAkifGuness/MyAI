import unittest
from v180_pricing import TAX_RATE

class PricingTests(unittest.TestCase):
    def test_tax_rate(self):
        self.assertEqual(TAX_RATE, 0.20)