import copy
import json
import unittest
from pathlib import Path
from build_stoic_shortcut import build
from build_ledger_shortcut import LEDGER_SCHEMA
import test_raw_backup as raw_tests
from test_batch import Stopped


class ImportSim(raw_tests.RawSim):
    def __init__(self, files, ledger=None, import_now=True, fail_save=None, fail_write=False, manual=False):
        super().__init__(files, assemble=True)
        self.disk = copy.deepcopy(ledger); self.import_now = import_now
        self.reads = 0; self.saves = 0; self.fail_save = fail_save; self.fail_write = fail_write
        self.manual = manual; self.searches = []

    def menu_choice(self, p):
        if 'Только предпросмотр' in p['WFMenuItems']:
            return 'Импортировать записи' if self.import_now else 'Только предпросмотр'
        if 'Как проверять' in p.get('WFMenuPrompt', ''):
            return 'Также открыть поиск Journal перед новой записью' if self.manual else 'Только UUID-реестр'
        if 'Запись уже есть — пропустить' in p['WFMenuItems']:
            return 'Запись уже есть — пропустить'
        return super().menu_choice(p)

    def dictionary_input(self, value):
        return copy.deepcopy(self.disk) if value == 'ledger-file' else super().dictionary_input(value)

    def journal_write(self, p):
        if self.fail_write: raise OSError('Synthetic ambiguous Journal failure')
        super().journal_write(p)

    def external(self, ident, p):
        if ident.endswith('documentpicker.open'):
            self.reads += 1
            return 'ledger-file' if self.disk is not None else None
        if ident.endswith('documentpicker.save'):
            self.saves += 1
            if self.saves == self.fail_save: raise OSError('Synthetic ledger save failure')
            self.disk = copy.deepcopy(self.value(p['WFInput'])); return 'ledger-file'
        if ident == 'com.apple.journal.SearchEntriesIntent':
            self.searches.append(self.value(p['criteria'])); return None
        if ident.endswith('text.split'): return self.value(p['text']).splitlines()
        if ident.endswith('getitemfromlist'): return self.value(p['WFInput'])[0]
        return super().external(ident, p)


