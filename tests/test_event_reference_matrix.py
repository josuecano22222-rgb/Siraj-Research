"""Synthetic effective metadata and links only, never an actual Frappe site."""
import copy
import unittest
from siraj_research.setup.event_reference_matrix import inspect, PlanError

def field(name,kind,options=None): return {'fieldname':name,'fieldtype':kind,'options':options}
def meta(name,fields,istable=0): return {'name':name,'fields':fields,'istable':istable}
def row(dt,name,**values): return {'doctype':dt,'name':name,'values':values}
def decision(dt,name,fieldname,classification='research'):
    return {'doctype':dt,'name':name,'field':fieldname,'classification':classification,'evidence':'fixture review'}

class ReferenceMatrixTest(unittest.TestCase):
    def setUp(self):
        self.metadata=[meta('Event',[]),meta('File',[field('attached_to_doctype','Link','DocType'),field('attached_to_name','Dynamic Link','attached_to_doctype')]),
                       meta('Comment',[field('reference_doctype','Link','DocType'),field('reference_name','Dynamic Link','reference_doctype')]),
                       meta('Evidence',[],1),meta('Custom',[field('historical_event','Link','Event')]),
                       meta('Relationship',[field('subject_type','Select','Person\nEvent'),field('subject','Dynamic Link','subject_type')])]
        self.events=[{'name':'r','classification':'research'},{'name':'c','classification':'calendar'}]
        self.rows=[row('Event','r',title='research'),row('Event','c',subject='meeting'),
                   row('File','f',attached_to_doctype='Event',attached_to_name='r'),
                   row('Comment','m',reference_doctype='Event',reference_name='r'),
                   row('Evidence','e',parenttype='Event',parent='r',parentfield='evidence'),
                   row('Custom','x',historical_event='r'),row('Relationship','rel',subject_type='Event',subject='c')]
        self.decisions=[decision('File','f','attached_to_name'),decision('Comment','m','reference_name'),
                        decision('Evidence','e','parent'),decision('Custom','x','historical_event'),decision('Relationship','rel','subject','calendar')]
    def test_all_reference_shapes_explicitly_reviewed_without_mutation(self):
        initial=copy.deepcopy((self.metadata,self.rows,self.events,self.decisions)); r=inspect(*initial)
        self.assertEqual(len(r['findings']),5); self.assertEqual(r['issues'],[]); self.assertFalse(r['execution_ready'])
        self.assertEqual({x['kind'] for x in r['findings']},{'direct','dynamic','child'})
        self.assertEqual((self.metadata,self.rows,self.events,self.decisions),initial)
    def test_orphan_empty_ambiguous_missing_and_decision_conflicts(self):
        rows=copy.deepcopy(self.rows); rows[2]['values']['attached_to_name']='lost'; rows[3]['values']['reference_name']=''
        rows[4]['values'].pop('parent'); rows[5]['values']['historical_event']='c'
        events=copy.deepcopy(self.events); events[1]['classification']='ambiguous'
        r=inspect(self.metadata,rows,events,[]); kinds={x['kind'] for x in r['issues']}
        self.assertTrue({'orphan_target','empty_event_target','reference_field_missing','ambiguous_target'} <= kinds)
        result=inspect(self.metadata,self.rows,self.events,[])
        self.assertEqual(sum(x['kind']=='unreviewed_reference' for x in result['issues']),5)
        decisions=copy.deepcopy(self.decisions); decisions[0]['classification']='calendar'
        self.assertIn('reference_classification_conflict',{x['kind'] for x in inspect(self.metadata,self.rows,self.events,decisions)['issues']})
    def test_missing_metadata_bad_selector_and_duplicate_inputs_fail_closed(self):
        meta2=copy.deepcopy(self.metadata); meta2[1]['fields'][1]['options']='missing'
        r=inspect(meta2,self.rows,self.events,self.decisions)
        self.assertIn('dynamic_selector_missing',{x['kind'] for x in r['issues']})
        self.assertIn('metadata_missing',{x['kind'] for x in inspect(self.metadata[:-1],self.rows,self.events,self.decisions)['issues']})
        for metadata,rows,events,decisions in [(self.metadata,self.rows+[self.rows[0]],self.events,self.decisions),
           (self.metadata,self.rows,self.events+[self.events[0]],self.decisions),
           (self.metadata,self.rows,self.events,self.decisions+[self.decisions[0]])]:
            with self.subTest(metadata=metadata), self.assertRaises(PlanError): inspect(metadata,rows,events,decisions)
    def test_missing_source_and_untyped_reference_are_blockers(self):
        rows=copy.deepcopy(self.rows); rows.pop(0); rows[-1]['values']['subject_type']=''
        kinds={i['kind'] for i in inspect(self.metadata,rows,self.events,self.decisions)['issues']}
        self.assertIn('classified_event_missing',kinds); self.assertIn('untyped_target',kinds)
        result=inspect(self.metadata,self.rows,self.events[:-1],self.decisions)
        self.assertIn('event_unclassified',{i['kind'] for i in result['issues']})

    def test_non_event_dynamic_link_not_rewritten(self):
        rows=copy.deepcopy(self.rows); rows[-1]['values']['subject_type']='Person'
        result=inspect(self.metadata,rows,self.events,self.decisions[:-1])
        self.assertFalse(any(x['name']=='rel' for x in result['findings']))

if __name__=='__main__': unittest.main()
