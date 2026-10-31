#!/usr/bin/env python3
"""Build a generic one-photo importer. No private content is embedded."""
from pathlib import Path
import plistlib
from build_single_entry_shortcut import ROOT, build, uid, ref, token


def build_photo():
    workflow = build()
    actions = workflow['WFWorkflowActions']
    journal_index = next(i for i,a in enumerate(actions) if a['WFWorkflowActionIdentifier']=='com.apple.journal.CreateEntryIntent')
    # Select and preview media before the optional-title branch, so both paths have it.
    insert_index = journal_index - 1
    dict_action = next(a for a in actions if a['WFWorkflowActionIdentifier']=='is.workflow.actions.detect.dictionary')
    dict_id = dict_action['WFWorkflowActionParameters']['UUID']
    def action(name, **parameters):
        parameters.setdefault('UUID', uid())
        return {'WFWorkflowActionIdentifier': 'is.workflow.actions.' + name, 'WFWorkflowActionParameters': parameters}
    filename = action('getvalueforkey', WFDictionaryKey='attachmentFileName', WFInput=ref(dict_id))
    count = action('getvalueforkey', WFDictionaryKey='attachmentCount', WFInput=ref(dict_id))
    count_id = count['WFWorkflowActionParameters']['UUID']
    # Stop if a text-only or multi-photo payload is selected. Use the
    # explicit Text comparison already verified by the one-entry workflow.
    number = action('gettext', WFTextActionText=token(count_id, 'Dictionary Value'))
    group = uid()
    invalid = action('conditional', WFControlFlowMode=0, GroupingIdentifier=group, WFCondition=5,
                     WFConditionalActionString='1',
                     WFInput={'Type':'Variable', 'Variable':ref(number['WFWorkflowActionParameters']['UUID'], 'Text')})
    stop_alert = action('alert', WFAlertActionTitle='Import stopped',
                        WFAlertActionMessage='Choose the prepared one-photo JSON with attachmentCount = 1.',
                        WFAlertActionCancelButtonShown=False)
    picker = action('file.select', WFPickingMode='Files', WFSelectMultiple=False)
    photo_ref = ref(picker['WFWorkflowActionParameters']['UUID'], 'File')
    before = [filename, count, number, invalid, stop_alert, action('exit'),
              action('conditional', WFControlFlowMode=2, GroupingIdentifier=group),
              action('alert', WFAlertActionTitle='Next: select this photo file',
                     WFAlertActionMessage=token(filename['WFWorkflowActionParameters']['UUID'], 'Dictionary Value'),
                     WFAlertActionCancelButtonShown=True),
              picker,
              action('previewdocument', WFInput=photo_ref),
              action('alert', WFAlertActionTitle='Create ONE entry with this photo?',
                     WFAlertActionMessage='Check the image you just previewed. Cancel if it is wrong or this entry already exists. Continue creates one new Journal entry.',
                     WFAlertActionCancelButtonShown=True)]
    for journal in actions:
        if journal['WFWorkflowActionIdentifier']=='com.apple.journal.CreateEntryIntent':
            journal['WFWorkflowActionParameters']['mediaItems'] = photo_ref
    actions[insert_index:insert_index] = before
    for a in actions:
        p=a['WFWorkflowActionParameters']
        if a['WFWorkflowActionIdentifier']=='is.workflow.actions.alert' and p.get('WFAlertActionTitle','').startswith('Create ONE Journal entry?'):
            p['WFAlertActionTitle']='Review entry text. Photo selection follows.'
    for item in actions:
        params = item['WFWorkflowActionParameters']
        if params.get('WFAlertActionMessage') == 'Choose the prepared stoic-one-entry.json file. No entry was created.':
            params['WFAlertActionMessage'] = 'First choose stoic-one-photo-entry.json from the unzipped folder, not the ZIP or photo. No entry was created.'
    actions[0]['WFWorkflowActionParameters']['WFCommentActionText']=(
        'Import ONE prepared Stoic routine with ONE photo. First choose stoic-one-photo-entry.json; '
        'then choose the named image file. Preview and confirm before writing. No AI, network, loops or ledger. '
        'Re-running creates duplicates. Journal action adapted from jeffd/DayOneToJournal (MIT).')
    return workflow


if __name__ == '__main__':
    workflow = build_photo()
    (ROOT/'shortcuts/ImportOneStoicPhoto.plist').write_bytes(plistlib.dumps(workflow))
    Path('/private/tmp/ImportOneStoicPhoto-unsigned.shortcut').write_bytes(plistlib.dumps(workflow,fmt=plistlib.FMT_BINARY))
    print('Generated generic one-photo workflow. No personal text or media embedded.')