class StoicImportTests(unittest.TestCase):
    def files(self, count=12):
        return {name + '.json': json.dumps(records) for name, records in {
            'answers': [], 'assets': [], 'routines': [],
            'journal-entries': [{'uuid': f'00000000-0000-4000-8000-{i:012d}',
                'timestamp': 1700000000000 + i * 1000, 'text': f'Synthetic {i}\n\nBody {i}'}
                for i in range(count)]}.items()}

    def test_original_zip_first_ten_then_remaining_then_no_repeat(self):
        files = self.files()
        first = ImportSim(files); first.run(build()['WFWorkflowActions'])
        self.assertEqual(len(first.writes), 10)
        self.assertEqual(len(first.disk), 11)
        second = ImportSim(files, ledger=first.disk); second.run(build()['WFWorkflowActions'])
        self.assertEqual(len(second.writes), 2)
        self.assertEqual(len(second.disk), 13)
        self.assertTrue(all(status == 'action-returned' for key, status in second.disk.items() if key != '__schema__'))
        third = ImportSim(files, ledger=second.disk)
        with self.assertRaises(Stopped): third.run(build()['WFWorkflowActions'])
        self.assertEqual(third.writes, [])

    def test_preview_does_not_access_registry_or_create(self):
        sim = ImportSim(self.files(), import_now=False)
        with self.assertRaises(Stopped): sim.run(build()['WFWorkflowActions'])
        self.assertEqual((sim.reads, sim.saves, sim.writes), (0, 0, []))

    def test_review_records_excluded_and_photo_tracks_same_source(self):
        files = raw_tests.RawBackupTests().linked_files()
        answers = json.loads(files['answers.json']); answers[2]['text'] = 'Third answer'
        files['answers.json'] = json.dumps(answers)
        sim = ImportSim(files); sim.run(build()['WFWorkflowActions'])
        self.assertEqual(len(sim.writes), 2)
        self.assertEqual(sim.writes[0]['mediaItems'], [])
        self.assertEqual(sim.writes[1]['mediaItems'], ['media/photo.jpg'])
        self.assertEqual(set(sim.disk), {'__schema__', 'j1', 'r1'})
        self.assertNotIn('a4', sim.disk)

    def test_unresolved_scales_are_not_imported(self):
        sim = ImportSim(raw_tests.RawBackupTests().linked_files()); sim.run(build()['WFWorkflowActions'])
        self.assertEqual(len(sim.writes), 1)
        self.assertEqual(set(sim.disk), {'__schema__', 'j1'})

    def test_pending_unknown_and_invalid_schema_stop_before_writes(self):
        first_id = json.loads(self.files()['journal-entries.json'])[0]['uuid']
        for ledger in [{'__schema__': 'wrong'}, {'__schema__': LEDGER_SCHEMA, first_id: 'pending'},
                       {'__schema__': LEDGER_SCHEMA, first_id: 'unknown'}]:
            sim = ImportSim(self.files(), ledger=ledger)
            with self.assertRaises(Stopped): sim.run(build()['WFWorkflowActions'])
            self.assertEqual(sim.writes, [])
            self.assertEqual(sim.disk, ledger)

    def test_pending_later_in_plan_stops_entire_batch_before_writes(self):
        files = self.files()
        last_id = json.loads(files['journal-entries.json'])[-1]['uuid']
        sim = ImportSim(files, ledger={'__schema__': LEDGER_SCHEMA, last_id: 'pending'})
        with self.assertRaises(Stopped): sim.run(build()['WFWorkflowActions'])
        self.assertEqual(sim.writes, [])

    def test_no_title_body_and_date_reach_one_journal_action(self):
        files = self.files(1)
        records = json.loads(files['journal-entries.json'])
        records[0]['text'] = 'One line only'; records[0]['timestamp'] = 1700000000123
        files['journal-entries.json'] = json.dumps(records)
        sim = ImportSim(files); sim.run(build()['WFWorkflowActions'])
        self.assertEqual(len(sim.writes), 1)
        self.assertNotIn('title', sim.writes[0])
        self.assertEqual(sim.writes[0]['message'], 'One line only')
        self.assertTrue(sim.writes[0]['entryDate'].endswith('.123+00:00'))

    def test_failed_pending_save_never_calls_journal(self):
        sim = ImportSim(self.files(), fail_save=2)
        with self.assertRaises(OSError): sim.run(build()['WFWorkflowActions'])
        self.assertEqual(sim.writes, [])

    def test_journal_failure_leaves_pending_and_blocks_retry(self):
        files = self.files(); sim = ImportSim(files, fail_write=True)
        with self.assertRaises(OSError): sim.run(build()['WFWorkflowActions'])
        self.assertIn('pending', sim.disk.values())
        retry = ImportSim(files, ledger=sim.disk)
        with self.assertRaises(Stopped): retry.run(build()['WFWorkflowActions'])
        self.assertEqual(retry.writes, [])

    def test_failed_receipt_after_journal_blocks_retry(self):
        files = self.files(); sim = ImportSim(files, fail_save=3)
        with self.assertRaises(OSError): sim.run(build()['WFWorkflowActions'])
        self.assertEqual(len(sim.writes), 1)
        self.assertIn('pending', sim.disk.values())
        retry = ImportSim(files, ledger=sim.disk)
        with self.assertRaises(Stopped): retry.run(build()['WFWorkflowActions'])
        self.assertEqual(retry.writes, [])

    def test_late_invalid_source_stops_before_any_write(self):
        files = self.files(); records = json.loads(files['journal-entries.json'])
        records[-1]['timestamp'] = None; files['journal-entries.json'] = json.dumps(records)
        sim = ImportSim(files)
        with self.assertRaises(Stopped): sim.run(build()['WFWorkflowActions'])
        self.assertEqual(sim.writes, [])
        self.assertEqual(sim.reads, 0)

    def test_manual_confirmation_records_existing_without_writing(self):
        sim = ImportSim(self.files(2), manual=True); sim.run(build()['WFWorkflowActions'])
        self.assertEqual(len(sim.searches), 2)
        self.assertEqual(sim.writes, [])
        self.assertTrue(all(v == 'manual-confirmed' for k, v in sim.disk.items() if k != '__schema__'))

    def test_static_workflow_uses_only_native_actions_and_valid_references(self):
        seen = set()
        def refs(value):
            if isinstance(value, dict):
                if 'OutputUUID' in value: yield value['OutputUUID']
                for child in value.values(): yield from refs(child)
            elif isinstance(value, list):
                for child in value: yield from refs(child)
        for action in build()['WFWorkflowActions']:
            ident = action['WFWorkflowActionIdentifier']
            self.assertTrue(ident.startswith('is.workflow.actions.') or ident in [
                'com.apple.journal.CreateEntryIntent', 'com.apple.journal.SearchEntriesIntent'])
            self.assertFalse(any(word in ident for word in ['script', 'runworkflow', 'download', 'url', 'web']))
            params = action['WFWorkflowActionParameters']
            for output in refs(params): self.assertIn(output, seen)
            seen.add(params['UUID'])

    def test_registry_file_parameters_match_native_editor_export(self):
        fixture = json.loads((Path(__file__).parent / 'Fixtures/native_file_actions.json').read_text())
        actions = build()['WFWorkflowActions']
        saves = [a['WFWorkflowActionParameters'] for a in actions if a['WFWorkflowActionIdentifier'] == fixture['save']['identifier']]
        loads = [a['WFWorkflowActionParameters'] for a in actions if a['WFWorkflowActionIdentifier'] == fixture['load']['identifier']]
        self.assertTrue(saves and loads)
        for params in saves:
            for name in ['WFAskWhereToSave', 'WFSaveFileOverwrite']:
                self.assertEqual(params[name], fixture['save']['scalars'][name])
            self.assertEqual(params['WFFileDestinationPath'], 'stoic-import-ledger.json')
            self.assertEqual(params['WFInput']['Value']['VariableName'], 'StoicLedger')
            self.assertIn('WFFolder', params)
        for params in loads:
            self.assertEqual(params['WFFileErrorIfNotFound'], fixture['load']['scalars']['WFFileErrorIfNotFound'])
            self.assertEqual(params['WFGetFilePath'], 'stoic-import-ledger.json')
            self.assertIn('WFFile', params)


if __name__ == '__main__': unittest.main()
