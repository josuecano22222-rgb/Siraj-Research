"""Exact text coordinate bounds independent of Decimal context precision."""

import unittest
from decimal import Decimal, localcontext

from test_visualization import FakeFrappe, load_visualization


class CoordinateBoundaryTest(unittest.TestCase):
	def test_boundary_comparison_does_not_round_long_text(self):
		viz = load_visualization(FakeFrappe())
		for limit in (90, 180):
			for sign in ("", "-"):
				over = sign + str(limit) + "." + "0" * 50 + "1"
				exact = sign + str(limit) + "." + "0" * 50
				with self.subTest(limit=limit, sign=sign), localcontext() as context:
					context.prec = 5
					self.assertIsNone(viz._coordinate(over, limit))
					self.assertEqual(abs(viz._coordinate(exact, limit)), limit)
					self.assertIsNone(viz._coordinate(Decimal(over), limit))


if __name__ == "__main__":
	unittest.main()
