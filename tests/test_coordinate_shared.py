"""Shared exact-decimal parsing across fixture audit and transition."""
import unittest
from decimal import Decimal, localcontext
from siraj_research.utils.coordinates import parse_coordinate, bounded_coordinate, map_number
from siraj_research.setup.coordinate_transition import audit
import test_visualization

class SharedCoordinateTests(unittest.TestCase):
    def test_ranges_unicode_and_legacy_numeric(self):
        for value, limit, expected in [('٣٣٫٢٥',90,Decimal('33.25')),('۴۴٫۵',180,Decimal('44.5')),(-90,90,Decimal('-90')),('180.0',180,Decimal('180')),(1e-7,90,Decimal('1e-7')),(Decimal('1E-7'),90,Decimal('1e-7'))]:
            with self.subTest(value=value): self.assertEqual(bounded_coordinate(value,limit),('valid',expected))
        for value in (True,'1e-7','NaN','180.00000000001'):
            with self.subTest(value=value): self.assertEqual(bounded_coordinate(value,180),('invalid',None))
        self.assertEqual(parse_coordinate('  '),('blank',None))
    def test_exact_boundary_is_not_rounded_by_decimal_context(self):
        with localcontext() as ctx:
            ctx.prec=5
            self.assertIsNone(map_number('90.'+'0'*50+'1',90))
            self.assertEqual(map_number('90.'+'0'*50,90),90)
    def test_explorer_uses_shared_parser_and_excludes_ambiguous_zero(self):
        viz = test_visualization.load_visualization(test_visualization.FakeFrappe())
        for value,limit in [('٣٣٫٢٥',90),('90.'+'0'*50+'1',90),(1e-7,90),('1e-7',90),(Decimal('1E-7'),90)]:
            with self.subTest(value=value): self.assertEqual(viz._coordinate(value,limit),map_number(value,limit))
        self.assertFalse(viz._valid_point('0','0'))
        self.assertTrue(viz._valid_point('0','20'))

    def test_planner_and_shared_parser_agree_and_require_review(self):
        rows=[{'doctype':'Place','name':'x','values':{'latitude':'٣٣٫٢٥','longitude':'۴۴٫۵'}}]
        decision=[{'doctype':'Place','name':'x','orientation':'lat_lon','zero':'not_zero'}]
        report=audit(rows,decision); self.assertEqual(report['proposals'][0]['latitude'],'33.25')
        self.assertEqual(report['proposals'][0]['longitude'],'44.5'); self.assertFalse(report['execution_ready'])
        self.assertEqual(audit(rows,[])['issues'][0]['kind'],'orientation_unreviewed')

if __name__=='__main__': unittest.main()
