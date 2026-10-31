import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
from build_mac_writer_shortcut import build


class MacWriterTests(unittest.TestCase):
    def test_photo_path_is_a_text_template_for_native_shortcuts(self):
        actions = build()['WFWorkflowActions']
        photo = [a for a in actions if a['WFWorkflowActionIdentifier'].endswith('.documentpicker.open')][1]
        path = photo['WFWorkflowActionParameters']['WFGetFilePath']
        self.assertEqual(path['WFSerializationType'], 'WFTextTokenString')
        self.assertEqual(path['Value']['string'], '\ufffc')
        self.assertEqual(path['Value']['attachmentsByRange']['{0, 1}'],
                         {'Type': 'Variable', 'VariableName': 'Repeat Item'})

    def test_all_files_are_loaded_and_count_checked_before_journal_write(self):
        actions = build()['WFWorkflowActions']
        starts = [i for i, a in enumerate(actions) if a['WFWorkflowActionIdentifier'].endswith('.repeat.each') and a['WFWorkflowActionParameters']['WFControlFlowMode'] == 0]
        self.assertEqual(len(starts), 1)
        start = starts[0]
        group = actions[start]['WFWorkflowActionParameters']['GroupingIdentifier']
        end = next(i for i in range(start + 1, len(actions)) if actions[i]['WFWorkflowActionIdentifier'].endswith('.repeat.each') and actions[i]['WFWorkflowActionParameters']['GroupingIdentifier'] == group)
        inside = actions[start + 1:end]
        self.assertEqual(len(inside), 1)
        self.assertTrue(inside[0]['WFWorkflowActionIdentifier'].endswith('.documentpicker.open'))
        self.assertTrue(inside[0]['WFWorkflowActionParameters']['WFFileErrorIfNotFound'])
        result_id = actions[end]['WFWorkflowActionParameters']['UUID']
        journal = next(a for a in actions[end + 1:] if 'mediaItems' in a['WFWorkflowActionParameters'])
        self.assertEqual(journal['WFWorkflowActionParameters']['mediaItems']['Value']['OutputUUID'], result_id)
        self.assertEqual(journal['WFWorkflowActionParameters']['WFInput'], journal['WFWorkflowActionParameters']['mediaItems'])
        self.assertEqual(journal['WFWorkflowActionParameters']['mediaItems']['Value']['OutputName'], 'Repeat Results')
        between = actions[end + 1:actions.index(journal)]
        self.assertTrue(any(a['WFWorkflowActionIdentifier'].endswith('.exit') for a in between))
        self.assertTrue(any(a['WFWorkflowActionIdentifier'].endswith('.count') and a['WFWorkflowActionParameters']['WFInput']['Value']['OutputUUID'] == result_id for a in between))
        self.assertNotIn('title', journal['WFWorkflowActionParameters'])

    def test_creating_entries_does_not_try_to_open_them(self):
        journal = [a for a in build()['WFWorkflowActions'] if a['WFWorkflowActionIdentifier'] == 'com.apple.journal.CreateEntryIntent']
        self.assertEqual(len(journal), 2)
        for action in journal:
            self.assertIs(action['WFWorkflowActionParameters']['OpenWhenRun'], False)

    def test_v2_payload_required_and_text_only_branch_has_no_media(self):
        actions = build()['WFWorkflowActions']
        self.assertTrue(any(a['WFWorkflowActionParameters'].get('WFConditionalActionString') == 'stoic-mac-bridge-v2' for a in actions))
        self.assertTrue(any(a['WFWorkflowActionParameters'].get('WFDictionaryKey') == 'attachmentFileNames' for a in actions))
        journal = [a for a in actions if a['WFWorkflowActionIdentifier'] == build()['WFWorkflowActions'][-2]['WFWorkflowActionIdentifier']]
        self.assertEqual(len(journal), 2)
        self.assertNotIn('mediaItems', journal[0]['WFWorkflowActionParameters'])
        self.assertNotIn('WFInput', journal[0]['WFWorkflowActionParameters'])
        self.assertIn('mediaItems', journal[1]['WFWorkflowActionParameters'])

from test_batch import OfflineBatch, Stopped


class WriterSim(OfflineBatch):
    def __init__(self, names, files, declared_count=None):
        super().__init__({'schema': 'stoic-mac-bridge-v2', 'date': '2001-02-04T12:00:00Z', 'text': 'Synthetic',
                          'attachmentCount': len(names) if declared_count is None else declared_count,
                          'attachmentFileNames': names})
        self.files = files

    def dictionary_input(self, value):
        return value

    def external(self, ident, params):
        if ident == 'is.workflow.actions.documentpicker.open':
            path = self.value(params['WFGetFilePath'])
            return self.payload if path == 'entry.json' else self.files[path]
        raise AssertionError(ident)

    def run(self, actions):
        index = 0
        while index < len(actions):
            action = actions[index]
            params = action['WFWorkflowActionParameters']
            ident = action['WFWorkflowActionIdentifier']
            if ident.endswith('.repeat.each') or ident.endswith('.conditional'):
                end = next(i for i in range(index + 1, len(actions))
                           if actions[i]['WFWorkflowActionParameters'].get('GroupingIdentifier') == params['GroupingIdentifier']
                           and actions[i]['WFWorkflowActionParameters'].get('WFControlFlowMode') == 2)
                if ident.endswith('.repeat.each'):
                    results = []
                    for item in self.value(params['WFInput']):
                        self.item = item
                        self.run(actions[index + 1:end])
                        results.append(self.outputs[actions[end - 1]['WFWorkflowActionParameters']['UUID']])
                    self.outputs[actions[end]['WFWorkflowActionParameters']['UUID']] = results
                else:
                    super().run(actions[index:end + 1])
                index = end + 1
            else:
                super().run([action])
                index += 1


class MacWriterBehaviorTests(unittest.TestCase):
    def test_multiple_photos_create_one_entry_in_list_order(self):
        sim = WriterSim(['b.png', 'a.png', 'c.heic'], {'a.png': 'A', 'b.png': 'B', 'c.heic': 'C'})
        sim.run(build()['WFWorkflowActions'])
        self.assertEqual(len(sim.writes), 1)
        self.assertEqual(sim.writes[0]['mediaItems'], ['B', 'A', 'C'])
        self.assertEqual(sim.writes[0]['entryDate'], sim.payload['date'])
        self.assertEqual(sim.writes[0]['message'], 'Synthetic')

    def test_missing_later_photo_never_creates_partial_entry(self):
        sim = WriterSim(['a.png', 'missing.png'], {'a.png': 'A'})
        with self.assertRaises(KeyError):
            sim.run(build()['WFWorkflowActions'])
        self.assertEqual(sim.writes, [])

    def test_mismatched_list_count_stops_before_write(self):
        sim = WriterSim(['a.png'], {'a.png': 'A'}, declared_count=2)
        with self.assertRaises(Stopped):
            sim.run(build()['WFWorkflowActions'])
        self.assertEqual(sim.writes, [])

    def test_zero_photos_creates_text_entry(self):
        sim = WriterSim([], {})
        sim.run(build()['WFWorkflowActions'])
        self.assertEqual(len(sim.writes), 1)
        self.assertNotIn('mediaItems', sim.writes[0])
