import json
import re
import unittest
import datetime as dt
from build_raw_backup_shortcut import build
from test_batch import OfflineBatch, Stopped


class RawSim(OfflineBatch):
    """Workflow evaluation only; native file coercion/extraction still needs runtime QA."""
    def __init__(self, files, names_include_extension=True, assemble=False):
        super().__init__({})
        self.files = files
        self.names_include_extension = names_include_extension
        self.previews = []
        self.assemble = assemble

    def menu_choice(self, parameters):
        return 'Собрать записи для проверки' if self.assemble else 'Завершить'

    def dictionary_input(self, value):
        return json.loads(value)

    def value(self, value):
        if isinstance(value, dict) and value.get('WFSerializationType') == 'WFTextTokenString':
            payload = value['Value']
            text = payload['string']
            for key, attachment in sorted(payload['attachmentsByRange'].items(),
                    key=lambda item: int(item[0].split(',')[0][1:]), reverse=True):
                position = int(key.split(',')[0][1:])
                resolved = self.value(attachment)
                text = text[:position] + ('' if resolved is None else str(resolved)) + text[position + 1:]
            return text
        return super().value(value)

    def external(self, ident, p):
        kind = ident.removeprefix('is.workflow.actions.')
        if kind == 'unzip':
            return list(self.files)
        if kind == 'filter.files':
            filters = p['WFContentItemFilter']['Value']['WFActionParameterFilterTemplates']
            stem, extension = [self.value(f['Values']['String']) for f in filters]
            return [f for f in self.files if stem in f.rsplit('/', 1)[-1]
                    and f.endswith('.' + extension)]
        if kind == 'getitemname':
            name = self.value(p['WFInput'])[0].rsplit('/', 1)[-1]
            return name if self.names_include_extension else name.removesuffix('.json')
        if kind == 'text.replace':
            replacement = re.sub(r'\$(\d+)', r'\\g<\1>', p['WFReplaceTextReplace'])
            return re.sub(p['WFReplaceTextFind'], replacement, self.value(p['WFInput']))
        if kind == 'detect.text':
            return self.files[self.value(p['WFInput'])[0]]
        if kind == 'text.match':
            return re.findall(p['WFMatchTextPattern'], self.value(p['text']))
        if kind == 'list': return []
        if kind == 'appendvariable':
            name = p['WFVariableName']; value = self.value(p['WFInput'])
            self.variables.setdefault(name, []).extend(value if isinstance(value, list) else [value])
            return self.variables[name]
        if kind == 'text.combine':
            return p['WFTextCustomSeparator'].join(self.value(p['text']))
        if kind == 'math':
            assert p['WFMathOperation'] == '/'
            return float(self.value(p['WFInput'])) / p['WFMathOperand']
        if kind == 'adjustdate':
            assert p['WFDuration']['Value']['Unit'] == 'sec'
            epoch = dt.datetime.fromisoformat(self.value(p['WFDate']).replace('Z', '+00:00'))
            # The native synthetic probe discarded fractional seconds: model that.
            return epoch + dt.timedelta(seconds=int(float(self.value(p['WFDuration']['Value']['Magnitude']))))
        if kind == 'format.date':
            assert p['WFDateFormatStyle'] == 'Custom'
            assert p['WFLocale'] == 'en_US_POSIX'
            if p['WFDateFormat'] == 'XXX': return '+00:00'
            assert p['WFDateFormat'] == "yyyy-MM-dd'T'HH:mm:ss"
            return self.value(p['WFDate']).strftime('%Y-%m-%dT%H:%M:%S')
        raise AssertionError(ident)


