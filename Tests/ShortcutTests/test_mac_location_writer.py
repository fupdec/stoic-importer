import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
from build_mac_location_writer import build, VARIABLE


class LocationWriterTests(unittest.TestCase):
    def test_location_is_reset_before_loading_optional_file(self):
        actions = build(True)['WFWorkflowActions']
        self.assertTrue(actions[0]['WFWorkflowActionIdentifier'].endswith('.nothing'))
        reset = actions[1]['WFWorkflowActionParameters']
        self.assertEqual(reset['WFVariableName'], VARIABLE)
        self.assertEqual(reset['WFInput']['Value']['OutputUUID'], actions[0]['WFWorkflowActionParameters']['UUID'])
        guard = next(i for i, a in enumerate(actions) if a['WFWorkflowActionIdentifier'].endswith('.conditional'))
        load = next(i for i, a in enumerate(actions)
                    if isinstance(a['WFWorkflowActionParameters'].get('WFGetFilePath'), dict))
        self.assertLess(guard, load)
        self.assertTrue(actions[load]['WFWorkflowActionParameters']['WFFileErrorIfNotFound'])
        self.assertTrue(all(a['WFWorkflowActionIdentifier'].startswith('is.workflow.actions.') for a in actions))

    def test_journal_uses_only_prepared_location_and_carrier_is_not_media(self):
        actions = build()['WFWorkflowActions']
        writers = [a['WFWorkflowActionParameters'] for a in actions if a['WFWorkflowActionIdentifier'] == 'com.apple.journal.CreateEntryIntent']
        self.assertEqual(len(writers), 2)
        for writer in writers:
            self.assertEqual(writer['location']['Value'], {'Type': 'Variable', 'VariableName': VARIABLE})
        self.assertEqual(writers[1]['mediaItems']['Value']['OutputName'], 'Repeat Results')
        self.assertFalse(any('currentlocation' in a['WFWorkflowActionIdentifier'] for a in actions))


if __name__ == '__main__':
    unittest.main()
