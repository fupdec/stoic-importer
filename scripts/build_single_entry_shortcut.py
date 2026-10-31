#!/usr/bin/env python3
"""Generate an AI-free, one-entry file importer. Never embeds private content."""
import copy
from pathlib import Path
import plistlib
import uuid

ROOT = Path(__file__).resolve().parent.parent


def uid():
    return str(uuid.uuid4()).upper()


def ref(output_id, name='Dictionary'):
    return {'Value': {'Type': 'ActionOutput', 'OutputUUID': output_id, 'OutputName': name},
            'WFSerializationType': 'WFTextTokenAttachment'}


def token(output_id, name):
    return {'Value': {'string': '\ufffc', 'attachmentsByRange': {
        '{0, 1}': {'Type': 'ActionOutput', 'OutputUUID': output_id, 'OutputName': name}}},
        'WFSerializationType': 'WFTextTokenString'}


def text_input(value):
    """Use a text template for text fields, retaining the original variable."""
    if isinstance(value, dict) and value.get('WFSerializationType') == 'WFTextTokenAttachment':
        return {'Value': {'string': '\ufffc', 'attachmentsByRange': {
            '{0, 1}': value['Value']}}, 'WFSerializationType': 'WFTextTokenString'}
    return value


def build():
    workflow = plistlib.loads((ROOT / 'shortcuts/HistoricalDateProbe.plist').read_bytes())
    journal = copy.deepcopy(workflow['WFWorkflowActions'][0])
    actions = []
    def add(identifier, **params):
        params.setdefault('UUID', uid())
        actions.append({'WFWorkflowActionIdentifier': identifier, 'WFWorkflowActionParameters': params})
        return params['UUID']
    add('is.workflow.actions.comment', WFCommentActionText=(
        'Import ONE prepared Stoic entry. Select stoic-one-entry.json. '
        'No AI, web requests, loops, or automatic retry. Re-running can duplicate the entry. '
        'Journal action adapted from jeffd/DayOneToJournal (MIT).'))
    file_id = add('is.workflow.actions.file.select', WFPickingMode='Files', WFSelectMultiple=False)
    dict_id = add('is.workflow.actions.detect.dictionary', WFInput=ref(file_id, 'File'))
    values = {}
    for key in ['schema', 'title', 'date', 'text']:
        values[key] = add('is.workflow.actions.getvalueforkey', WFDictionaryKey=key, WFInput=ref(dict_id))
    schema_text = add('is.workflow.actions.gettext', WFTextActionText=token(values['schema'], 'Dictionary Value'))
    # Dictionary values are untyped in Shortcuts. Force Text before comparing.
    # Stop safely before Journal if an unrelated or incomplete JSON is selected.
    for key, condition, expected in [('schema', 5, 'stoic-single-entry-v1'), ('date', 101, None), ('text', 101, None)]:
        group = uid()
        subject = ref(schema_text, 'Text') if key == 'schema' else ref(values[key], 'Dictionary Value')
        params = dict(WFControlFlowMode=0, GroupingIdentifier=group, WFCondition=condition,
                      WFInput={'Type': 'Variable', 'Variable': subject})
        if expected is not None:
            params['WFConditionalActionString'] = expected
        add('is.workflow.actions.conditional', **params)
        add('is.workflow.actions.alert', WFAlertActionTitle='Import stopped',
            WFAlertActionMessage='Choose the prepared stoic-one-entry.json file. No entry was created.',
            WFAlertActionCancelButtonShown=False)
        add('is.workflow.actions.exit')
        add('is.workflow.actions.conditional', WFControlFlowMode=2, GroupingIdentifier=group)
    # Two cancelable previews: date first, full personal text second.
    add('is.workflow.actions.alert', WFAlertActionTitle='Check original date (UTC)',
        WFAlertActionMessage=token(values['date'], 'Dictionary Value'), WFAlertActionCancelButtonShown=True)
    add('is.workflow.actions.alert', WFAlertActionTitle='Create ONE Journal entry? Cancel if already imported.',
        WFAlertActionMessage=token(values['text'], 'Dictionary Value'), WFAlertActionCancelButtonShown=True)
    title_text = add('is.workflow.actions.gettext', WFTextActionText=token(values['title'], 'Dictionary Value'))
    title_group = uid()
    add('is.workflow.actions.conditional', WFControlFlowMode=0, GroupingIdentifier=title_group, WFCondition=100,
        WFInput={'Type': 'Variable', 'Variable': ref(title_text, 'Text')})
    for has_title in [True, False]:
        if not has_title:
            add('is.workflow.actions.conditional', WFControlFlowMode=1, GroupingIdentifier=title_group)
        current = copy.deepcopy(journal)
        params = current['WFWorkflowActionParameters']
        params.update(UUID=uid(), entryDate=token(values['date'], 'Dictionary Value'),
                      message=token(values['text'], 'Dictionary Value'))
        if has_title:
            params['title'] = token(title_text, 'Text')
        else:
            params.pop('title', None)
        actions.append(current)
    add('is.workflow.actions.conditional', WFControlFlowMode=2, GroupingIdentifier=title_group)
    # Do not claim persistence based only on action completion.
    add('is.workflow.actions.alert', WFAlertActionTitle='Check Journal',
        WFAlertActionMessage='The create action returned. Verify the entry text and date in Journal before running again.',
        WFAlertActionCancelButtonShown=False)
    workflow['WFWorkflowActions'] = actions
    return workflow


if __name__ == '__main__':
    workflow = build()
    (ROOT / 'shortcuts/ImportOneStoicEntry.plist').write_bytes(plistlib.dumps(workflow))
    Path('/private/tmp/ImportOneStoicEntry-unsigned.shortcut').write_bytes(plistlib.dumps(workflow, fmt=plistlib.FMT_BINARY))
    print('Generated generic one-entry importer; no private diary content embedded.')