class RawBackupTests(unittest.TestCase):
    def files(self):
        return {name + '.json': json.dumps([{'uuid': f'{name}-{i}'} for i in range(count)])
                for name, count in [('answers', 4), ('routines', 2), ('journal-entries', 1), ('assets', 0)]}

    def run_inspection(self, files, **kwargs):
        sim = RawSim(files, **kwargs)
        with self.assertRaises(Stopped):
            sim.run(build()['WFWorkflowActions'])  # Default menu exits without writes.
        return sim

    def test_original_arrays_and_empty_assets_on_both_name_styles(self):
        for extension in [True, False]:
            sim = self.run_inspection(self.files(), names_include_extension=extension)
            self.assertEqual(sim.writes, [])
            summaries = [v for v in sim.outputs.values() if isinstance(v, str)
                         and v.startswith('Исходный архив Stoic прочитан.')]
            self.assertEqual(len(summaries), 1)
            for line in ['Ответы: 4', 'Рутины: 2', 'Отдельные записи: 1', 'Описания вложений: 0']:
                self.assertIn(line, summaries[0])

    def test_missing_ambiguous_or_wrong_name_stops_before_summary(self):
        for mode in ['missing', 'duplicate', 'wrong-name']:
            files = self.files()
            if mode == 'missing': del files['answers.json']
            if mode == 'duplicate': files['other/answers.json'] = files['answers.json']
            if mode == 'wrong-name': files['old-answers.json'] = files.pop('answers.json')
            sim = self.run_inspection(files)
            self.assertFalse(any(isinstance(v, str) and v.startswith('Исходный архив Stoic прочитан.')
                                 for v in sim.outputs.values()))

    def test_object_instead_of_array_is_rejected(self):
        files = self.files(); files['answers.json'] = '{"uuid":"not-an-array"}'
        sim = self.run_inspection(files)
        self.assertEqual(sim.writes, [])
        self.assertFalse(any(isinstance(v, str) and v.startswith('Исходный архив Stoic прочитан.')
                             for v in sim.outputs.values()))

    def test_no_scripts_network_journal_or_registry_actions(self):
        allowed = {'comment', 'file.select', 'unzip', 'filter.files', 'count', 'conditional',
                   'alert', 'exit', 'getitemname', 'text.replace', 'detect.text', 'text.match',
                   'gettext', 'detect.dictionary', 'getvalueforkey', 'previewdocument', 'choosefrommenu',
                   'setvariable', 'setvalueforkey', 'dictionary', 'list', 'repeat.each', 'appendvariable', 'text.combine',
                   'math', 'adjustdate', 'format.date'}
        actions = build()['WFWorkflowActions']
        seen = set()
        def refs(value):
            if isinstance(value, dict):
                if 'OutputUUID' in value: yield value['OutputUUID']
                for child in value.values(): yield from refs(child)
            elif isinstance(value, list):
                for child in value: yield from refs(child)
        for action in actions:
            self.assertIn(action['WFWorkflowActionIdentifier'].removeprefix('is.workflow.actions.'), allowed)
            parameters = action['WFWorkflowActionParameters']
            for reference in refs(parameters): self.assertIn(reference, seen)
            seen.add(parameters['UUID'])

    def linked_files(self):
        records = {
            'answers': [
                {'uuid': 'a2', 'routine': 'r1', 'text': 'Второй ответ', 'timestamp': 1002, 'assets': ['p1']},
                {'uuid': 'a1', 'text': 'Отдельная запись', 'timestamp': 1001},
                {'uuid': 'a3', 'routine': 'r1', 'text': '{"scale":3}', 'timestamp': 1003},
                {'uuid': 'a4', 'text': 'Ответ без связи', 'timestamp': 1004}],
            'routines': [{'uuid': 'r1', 'date': '01/01/2001', 'isCompleted': True}],
            'journal-entries': [{'uuid': 'j1', 'answers': ['a1'], 'timestamp': 1001}],
            'assets': [{'uuid': 'p1', 'answer': 'a2', 'type': 'image', 'relativePath': 'media/photo.jpg'}]}
        files = {k + '.json': json.dumps(v, ensure_ascii=False) for k, v in records.items()}
        files['media/photo.jpg'] = b'synthetic-image'
        return files

    def assemble(self, files, **kwargs):
        sim = RawSim(files, assemble=True, **kwargs)
        sim.run(build()['WFWorkflowActions'])
        return sim

    def test_links_standalone_routine_photo_and_orphan_without_losing_source(self):
        for extension in [True, False]:
            files = self.linked_files()
            sim = self.assemble(files, names_include_extension=extension)
            plan = sim.variables['StoicPlan']
            self.assertEqual([entry['sourceID'] for entry in plan], ['j1', 'r1', 'a4'])
            self.assertEqual(plan[0]['text'], 'Отдельная запись')
            self.assertEqual(plan[1]['sourceText'], 'Второй ответ\n\n{"scale":3}')
            self.assertEqual(plan[1]['title'], 'Второй ответ')
            self.assertEqual(plan[1]['text'], '{"scale":3}')
            self.assertEqual(plan[1]['attachmentPaths'], ['media/photo.jpg'])
            self.assertEqual(plan[0]['source']['timestamp'], 1001)
            self.assertEqual(plan[1]['answers'][0]['timestamp'], 1002)
            self.assertEqual(plan[2]['sourceKind'], 'orphan-answer')
            original_answers = json.loads(files['answers.json'])
            linked = [a for entry in plan for a in entry['answers']]
            self.assertEqual(sorted(linked, key=lambda a: a['uuid']), sorted(original_answers, key=lambda a: a['uuid']))
            self.assertEqual(sim.writes, [])

    def test_standalone_reference_order_is_preserved(self):
        files = self.linked_files()
        entries = json.loads(files['journal-entries.json'])
        entries[0]['answers'] = ['a4', 'a1']
        files['journal-entries.json'] = json.dumps(entries)
        sim = self.assemble(files)
        self.assertEqual(sim.variables['StoicPlan'][0]['sourceText'], 'Ответ без связи\n\nОтдельная запись')

    def test_plain_standalone_without_answers_is_preserved(self):
        files = self.linked_files()
        entries = json.loads(files['journal-entries.json'])
        entries.append({'uuid': 'j2', 'text': 'Текст без ссылок', 'timestamp': 1234.5})
        files['journal-entries.json'] = json.dumps(entries)
        sim = self.assemble(files)
        entry = sim.variables['StoicPlan'][1]
        self.assertEqual(entry['sourceID'], 'j2')
        self.assertEqual(entry['text'], 'Текст без ссылок')
        self.assertEqual(entry['source']['timestamp'], 1234.5)
        self.assertEqual(entry['answers'], [])

    def test_rich_text_only_stops_instead_of_silently_dropping(self):
        files = self.linked_files()
        files['journal-entries.json'] = json.dumps([{'uuid': 'rich', 'attributedText': 'opaque-content'}])
        sim = RawSim(files, assemble=True)
        with self.assertRaises(Stopped): sim.run(build()['WFWorkflowActions'])
        self.assertIn('rich-text-only', sim.alerts[-1])
        self.assertEqual(sim.writes, [])

    def test_routine_question_order_keeps_unknown_answers_and_does_not_duplicate(self):
        files = self.linked_files()
        answers = json.loads(files['answers.json'])
        answers[0]['question'] = 'Second... prompt'
        answers[2]['question'] = 'First prompt'
        answers.append({'uuid': 'extra', 'routine': 'r1', 'question': 'Unlisted', 'text': 'Last', 'timestamp': 999})
        routines = json.loads(files['routines.json'])
        routines[0]['questions'] = ['First prompt', 'Second... prompt', 'First prompt', 'missing']
        files.update({'answers.json': json.dumps(answers), 'routines.json': json.dumps(routines)})
        plan = self.assemble(files).variables['StoicPlan']
        routine = plan[1]
        self.assertEqual([a['uuid'] for a in routine['answers']], ['a3', 'a2', 'extra'])
        self.assertIn('First prompt\n\n{"scale":3}', routine['sourceText'])
        self.assertEqual(routine['sourceTimestampMilliseconds'], 999)
        self.assertEqual(dt.datetime.fromisoformat(routine['date']).timestamp(), .999)

    def test_uuid_question_is_metadata_and_structured_answer_needs_review(self):
        files = self.linked_files()
        answers = json.loads(files['answers.json'])
        answers[2]['question'] = '00000000-0000-4000-8000-000000000001'
        files['answers.json'] = json.dumps(answers)
        routine = self.assemble(files).variables['StoicPlan'][1]
        self.assertNotIn(answers[2]['question'], routine['sourceText'])
        self.assertTrue(routine['needsReview'])
        self.assertIn('{"scale":3}', routine['sourceText'])

    def test_title_boundary_first_line_and_body_are_preserved(self):
        for source_text, expected_title, expected_body in [
            ('я' * 79 + '\n\nТело', 'я' * 79, 'Тело'),
            ('я' * 80 + '\n\nТело', '', 'я' * 80 + '\n\nТело'),
            ('Одна строка', '', 'Одна строка'),
            ('# Заголовок\r\n\r\nТело\r\nЗаголовок', 'Заголовок', 'Тело\r\nЗаголовок'),
            ('123\n\nТекст', '', '123\n\nТекст')]:
            files = self.linked_files()
            files['journal-entries.json'] = json.dumps([{'uuid': 'title-case', 'text': source_text, 'timestamp': 0}])
            entry = self.assemble(files).variables['StoicPlan'][0]
            with self.subTest(text_length=len(source_text)):
                self.assertEqual(entry['title'], expected_title)
                self.assertEqual(entry['text'], expected_body)
                self.assertEqual(entry['sourceText'], source_text)

    def test_date_keeps_milliseconds_even_when_native_adjustdate_truncates(self):
        for stamp in [0, 1, 12, 999, 1000, 1002, 1234.5, 978177600123.75, 1767225599999]:
            files = self.linked_files()
            files['journal-entries.json'] = json.dumps([{'uuid': 'date-case', 'text': 'Synthetic', 'timestamp': stamp}])
            entry = self.assemble(files).variables['StoicPlan'][0]
            rendered = dt.datetime.fromisoformat(entry['date']).timestamp()
            with self.subTest(stamp=stamp):
                self.assertLess(abs(rendered - stamp / 1000), .001)
                self.assertEqual(entry['sourceTimestampMilliseconds'], stamp)
                self.assertEqual(entry['source']['timestamp'], stamp)

    def test_missing_negative_or_non_numeric_timestamp_stops(self):
        for stamp in [None, 'yesterday', -1, True]:
            files = self.linked_files()
            files['journal-entries.json'] = json.dumps([{'uuid': 'bad-date', 'text': 'Synthetic', 'timestamp': stamp}])
            sim = RawSim(files, assemble=True)
            with self.subTest(stamp=stamp):
                with self.assertRaises(Stopped): sim.run(build()['WFWorkflowActions'])
                self.assertEqual(sim.writes, [])

    def test_broken_links_duplicate_ids_and_ambiguous_media_stop(self):
        for mode in ['missing-answer', 'duplicate-answer', 'duplicate-source', 'double-owner',
                     'missing-asset', 'wrong-owner', 'missing-photo', 'ambiguous-photo', 'unsafe-path', 'not-image']:
            files = self.linked_files()
            answers = json.loads(files['answers.json'])
            entries = json.loads(files['journal-entries.json'])
            assets = json.loads(files['assets.json'])
            if mode == 'missing-answer': entries[0]['answers'] = ['missing']
            if mode == 'duplicate-answer': answers.append(answers[0])
            if mode == 'duplicate-source': entries.append(entries[0])
            if mode == 'double-owner': entries[0]['answers'].append('a2')
            if mode == 'missing-asset': assets = []
            if mode == 'wrong-owner': assets[0]['answer'] = 'a3'
            if mode == 'missing-photo': del files['media/photo.jpg']
            if mode == 'ambiguous-photo': files['other/photo.jpg'] = b'other'
            if mode == 'unsafe-path': assets[0]['relativePath'] = '../photo.jpg'
            if mode == 'not-image': assets[0]['type'] = 'video'
            files.update({'answers.json': json.dumps(answers), 'journal-entries.json': json.dumps(entries),
                          'assets.json': json.dumps(assets)})
            sim = RawSim(files, assemble=True)
            with self.subTest(mode=mode):
                with self.assertRaises(Stopped): sim.run(build()['WFWorkflowActions'])
                self.assertEqual(sim.writes, [])


