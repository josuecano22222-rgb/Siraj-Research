"""Pure coordinate decisions and guarded reversal, no real site/data."""
import copy
import unittest
from siraj_research.setup.coordinate_transition import audit,prepare,transition,PlanError

def row(name,latitude,longitude,dt='Place'):
    return {'doctype':dt,'name':name,'values':{'latitude':latitude,'longitude':longitude,'geometry_source':'fixture','owner':'owner'}}
def decision(name,orientation='lat_lon',zero='not_zero',dt='Place'):
    return {'doctype':dt,'name':name,'orientation':orientation,'zero':zero}

class CoordinateTransitionTests(unittest.TestCase):
    def test_boundaries_unicode_precision_and_numeric_values(self):
        rows=[row('edge','-90.000','180.000'),row('unicode','٣٣٫١٢٣٤٥٦٧٨٩٠١٢٣٤٥','۴۴٫۲۵'),row('numeric',1e-7,20)]
        result=prepare(rows,[decision('edge'),decision('unicode'),decision('numeric')]); p={x['name']:x for x in result['report']['proposals']}
        self.assertEqual((p['edge']['latitude'],p['edge']['longitude']),('-90','180'))
        self.assertEqual((p['unicode']['latitude'],p['unicode']['longitude']),('33.123456789012345','44.25'))
        self.assertEqual(p['numeric']['latitude'],'0.0000001'); self.assertFalse(result['execution_ready'])
    def test_blank_partial_invalid_and_boundary_overflow(self):
        rows=[row('empty',None,''),row('partial','1',None),row('bad','foo','2'),row('over','90.0000000000000000001','181'),row('bool',True,2),row('exp','1e-7',2)]
        report=audit(rows,[]); self.assertEqual(report['counts']['both_blank'],1)
        self.assertEqual({x['kind'] for x in report['issues']},{'partial_pair','invalid_coordinate','out_of_range'})
        with self.assertRaises(PlanError): prepare(rows,[])
    def test_swap_and_zero_require_explicit_review(self):
        rows=[row('swap','120','40'),row('zero',0,0),row('both_possible','10','20')]
        report=audit(rows,[]); self.assertTrue(all(i['kind']=='orientation_unreviewed' for i in report['issues']))
        result=prepare(rows,[decision('swap','swap'),decision('zero',zero='preserve'),decision('both_possible')])
        proposals={r['name']:r for r in result['report']['proposals']}
        self.assertEqual((proposals['swap']['latitude'],proposals['swap']['longitude']),('40','120'))
        self.assertEqual(proposals['zero']['latitude'],'0')
        with self.assertRaises(PlanError): prepare(rows,[decision('swap'),decision('zero'),decision('both_possible')])
    def test_original_types_and_provenance_recovered_idempotently(self):
        rows=[row('r',33.125,' ٤٤٫٥٠ '),row('blank',None,''),row('other',4,5,'Person')]
        decisions=[decision('r'),decision('other',dt='Person')]; original=copy.deepcopy((rows,decisions))
        manifest=prepare(rows,decisions)['manifest']; projected=transition(rows,manifest)
        self.assertEqual(projected['state'],'projected'); self.assertEqual(transition(projected['rows'],manifest)['state'],'already_projected')
        self.assertEqual(transition(projected['rows'],manifest,reverse=True)['rows'],rows)
        self.assertEqual(transition(rows,manifest,reverse=True)['state'],'already_reversed')
        self.assertEqual((rows,decisions),original)
    def test_conflicts_tampering_missing_and_duplicate_fail_closed(self):
        rows=[row('r','1','2')]; m=prepare(rows,[decision('r')])['manifest']; after=transition(rows,m)['rows']
        changed=copy.deepcopy(after); changed[0]['values']['longitude']='3'
        for bad in (changed,[],after+[row('new','1','2')]):
            with self.subTest(bad=bad),self.assertRaises(PlanError): transition(bad,m,reverse=True)
        tampered=copy.deepcopy(m); tampered['after'][0]['values']['latitude']='9'
        with self.assertRaises(PlanError): transition(rows,tampered)
        with self.assertRaises(PlanError): prepare(rows,[decision('r'),decision('r')])
        self.assertEqual(audit([{'doctype':'Place','name':'x','values':{'latitude':'1'}}],[])['issues'][0]['kind'],'missing_coordinate_field')
        with self.assertRaises(PlanError): prepare([{'doctype':'Place','name':'x','values':{'latitude':'1'}}],[])

if __name__ == '__main__': unittest.main()
