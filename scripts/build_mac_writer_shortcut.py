#!/usr/bin/env python3
"""Mac bridge v3: prepare every image before creating exactly one Journal entry."""
import copy
import plistlib
from pathlib import Path
from build_single_entry_shortcut import ROOT, uid, ref, token, text_input


def build():
    workflow = plistlib.loads((ROOT / 'shortcuts/HistoricalDateProbe.plist').read_bytes())
    template = copy.deepcopy(workflow['WFWorkflowActions'][0])
    actions = []

    def add(name, **params):
        params.setdefault('UUID', uid())
        actions.append({'WFWorkflowActionIdentifier': 'is.workflow.actions.' + name, 'WFWorkflowActionParameters': params})
        return params['UUID']

    def condition(value, code, expected):
        group = uid()
        add('conditional', WFControlFlowMode=0, GroupingIdentifier=group, WFCondition=code,
            WFInput={'Type': 'Variable', 'Variable': value}, WFConditionalActionString=expected)
        return group

    def end(group):
        add('conditional', WFControlFlowMode=2, GroupingIdentifier=group)

    def stop(message):
        add('alert', WFAlertActionTitle='Импорт остановлен', WFAlertActionMessage=message, WFAlertActionCancelButtonShown=False)
        add('exit')

    shortcut_input = {'Value': {'Type': 'ExtensionInput'}, 'WFSerializationType': 'WFTextTokenAttachment'}
    add('comment', WFCommentActionText='Stoic Mac Writer v3. Install as StoicMacWriterV3. Receives a private prepared folder. Reads ALL listed photos before ONE Journal write. No ZIP parser, network, ledger or automatic retry.')
    payload = add('documentpicker.open', WFFile=shortcut_input, WFGetFilePath='entry.json', WFFileErrorIfNotFound=True)
    dictionary = add('detect.dictionary', WFInput=ref(payload, 'File'))
    fields = {key: add('getvalueforkey', WFDictionaryKey=key, WFInput=ref(dictionary))
              for key in ['schema', 'date', 'text', 'attachmentCount', 'attachmentFileNames']}
    schema = add('gettext', WFTextActionText=token(fields['schema'], 'Dictionary Value'))
    invalid = condition(ref(schema, 'Text'), 5, 'stoic-mac-bridge-v2')
    stop('Запускайте StoicMacWriterV2 из обновлённого приложения Stoic Importer.')
    end(invalid)
    expected_count = add('gettext', WFTextActionText=token(fields['attachmentCount'], 'Dictionary Value'))
    listed_count = add('count', WFInput=ref(fields['attachmentFileNames'], 'Dictionary Value'), Input=ref(fields['attachmentFileNames'], 'Dictionary Value'))
    listed_text = add('gettext', WFTextActionText=token(listed_count, 'Count'))
    invalid = condition(ref(listed_text, 'Text'), 5, token(expected_count, 'Text'))
    stop('Количество фотографий не совпадает со списком. Запись не создана.')
    end(invalid)

    def journal(media=None):
        action = copy.deepcopy(template)
        params = action['WFWorkflowActionParameters']
        params.update(UUID=uid(), entryDate=token(fields['date'], 'Dictionary Value'), message=token(fields['text'], 'Dictionary Value'), OpenWhenRun=False)
        params.pop('title', None)
        if media:
            params['mediaItems'] = media
            params['WFInput'] = media
        else:
            params.pop('mediaItems', None)
            params.pop('WFInput', None)
        actions.append(action)

    no_photos = condition(ref(expected_count, 'Text'), 4, '0')
    journal()
    add('conditional', WFControlFlowMode=1, GroupingIdentifier=no_photos)
    photos = uid()
    add('repeat.each', WFControlFlowMode=0, GroupingIdentifier=photos, WFInput=ref(fields['attachmentFileNames'], 'Dictionary Value'))
    repeat_item = {'Value': {'Type': 'Variable', 'VariableName': 'Repeat Item'}, 'WFSerializationType': 'WFTextTokenAttachment'}
    # The file is the final action in each iteration, so Repeat Results contains all files.
    add('documentpicker.open', WFFile=shortcut_input, WFGetFilePath=text_input(repeat_item), WFFileErrorIfNotFound=True)
    results = add('repeat.each', WFControlFlowMode=2, GroupingIdentifier=photos)
    loaded_count = add('count', WFInput=ref(results, 'Repeat Results'), Input=ref(results, 'Repeat Results'))
    loaded_text = add('gettext', WFTextActionText=token(loaded_count, 'Count'))
    invalid = condition(ref(loaded_text, 'Text'), 5, token(expected_count, 'Text'))
    stop('Не удалось загрузить все фотографии. Запись не создана.')
    end(invalid)
    journal(ref(results, 'Repeat Results'))
    end(no_photos)
    workflow['WFWorkflowActions'] = actions
    workflow['WFWorkflowHasShortcutInputVariables'] = True
    workflow['WFWorkflowInputContentItemClasses'] = ['WFGenericFileContentItem', 'WFFolderContentItem']
    return workflow


if __name__ == '__main__':
    workflow = build()
    (ROOT / 'shortcuts/StoicMacWriterV3.plist').write_bytes(plistlib.dumps(workflow))
    Path('/tmp/StoicMacWriterV3-unsigned.shortcut').write_bytes(plistlib.dumps(workflow, fmt=plistlib.FMT_BINARY))
    print('Generated Mac writer v3 source and unsigned binary. No diary content included.')
