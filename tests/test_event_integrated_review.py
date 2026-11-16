"""Combined fixture coverage; no Frappe/database, hooks or site access."""
import copy
import unittest
from siraj_research.setup.event_integrated_review import review,transition,PlanError
from siraj_research.setup.event_compatibility import CORE_FIELDS, RESEARCH_FIELDS
from siraj_research.setup.event_reference_review import REQUIRED_AREAS,discover

def meta(name,module,fields): return {'name':name,'module':module,'fields':[{'fieldname':n,'fieldtype':t,**({'options':o} if o is not None else {})} for n,(t,o) in fields.items()]}
def row(dt,name,**values): return dict(doctype=dt,name=name,values=values)

class IntegratedReviewTest(unittest.TestCase):
    def setUp(self):
        self.core=meta('Event','Desk',CORE_FIELDS); self.source=meta('Event','Siraj Research',RESEARCH_FIELDS)
        self.target=meta('SIRAJ Research Event','Siraj Research',RESEARCH_FIELDS)
        self.files=[{'path':'app/hooks.py','text':'hook = "Event"'}]
        self.decisions=[{'index':i,'classification':'shared','evidence':'fixture'} for i in range(len(discover(self.files)['findings']))]
        self.events=[{'name':'r','classification':'research'},{'name':'c','classification':'calendar'}]
        self.rows=[row('Event','r',title_ar='R',custom='original'),row('Event','c',subject='calendar'),
                   row('File','f',attached_to_doctype='Event',attached_to_name='r'),
                   row('Comment','m',reference_doctype='Event',reference_name='r'),row('Evidence','e',parenttype='Event',parent='r')]
        self.refs=[dict(doctype='File',name='f',type_field='attached_to_doctype',name_field='attached_to_name',type_value='Event',target='r',classification='research'),
                   dict(doctype='Comment',name='m',type_field='reference_doctype',name_field='reference_name',type_value='Event',target='r',classification='research'),
                   dict(doctype='Evidence',name='e',type_field='parenttype',name_field='parent',type_value='Event',target='r',classification='research')]
        self.refmeta=[self.source,{'name':'File','fields':[{'fieldname':'attached_to_doctype','fieldtype':'Link','options':'DocType'},{'fieldname':'attached_to_name','fieldtype':'Dynamic Link','options':'attached_to_doctype'}]},
                      {'name':'Comment','fields':[{'fieldname':'reference_doctype','fieldtype':'Link','options':'DocType'},{'fieldname':'reference_name','fieldtype':'Dynamic Link','options':'reference_doctype'}]},
                      {'name':'Evidence','fields':[],'istable':1}]
        self.refdec=[{'doctype':x['doctype'],'name':x['name'],'field':x['name_field'],'classification':'research','evidence':'fixture'} for x in self.refs]
        self.coverage={x:'reviewed' for x in REQUIRED_AREAS}; self.schema={'database':'fixture','columns':['name','title_ar']}; self.hooks={'calendar':['Event'],'permissions':'fixture'}
    def params(self): return dict(files=self.files,code_decisions=self.decisions,events=self.events,references=self.refs,rows=self.rows,coverage=self.coverage,source_meta=self.source,target_meta=self.target,core_reference_meta=self.core,reference_metadata=self.refmeta,reference_decisions=self.refdec,physical_schema=self.schema,hook_inventory=self.hooks)
    def args(self): return dict(files=self.files,events=self.events,references=self.refs,rows=self.rows,source_meta=self.source,target_meta=self.target,core_reference_meta=self.core,reference_metadata=self.refmeta,physical_schema=self.schema,hook_inventory=self.hooks)
    def test_full_review_apply_repeat_and_rollback(self):
        original=copy.deepcopy(self.params()); r=review(**self.params()); self.assertEqual(r['status'],'fixture_ready'); self.assertFalse(r['execution_ready'])
        projected=transition(r['bundle'],r['checksum'],**self.args()); self.assertEqual(projected['state'],'projected')
        args=self.args(); args['rows']=projected['rows']; self.assertEqual(transition(r['bundle'],r['checksum'],**args)['state'],'already_projected')
        self.assertEqual(transition(r['bundle'],r['checksum'],reverse=True,**args)['state'],'reversed')
        self.assertEqual(self.params(),original)
    def test_stale_schema_hooks_records_and_rollback_refuse(self):
        r=review(**self.params()); projected=transition(r['bundle'],r['checksum'],**self.args())
        changed=copy.deepcopy(projected['rows']); next(x for x in changed if x['doctype']=='File')['values']['attached_to_name']='other'
        tests=[dict(physical_schema={'database':'changed'}),dict(hook_inventory={'calendar':[]}),dict(reference_metadata=[]),dict(rows=changed,reverse=True)]
        for override in tests:
            args=self.args(); args.update(override)
            with self.subTest(override=override), self.assertRaises(PlanError): transition(r['bundle'],r['checksum'],**args)
    def test_ambiguous_or_missing_reference_and_wrong_core_are_blocked(self):
        args=self.params(); args['reference_decisions']=[]; result=review(**args)
        self.assertEqual(result['status'],'blocked'); self.assertIn('reference_review_incomplete',result['blockers'])
        args=self.params(); args['core_reference_meta']=dict(self.core,module='Siraj Research')
        self.assertIn('selected_compatibility_contract_failed',review(**args)['blockers'])
        args=self.params(); args['physical_schema']={}
        with self.assertRaises(PlanError): review(**args)
    def test_omitted_or_unhandled_discovered_reference_is_blocked(self):
        args=self.params(); args['references']=self.refs[:-1]
        self.assertIn('reference_projection_mismatch',review(**args)['blockers'])
        args=self.params(); args['rows']=self.rows+[row('Custom','x',historical_event='r')]
        args['reference_metadata']=self.refmeta+[{'name':'Custom','fields':[{'fieldname':'historical_event','fieldtype':'Link','options':'Event'}]}]
        args['reference_decisions']=self.refdec+[{'doctype':'Custom','name':'x','field':'historical_event','classification':'research','evidence':'fixture'}]
        self.assertIn('direct_link_transition_unsupported',review(**args)['blockers'])
        args=self.params(); args['reference_metadata']=self.refmeta+[{'name':'EmptyCustom','fields':[{'fieldname':'event','fieldtype':'Link','options':'Event'}]}]
        self.assertIn('direct_link_transition_unsupported',review(**args)['blockers'])

    def test_source_metadata_mismatch_and_event_owned_reference_blocked(self):
        args=self.params(); args['reference_metadata']=copy.deepcopy(self.refmeta)
        args['reference_metadata'][0]['fields']=[]
        self.assertIn('source_reference_metadata_mismatch',review(**args)['blockers'])
        args=self.params(); args['source_meta']=copy.deepcopy(self.source)
        args['source_meta']['fields'] += [{'fieldname':'link_type','fieldtype':'Link','options':'DocType'}, {'fieldname':'link_name','fieldtype':'Dynamic Link','options':'link_type'}]
        args['reference_metadata']=copy.deepcopy(self.refmeta); args['reference_metadata'][0]=args['source_meta']
        args['rows']=copy.deepcopy(self.rows); args['rows'][0]['values'].update(link_type='Event',link_name='c'); args['rows'][1]['values'].update(link_type=None,link_name=None)
        args['reference_decisions']=self.refdec+[{'doctype':'Event','name':'r','field':'link_name','classification':'calendar','evidence':'fixture'}]
        args['references']=self.refs+[dict(doctype='Event',name='r',type_field='link_type',name_field='link_name',type_value='Event',target='c',classification='calendar')]
        self.assertIn('projection_rejected',review(**args)['blockers'])

    def test_checksum_tamper_and_stale_source(self):
        r=review(**self.params()); r['bundle']['hook_inventory']['calendar']=[]
        with self.assertRaises(PlanError): transition(r['bundle'],r['checksum'],**self.args())
        r=review(**self.params()); args=self.args(); args['rows']=copy.deepcopy(self.rows); args['rows'][0]['values']['custom']='changed'
        with self.assertRaises(PlanError): transition(r['bundle'],r['checksum'],**args)

if __name__=='__main__': unittest.main()
