"""Synthetic multi-dependency Event evidence integration; no site I/O."""
import copy
import unittest
from siraj_research.setup.event_integrity_bundle import prepare_bundle, verify_transition, PlanError
from siraj_research.setup.event_reference_review import REQUIRED_AREAS,discover


def row(dt,name,**values): return {'doctype':dt,'name':name,'values':values}
def ref(dt,name,type_field,name_field,target,classification='research'):
    return dict(doctype=dt,name=name,type_field=type_field,name_field=name_field,type_value='Event',target=target,classification=classification)

class EventIntegrityTest(unittest.TestCase):
    def setUp(self):
        self.files=[{'path':'app/hooks.py','text':'doc_events = {"Event": "calendar"}'},
                    {'path':'app/report/report.py','text':'link = "Event"'}]
        self.decisions=[dict(index=i,classification='shared',evidence='synthetic review') for i in range(len(discover(self.files)['findings']))]
        self.events=[dict(name='r',classification='research'),dict(name='c',classification='calendar')]
        self.rows=[row('Event','r',title='Research',custom='value',owner='a',modified='before'),row('Event','c',subject='Calendar'),
                   row('File','f',attached_to_doctype='Event',attached_to_name='r',url='private'),
                   row('Comment','m',reference_doctype='Event',reference_name='r',text='comment'),
                   row('Evidence','e',parenttype='Event',parent='r',parentfield='evidence',idx=1),
                   row('Relationship','x',subject_type='Event',subject='c')]
        self.refs=[ref('File','f','attached_to_doctype','attached_to_name','r'),ref('Comment','m','reference_doctype','reference_name','r'),
                   ref('Evidence','e','parenttype','parent','r'),ref('Relationship','x','subject_type','subject','c','calendar')]
        self.coverage={x:'reviewed' for x in REQUIRED_AREAS}
        fields=[{'fieldname':'title','fieldtype':'Data'},{'fieldname':'custom','fieldtype':'Data'}]
        self.source={'name':'Event','module':'Siraj Research','fields':fields}; self.target={'name':'SIRAJ Research Event','module':'Siraj Research','fields':copy.deepcopy(fields)}
    def make(self): return prepare_bundle(self.files,self.decisions,self.events,self.refs,self.rows,self.coverage,self.source,self.target)
    def transition(self,p,**overrides):
        kw={'files':self.files,'events':self.events,'references':self.refs,'source_meta':self.source,'target_meta':self.target,'rows':self.rows}
        kw.update(overrides); return verify_transition(p['bundle'],p['fingerprint'],**kw)
    def test_integrated_rehearsal_repeats_and_reverses_without_mutation(self):
        before=copy.deepcopy((self.files,self.decisions,self.events,self.refs,self.rows,self.source,self.target)); p=self.make()
        self.assertEqual(p['status'],'fixture_ready'); self.assertFalse(p['execution_ready'])
        result=self.transition(p); self.assertEqual(result['state'],'projected'); self.assertFalse(result['execution_ready'])
        self.assertEqual(self.transition(p,rows=result['rows'])['state'],'already_projected')
        restored=self.transition(p,rows=result['rows'],reverse=True); self.assertEqual(restored['state'],'reversed')
        self.assertEqual((self.files,self.decisions,self.events,self.refs,self.rows,self.source,self.target),before)
    def test_stale_source_destination_metadata_code_and_reference_rejected(self):
        p=self.make(); after=self.transition(p)['rows']
        changed=copy.deepcopy(self.rows); changed[0]['values']['title']='changed'
        destination=copy.deepcopy(after); next(x for x in destination if x['doctype']=='SIRAJ Research Event')['values']['custom']='modified'
        metadata=copy.deepcopy(self.target); metadata['fields'][1]['fieldtype']='Text'
        refs=copy.deepcopy(self.refs); refs[0]['target']='c'
        for kwargs in ({'rows':changed},{'rows':destination,'reverse':True},{'target_meta':metadata},{'files':[{'path':'app/hooks.py','text':'changed'}]},{'references':refs}):
            with self.subTest(kwargs=kwargs), self.assertRaises(PlanError): self.transition(p,**kwargs)
    def test_tampered_bundle_or_checksum_rejected(self):
        p=self.make(); p['bundle']['journal']['before'][0]['values']['custom']='tampered'
        with self.assertRaises(PlanError): self.transition(p)
        p=self.make(); p['fingerprint']='0'*64
        with self.assertRaises(PlanError): self.transition(p)
    def test_ambiguous_evidence_or_custom_schema_blocks(self):
        decisions=copy.deepcopy(self.decisions); decisions[0]['classification']='ambiguous'
        p=prepare_bundle(self.files,decisions,self.events,self.refs,self.rows,self.coverage,self.source,self.target)
        self.assertEqual(p['status'],'blocked'); self.assertIsNone(p['bundle'])
        target=copy.deepcopy(self.target); target['fields'].pop()
        p=prepare_bundle(self.files,self.decisions,self.events,self.refs,self.rows,self.coverage,self.source,target)
        self.assertEqual(p['status'],'blocked'); self.assertFalse(p['gates']['schema'])

if __name__=='__main__': unittest.main()
