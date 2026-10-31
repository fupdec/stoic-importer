#!/usr/bin/env python3
"""Build native Shortcuts actions for original Stoic ZIP inspection. No runtime code."""
import plistlib
from pathlib import Path
from build_single_entry_shortcut import ROOT, uid, ref, token, text_input
from raw_backup_plan import append_plan


def build(include_import=False):
    workflow = plistlib.loads((ROOT / 'shortcuts/HistoricalDateProbe.plist').read_bytes())
    actions = []

    def add(name, **parameters):
        if name in ('text.match', 'text.split') and 'text' in parameters:
            parameters['text'] = text_input(parameters['text'])
        if name == 'text.replace' and 'WFInput' in parameters:
            parameters['WFInput'] = text_input(parameters['WFInput'])
        parameters.setdefault('UUID', uid())
        actions.append({'WFWorkflowActionIdentifier': 'is.workflow.actions.' + name,
                        'WFWorkflowActionParameters': parameters})
        return parameters['UUID']

    def stop_unless(subject, expected, message):
        group = uid()
        comparison = {'WFNumberValue': expected} if isinstance(expected, int) else {'WFConditionalActionString': expected}
        add('conditional', GroupingIdentifier=group, WFControlFlowMode=0, WFCondition=5,
            WFInput={'Type': 'Variable', 'Variable': subject}, **comparison)
        add('alert', WFAlertActionTitle='Архив не поддерживается',
            WFAlertActionMessage=message, WFAlertActionCancelButtonShown=False)
        add('exit')
        add('conditional', GroupingIdentifier=group, WFControlFlowMode=2)

    def wrapped_list(text_id):
        # Get Dictionary is given an OBJECT even when Stoic stores a root array.
        text = token(text_id, 'Text')
        text['Value']['string'] = '{"records":\ufffc}'
        text['Value']['attachmentsByRange'] = {'{11, 1}': next(iter(text['Value']['attachmentsByRange'].values()))}
        wrapped = add('gettext', WFTextActionText=text)
        parsed = add('detect.dictionary', WFInput=ref(wrapped, 'Text'))
        return add('getvalueforkey', WFDictionaryKey='records', WFInput=ref(parsed))

    add('comment', WFCommentActionText=(
        'ORIGINAL STOIC ZIP INSPECTION ONLY. Standard Shortcuts actions; no scripts, '
        'AI, network or Journal writes. Expects answers.json, routines.json, '
        'journal-entries.json and assets.json as JSON arrays. Extraction uses '
        'native Shortcuts and is not a hardened ZIP validator.'))
    selected = add('file.select', WFPickingMode='Files', WFSelectMultiple=False)
    extracted = add('unzip', WFArchive=ref(selected, 'File'))
    counts = {}
    collections = {}
    files = []
    for stem in ['answers', 'routines', 'journal-entries', 'assets']:
        found = add('filter.files', WFContentItemInputParameter=ref(extracted, 'Files'),
            WFContentItemLimitEnabled=False,
            WFContentItemFilter={'Value': {
                'WFActionParameterFilterPrefix': 1,
                'WFActionParameterFilterTemplates': [
                    {'Operator': 8, 'Property': 'Name', 'Removable': True,
                     'Values': {'String': stem, 'Unit': 4}},
                    {'Operator': 4, 'Property': 'File Extension', 'Removable': True,
                     'Values': {'String': 'json', 'Unit': 4}}],
                'WFContentPredicateBoundedDate': False},
                'WFSerializationType': 'WFContentPredicateTableTemplate'})
        count = add('count', WFInput=ref(found, 'Files'), Input=ref(found, 'Files'))
        stop_unless(ref(count, 'Count'), 1,
                    f'Ожидается ровно один {stem}.json. Архив не изменён. Записи не создавались.')
        name = add('getitemname', WFInput=ref(found, 'Files'))
        normalized = add('text.replace', WFInput=token(name, 'Name'),
            WFReplaceTextFind=r'\.json$', WFReplaceTextReplace='', WFReplaceTextRegularExpression=True)
        stop_unless(ref(normalized, 'Updated Text'), stem, 'Имя JSON не соответствует формату Stoic.')
        files.append(found)
        text = add('detect.text', WFInput=ref(found, 'Files'))
        shape = add('text.match', text=ref(text, 'Text'), WFMatchTextPattern=r'^\s*\[')
        shape_count = add('count', WFInput=ref(shape, 'Matches'), Input=ref(shape, 'Matches'))
        stop_unless(ref(shape_count, 'Count'), 1, f'{stem}.json должен содержать JSON-массив.')
        # Array wrapping avoids relying on implicit root-array coercion.
        records = wrapped_list(text)
        collections[stem] = records
        counts[stem] = add('count', WFInput=ref(records, 'Dictionary Value'), Input=ref(records, 'Dictionary Value'))

    lines = ['Исходный архив Stoic прочитан.', '']
    attachments = {}
    labels = [('answers', 'Ответы'), ('routines', 'Рутины'),
              ('journal-entries', 'Отдельные записи'), ('assets', 'Описания вложений')]
    for key, label in labels:
        lines.append(label + ': \ufffc')
    lines += ['', 'Это количества исходных объектов, а не будущих записей Journal.',
              'Связи, даты и наличие файлов фотографий ещё не проверены.',
              'Следом можно просмотреть исходные JSON. Новые записи не создаются.']
    summary = '\n'.join(lines)
    offset = 0
    for key, _ in labels:
        position = summary.index('\ufffc', offset)
        attachments[f'{{{position}, 1}}'] = {'Type': 'ActionOutput', 'OutputUUID': counts[key], 'OutputName': 'Count'}
        offset = position + 1
    overview = add('gettext', WFTextActionText={'Value': {'string': summary, 'attachmentsByRange': attachments},
                                             'WFSerializationType': 'WFTextTokenString'})
    add('previewdocument', WFInput=ref(overview, 'Text'))
    menu = uid()
    add('choosefrommenu', GroupingIdentifier=menu, WFControlFlowMode=0,
        WFMenuPrompt='Просмотреть данные без импорта?', WFMenuItems=['Завершить', 'Собрать записи для проверки', 'Показать JSON'])
    add('choosefrommenu', GroupingIdentifier=menu, WFControlFlowMode=1, WFMenuItemTitle='Завершить')
    add('exit')
    add('choosefrommenu', GroupingIdentifier=menu, WFControlFlowMode=1, WFMenuItemTitle='Собрать записи для проверки')
    plan = append_plan(actions, collections, extracted)
    add('previewdocument', WFInput=plan)
    add('alert', WFAlertActionTitle='Записи собраны для проверки',
        WFAlertActionMessage='Это предпросмотр. Исходные данные сохранены в source и answers. Ответы без связи и нерасшифрованные шкалы отмечены для проверки. Даты Journal требуют проверки на устройстве. Ничего не импортировано.',
        WFAlertActionCancelButtonShown=False)
    if include_import:
        from raw_import_actions import append_import
        append_import(actions, plan, extracted)
    add('choosefrommenu', GroupingIdentifier=menu, WFControlFlowMode=1, WFMenuItemTitle='Показать JSON')
    for file_id in files:
        add('previewdocument', WFInput=ref(file_id, 'Files'))
    add('choosefrommenu', GroupingIdentifier=menu, WFControlFlowMode=2)
    workflow['WFWorkflowActions'] = actions
    return workflow


if __name__ == '__main__':
    workflow = build()
    (ROOT / 'shortcuts/InspectStoicBackup.plist').write_bytes(plistlib.dumps(workflow))
    print('Generated original-backup inspection actions. No Journal writes.')
