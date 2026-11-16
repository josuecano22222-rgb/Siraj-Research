"""Pure planning tests only; these do not run Frappe or a migration."""
import copy
import unittest
from siraj_research.setup.event_transition_plan import PlanError, prepare_transition


def ref(target='r', classification='research', **kwargs):
    result = dict(doctype='Relationship', name='link', type_field='subject_type',
                  name_field='subject', type_value='Event', target=target, classification=classification)
    result.update(kwargs)
    return result


class TransitionPlanTests(unittest.TestCase):
    def setUp(self):
        self.events = [dict(name='r', classification='research'), dict(name='c', classification='calendar')]

    def test_mixed_events_and_reference_changes_are_deterministic_without_mutation(self):
        refs = [ref(), ref('c', 'calendar', name='calendar-link'),
                ref('r', 'research', doctype='File', name='attachment', type_field='attached_to_doctype', name_field='attached_to_name')]
        inputs = copy.deepcopy((self.events, refs))
        result = prepare_transition(self.events, refs, [])
        self.assertEqual((self.events, refs), inputs)
        self.assertEqual(result['counts'], dict(research_events=1, calendar_events=1, references_reviewed=3, reference_changes=2))
        self.assertEqual(result['candidate_copies'][0]['target_name'], 'r')
        self.assertEqual([item['doctype'] for item in result['candidate_reference_changes']], ['File', 'Relationship'])
        self.assertTrue(all(x['expected_type'] == 'Event' and x['new_type'] == 'SIRAJ Research Event' for x in result['candidate_reference_changes']))
        self.assertIn('not migration approval', result['warning'])

    def test_empty_inputs_are_not_proof_of_safety(self):
        result = prepare_transition([], [], [])
        self.assertEqual(result['candidate_copies'], [])
        self.assertIn('not verified', result['warning'])

    def test_target_collision_and_duplicate_source_fail(self):
        for events, names in [(self.events, ['r']), (self.events + [self.events[0]], []), (self.events, ['unused', 'unused'])]:
            with self.subTest(events=events, names=names), self.assertRaises(PlanError):
                prepare_transition(events, [], names)

    def test_ambiguous_missing_and_orphan_targets_fail(self):
        for events, refs in [([dict(name='r', classification='unknown')], []),
                             (self.events, [ref('missing')]), (self.events, [ref('r', 'calendar')])]:
            with self.subTest(events=events, refs=refs), self.assertRaises(PlanError):
                prepare_transition(events, refs, [])

    def test_duplicate_and_unsupported_fields_fail(self):
        for refs in [[ref(), ref()], [ref(type_value='Other')], [ref(name_field='subject_type')], [ref(type_field='')], [ref(), ref(type_field='other_type', name_field='subject')]]:
            with self.subTest(refs=refs), self.assertRaises(PlanError):
                prepare_transition(self.events, refs, [])

    def test_bad_container_and_extra_unreviewed_fields_fail(self):
        for events, refs, target in [(None, [], []), (self.events, {}, []),
                                     (self.events, [], ['']), ([dict(name='r', classification='research', content='x')], [], []),
                                     (self.events, [dict(ref(), extra='x')], [])]:
            with self.subTest(events=events, refs=refs, target=target), self.assertRaises(PlanError):
                prepare_transition(events, refs, target)


if __name__ == '__main__':
    unittest.main()
