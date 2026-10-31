import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[2]
def module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / (name + '.py'))
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result
prepare = module('prepare_one_entry')
builder = module('build_single_entry_shortcut')

class SingleEntryTests(unittest.TestCase):
    def archive(self, folder, answers, entries):
        path = Path(folder) / 'synthetic.zip'
        with zipfile.ZipFile(path, 'w') as archive:
            archive.writestr('backup/answers.json', json.dumps(answers))
            archive.writestr('backup/journal-entries.json', json.dumps(entries))
        return path

    def test_selects_one_complete_entry_in_answer_order(self):
        with tempfile.TemporaryDirectory() as folder:
            path = self.archive(folder, [
                {'uuid':'a', 'text':'First', 'question':'Question 1'},
                {'uuid':'b', 'text':'Second', 'question':'Question 2'},
                {'uuid':'photo', 'text':'Photo', 'assets':['asset-1']},
            ], [
                {'uuid':'valid', 'timestamp':1766740000000, 'calendarDate':'26/12/2025', 'answers':['b','a']},
                {'uuid':'missing', 'timestamp':1766741000000, 'answers':['unresolved']},
                {'uuid':'media', 'timestamp':1766742000000, 'answers':['photo']},
            ])
            payload = prepare.prepare(path)
            self.assertEqual(payload['sourceID'], 'valid')
            self.assertEqual(payload['title'], 'Question 2')
            self.assertEqual(payload['text'], 'Second\n\nQuestion 1\n\nFirst')
            self.assertEqual(payload['sourceText'], 'Question 2\n\nSecond\n\nQuestion 1\n\nFirst')
            self.assertTrue(payload['date'].endswith('Z'))
            self.assertEqual(payload['attachmentCount'], 0)

    def test_missing_candidate_fails(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(ValueError):
                prepare.prepare(self.archive(folder, [], []))

    def test_duplicate_answers_fail(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(ValueError):
                prepare.prepare(self.archive(folder, [{'uuid':'x'},{'uuid':'x'}], []))

    def test_private_output_exclusive_and_restricted(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'data.json'
            prepare.exclusive_write(path, 'synthetic')
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            with self.assertRaises(FileExistsError):
                prepare.exclusive_write(path, 'replacement')
            self.assertEqual(path.read_text(), 'synthetic')

    def test_single_write_no_network_or_loops(self):
        actions = builder.build()['WFWorkflowActions']
        identifiers = [a['WFWorkflowActionIdentifier'] for a in actions]
        self.assertEqual(identifiers.count('com.apple.journal.CreateEntryIntent'), 2)
        from test_batch import OfflineBatch
        for title in ['Synthetic title', '']:
            sim = OfflineBatch(dict(schema='stoic-single-entry-v1', title=title, date='2001-02-04T12:00:00Z', text='Synthetic body'))
            sim.run(actions)
            self.assertEqual(len(sim.writes), 1)
            self.assertEqual('title' in sim.writes[0], bool(title))
        allowed = {'is.workflow.actions.' + s for s in [
            'comment','file.select','detect.dictionary','getvalueforkey','gettext','conditional','alert','exit']}
        allowed.add('com.apple.journal.CreateEntryIntent')
        self.assertTrue(set(identifiers) <= allowed)
        journal_index = identifiers.index('com.apple.journal.CreateEntryIntent')
        previews = [a for a in actions[:journal_index] if a['WFWorkflowActionIdentifier']=='is.workflow.actions.alert'
                    and a['WFWorkflowActionParameters'].get('WFAlertActionCancelButtonShown')]
        self.assertEqual(len(previews), 2)
        self.assertNotIn('mediaItems', actions[journal_index]['WFWorkflowActionParameters'])

    def test_schema_comparison_uses_explicit_text_output(self):
        actions = builder.build()['WFWorkflowActions']
        condition = next(a['WFWorkflowActionParameters'] for a in actions
                         if a['WFWorkflowActionIdentifier'] == 'is.workflow.actions.conditional')
        variable = condition['WFInput']['Variable']['Value']
        producer = next(a for a in actions if a['WFWorkflowActionParameters']['UUID'] == variable['OutputUUID'])
        self.assertEqual(producer['WFWorkflowActionIdentifier'], 'is.workflow.actions.gettext')
        self.assertEqual(variable['OutputName'], 'Text')
        self.assertEqual(condition['WFConditionalActionString'], 'stoic-single-entry-v1')
        self.assertEqual(condition['WFCondition'], 5)

    def test_foreign_keys_and_unresolved_scale_values_do_not_enter_body(self):
        question = '00000000-0000-4000-8000-000000000001'
        answers = [
            {'uuid':'a', 'question':question, 'text':'[0,2]'},
            {'uuid':'b', 'question':question, 'text':'1.25'},
            {'uuid':'c', 'question':question, 'text':'Synthetic prose.\nSecond paragraph.'},
            {'uuid':'d', 'question':question, 'text':'3'},
        ]
        body, unresolved = prepare.render_answers(answers)
        self.assertEqual(body, 'Synthetic prose.\nSecond paragraph.')
        self.assertNotIn(question, body)
        self.assertEqual([a['rawValue'] for a in unresolved], ['[0,2]', '1.25', '3'])
        self.assertEqual([a['answerID'] for a in unresolved], ['a','b','d'])

    def test_readable_prompt_with_numeric_answer_is_preserved(self):
        body, unresolved = prepare.render_answers([{'uuid':'a', 'question':'How many walks?', 'text':'3'}])
        self.assertEqual(body, 'How many walks?\n\n3')
        self.assertEqual(unresolved, [])

    def test_title_uses_only_first_line(self):
        self.assertEqual(prepare.make_title('\nКупил свитер\n\nДругие события'), 'Купил свитер')
        self.assertEqual(prepare.make_title('Первая строка\nпродолжение\n\nВторой абзац'), 'Первая строка')
        self.assertEqual(prepare.make_title('Первый\r\n\r\nВторой'), 'Первый')
        self.assertEqual(prepare.make_title('- Прогулка у моря'), 'Прогулка у моря')

    def test_title_limit_is_exclusive_and_does_not_truncate_or_skip(self):
        self.assertEqual(prepare.make_title('абвг', 5), 'абвг')
        self.assertEqual(prepare.make_title('абвгде\n\nКороткий', 5), 'Запись дневника')
        self.assertEqual(prepare.make_title('я' * 79), 'я' * 79)
        self.assertEqual(prepare.make_title('я' * 80), 'Запись дневника')
        self.assertEqual(prepare.make_title(''), 'Запись дневника')
        self.assertEqual(prepare.make_title('[0,2]\n\nТекст'), 'Запись дневника')
        with self.assertRaises(ValueError): prepare.make_title('Текст', 0)

    def test_promoted_line_is_removed_only_once_and_body_preserved(self):
        title, body = prepare.split_title_body('Купил свитер\n\nВторая строка\nКупил свитер')
        self.assertEqual(title, 'Купил свитер')
        self.assertEqual(body, 'Вторая строка\nКупил свитер')
        self.assertEqual(prepare.split_title_body('Короткая запись'), ('', 'Короткая запись'))
        long = 'я' * 80 + '\nТекст'
        self.assertEqual(prepare.split_title_body(long), ('', long))
        self.assertEqual(prepare.split_title_body('Заголовок\r\n\r\nТело'), ('Заголовок', 'Тело'))

if __name__ == '__main__': unittest.main()
