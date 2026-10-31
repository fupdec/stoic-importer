#!/usr/bin/env python3
"""Return the writer's loaded files without invoking Journal or writing receipts."""
import copy
import plistlib
from pathlib import Path

from build_mac_writer_shortcut import build as build_writer
from build_single_entry_shortcut import ROOT, uid, text_input


def build():
    workflow = copy.deepcopy(build_writer())
    for action in workflow['WFWorkflowActions']:
        params = action['WFWorkflowActionParameters']
        if action['WFWorkflowActionIdentifier'] == 'com.apple.journal.CreateEntryIntent':
            media = params.get('mediaItems', '')
            action['WFWorkflowActionIdentifier'] = 'is.workflow.actions.output'
            action['WFWorkflowActionParameters'] = {
                'UUID': uid(), 'WFOutput': text_input(media), 'WFResponse': 'Do Nothing'}
        elif action['WFWorkflowActionIdentifier'] == 'is.workflow.actions.comment':
            params['WFCommentActionText'] = (
                'Stoic media diagnostic. NO Journal actions. Reads a prepared folder '
                'using the V3 loader and returns its files for byte comparison. '
                'Use synthetic input only; no ledger, network or import.')
    assert all(a['WFWorkflowActionIdentifier'].startswith('is.workflow.actions.')
               for a in workflow['WFWorkflowActions'])
    return workflow


if __name__ == '__main__':
    workflow = build()
    (ROOT / 'shortcuts/StoicMacMediaDiagnostic.plist').write_bytes(plistlib.dumps(workflow))
    Path('/tmp/StoicMacMediaDiagnostic-unsigned.shortcut').write_bytes(
        plistlib.dumps(workflow, fmt=plistlib.FMT_BINARY))
    print('Generated diagnostic with no Journal actions.')
