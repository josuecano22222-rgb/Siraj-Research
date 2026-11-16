"""Synthetic Event journal checks. No Frappe or persistent changes."""
import copy
import unittest
from siraj_research.setup.event_rehearsal_journal import prepare, transition, PlanError


def row(dt,name,**values): return dict(doctype=dt,name=name,values=values)
def ref(dt,name,type_field,name_field,target,classification='research'):
    return dict(doctype=dt,name=name,type_field=type_field,name_field=name_field,type_value='Event',target=target,classification=classification)


class JournalTest(unittest.TestCase):
    def setUp(self):
        self.events=[dict(name='r',classification='research'),dict(name='c',classification='calendar')]
        self.rows=[row('Event','r',title='one',custom='value',owner='owner',modified='before'),row('Event','c',subject='meeting'),
                   row('File','f',attached_to_doctype='Event',attached_to_name='r',private=1),
                   row('Comment','m',reference_doctype='Event',reference_name='r',content='audit'),
                   row('Evidence','e',parenttype='Event',parent='r',parentfield='evidence',idx=1),
                   row('Relationship','link',subject_type='Event',subject='c')]
        self.refs=[ref('File','f','attached_to_doctype','attached_to_name','r'),ref('Comment','m','reference_doctype','reference_name','r'),
                   ref('Evidence','e','parenttype','parent','r'),ref('Relationship','link','subject_type','subject','c','calendar')]
    def test_apply_repeat_reverse_and_repeat_are_non_mutating(self):
        original=copy.deepcopy((self.events,self.refs,self.rows)); prepared=prepare(*original)
        manifest=prepared['manifest']; out=transition(self.rows,manifest); self.assertFalse(out['execution_ready'])
        self.assertEqual(out['state'],'projected'); self.assertEqual(transition(out['rows'],manifest)['state'],'already_projected')
        back=transition(out['rows'],manifest,reverse=True); self.assertEqual(back['state'],'reversed')
        self.assertEqual(sorted(back['rows'],key=lambda x:(x['doctype'],x['name'])),sorted(self.rows,key=lambda x:(x['doctype'],x['name'])))
        self.assertEqual(transition(back['rows'],manifest,reverse=True)['state'],'already_reversed')
        self.assertEqual((self.events,self.refs,self.rows),original)
    def test_partial_missing_added_and_changed_fail_closed(self):
        manifest=prepare(self.events,self.refs,self.rows)['manifest']
        after=transition(self.rows,manifest)['rows']
        changed=copy.deepcopy(after); next(x for x in changed if x['doctype']=='File')['values']['private']=0
        for conflict in (changed,after[:-1],after+[row('Person','new')], self.rows[:-1]):
            with self.subTest(conflict=conflict), self.assertRaises(PlanError): transition(conflict,manifest,reverse=True)
    def test_manifest_tamper_and_duplicate_reference_fail(self):
        manifest=prepare(self.events,self.refs,self.rows)['manifest']; manifest['after'][0]['values']['tamper']=1
        with self.assertRaises(PlanError): transition(self.rows,manifest)
        with self.assertRaises(PlanError): prepare(self.events,self.refs+[self.refs[0]],self.rows)
    def test_ambiguous_calendar_and_missing_related_rows_rejected(self):
        for events,refs,rows in [(self.events+[dict(name='u',classification='ambiguous')],self.refs,self.rows),
                                 (self.events,self.refs,self.rows[1:]),
                                 (self.events,self.refs+[ref('File','missing','kind','target','r')],self.rows),
                                 (self.events,self.refs,self.rows+[row('SIRAJ Research Event','r')])]:
            with self.subTest(events=events,refs=refs), self.assertRaises(PlanError): prepare(events,refs,rows)

if __name__ == '__main__': unittest.main()