if __name__ == '__main__': unittest.main()


class NativeTextParameterTests(unittest.TestCase):
    def test_dictionary_lookup_keys_use_text_parameter_state(self):
        from build_stoic_shortcut import build as build_unified
        named_keys = []
        for action in build_unified()['WFWorkflowActions']:
            if action['WFWorkflowActionIdentifier'] != 'is.workflow.actions.getvalueforkey':
                continue
            key = action['WFWorkflowActionParameters']['WFDictionaryKey']
            if not isinstance(key, dict):
                self.assertTrue(key)
                continue
            self.assertEqual(key['WFSerializationType'], 'WFTextTokenString')
            attachment = key['Value']['attachmentsByRange']['{0, 1}']
            if attachment['Type'] == 'Variable':
                named_keys.append(attachment['VariableName'])
        self.assertIn('SourceKey', named_keys)
        self.assertIn('Repeat Item', named_keys)

    def test_dictionary_variable_values_use_text_parameter_state(self):
        from build_stoic_shortcut import build as build_unified
        found = False
        for action in build_unified()['WFWorkflowActions']:
            if action['WFWorkflowActionIdentifier'] != 'is.workflow.actions.setvalueforkey':
                continue
            value = action['WFWorkflowActionParameters']['WFDictionaryValue']
            if not isinstance(value, dict):
                continue
            found = True
            self.assertEqual(value['WFSerializationType'], 'WFTextTokenString')
            self.assertEqual(value['Value']['string'], '\ufffc')
        self.assertTrue(found)

    def test_text_actions_use_native_text_input(self):
        # The device prompts for missing `text` when only WFInput is supplied.
        # Schema: ShortcutsBench/data/all_api2parasummary.json (text.match/combine).
        from build_stoic_shortcut import build as build_unified
        actions = build_unified()['WFWorkflowActions']
        matched = [a for a in actions if a['WFWorkflowActionIdentifier'] in {
            'is.workflow.actions.text.match', 'is.workflow.actions.text.combine',
            'is.workflow.actions.text.split'}]
        self.assertTrue(matched)
        for action in matched:
            with self.subTest(identifier=action['WFWorkflowActionIdentifier']):
                p = action['WFWorkflowActionParameters']
                self.assertIn('text', p)
                self.assertNotIn('WFInput', p)

    def test_text_fields_preserve_variables_in_text_templates(self):
        from build_stoic_shortcut import build as build_unified
        for action in build_unified()['WFWorkflowActions']:
            kind = action['WFWorkflowActionIdentifier'].removeprefix('is.workflow.actions.')
            if kind not in ('text.match', 'text.replace', 'text.split'):
                continue
            field = 'WFInput' if kind == 'text.replace' else 'text'
            value = action['WFWorkflowActionParameters'][field]
            with self.subTest(kind=kind):
                self.assertEqual(value['WFSerializationType'], 'WFTextTokenString')
                self.assertEqual(value['Value']['string'], '\ufffc')
                attachment = value['Value']['attachmentsByRange']['{0, 1}']
                self.assertIn(attachment['Type'], ('ActionOutput', 'Variable'))
