"""Pure Event mapping tests, no Frappe, schema changes or real records."""
import copy
import unittest
from siraj_research.setup.event_schema_compare import PlanError, compare_metadata


def meta(name, fields): return {'name':name,'module':'Siraj Research','fields':fields}
def field(name, kind, **extra): return {'fieldname':name,'fieldtype':kind,**extra}


class SchemaCompareTests(unittest.TestCase):
    def setUp(self):
        self.source = meta('Event',[field('layout','Section Break'),field('title','Data',length=140),
                                    field('place','Link',options='Place'),field('evidence','Table',options='Evidence')])
        self.target = meta('SIRAJ Research Event',copy.deepcopy(self.source['fields']))
    def test_equal_fields_include_child_mapping_and_standard_identity_requirements(self):
        result = compare_metadata(self.source,self.target)
        self.assertTrue(result['selected_attributes_match'])
        self.assertEqual([r['source'] for r in result['mappings']],['evidence','place','title'])
        self.assertIn('owner',result['standard_fields_to_preserve'])
        self.assertIn('not inspected',result['warning'])
    def test_missing_changed_extra_and_reserved_are_reported(self):
        self.target['fields'] = [field('title','Data',length=100), field('place','Link',options='Other'), field('extra','Data'),field('owner','Data')]
        result = compare_metadata(self.source,self.target)
        status = {r['source']:r for r in result['mappings']}
        self.assertEqual(status['evidence']['status'],'missing')
        self.assertEqual(status['title']['differences'],['length'])
        self.assertEqual(status['place']['differences'],['options'])
        self.assertEqual(result['target_only_fields'],['extra','owner'])
        self.assertEqual(result['reserved_name_conflicts'],['owner'])
        self.assertFalse(result['selected_attributes_match'])
    def test_wrong_ownership_and_duplicate_fields_fail(self):
        for change in ('owner','duplicate','identity'):
            target = copy.deepcopy(self.target)
            if change == 'owner': target['module']='Core'
            elif change == 'duplicate': target['fields'].append(field('title','Data'))
            else: target['name']='Event'
            with self.subTest(change=change), self.assertRaises(PlanError): compare_metadata(self.source,target)

if __name__ == '__main__': unittest.main()
