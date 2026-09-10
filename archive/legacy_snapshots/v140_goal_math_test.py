import unittest
from v140_goal_math import add

class GoalDrivenMathTests(unittest.TestCase):
    def test_add(self):
        self.assertEqual(add(2, 3), 5)