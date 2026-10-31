#!/usr/bin/env python3
"""Optional GPS from the first photo only. Never requests the current location."""
import copy
import plistlib
from pathlib import Path
from build_mac_writer_shortcut import build as base_writer
from build_single_entry_shortcut import ROOT, uid, ref, token

VARIABLE = 'StoicFirstPhotoLocation'


def location_actions():
    actions = []
    def add(name, **params):
        params.setdefault('UUID', uid())
        actions.append(dict(WFWorkflowActionIdentifier='is.workflow.actions.' + name,
                            WFWorkflowActionParameters=params))
        return params['UUID']
    # Reset on every invocation, including entries without coordinates.
    empty = add('nothing')
    add('setvariable', WFVariableName=VARIABLE, WFInput=ref(empty, 'Nothing'))
    shortcut_input = {'Value': {'Type': 'ExtensionInput'}, 'WFSerializationType': 'WFTextTokenAttachment'}
    payload = add('documentpicker.open', WFFile=shortcut_input, WFGetFilePath='entry.json', WFFileErrorIfNotFound=True)
    dictionary = add('detect.dictionary', WFInput=ref(payload, 'File'))
    filename = add('getvalueforkey', WFDictionaryKey='locationFileName', WFInput=ref(dictionary))
    text = add('gettext', WFTextActionText=token(filename, 'Dictionary Value'))
    group = uid()
    add('conditional', WFControlFlowMode=0, GroupingIdentifier=group, WFCondition=100,
        WFInput={'Type': 'Variable', 'Variable': ref(text, 'Text')})
    image = add('documentpicker.open', WFFile=shortcut_input, WFGetFilePath=token(text, 'Text'), WFFileErrorIfNotFound=True)
    location = add('properties.images', WFContentItemPropertyName='Location', WFInput=ref(image, 'File'))
    add('setvariable', WFVariableName=VARIABLE, WFInput=ref(location, 'Location'))
    add('conditional', WFControlFlowMode=2, GroupingIdentifier=group)
    return actions


def build(diagnostic=False):
    workflow = copy.deepcopy(base_writer())
    prefix = location_actions()
    location = {'Value': {'Type': 'Variable', 'VariableName': VARIABLE}, 'WFSerializationType': 'WFTextTokenAttachment'}
    if diagnostic:
        workflow['WFWorkflowActions'] = prefix
    else:
        for action in workflow['WFWorkflowActions']:
            if action['WFWorkflowActionIdentifier'] == 'com.apple.journal.CreateEntryIntent':
                action['WFWorkflowActionParameters']['location'] = location
        workflow['WFWorkflowActions'][1:1] = prefix
    return workflow


if __name__ == '__main__':
    for name, diagnostic in [('StoicMacWriterWithLocation', False), ('StoicPhotoLocationLoader', True)]:
        workflow = build(diagnostic)
        (ROOT / ('shortcuts/' + name + '.plist')).write_bytes(plistlib.dumps(workflow))
        Path('/tmp/' + name + '-unsigned.shortcut').write_bytes(plistlib.dumps(workflow, fmt=plistlib.FMT_BINARY))
