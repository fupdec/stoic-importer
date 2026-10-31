#!/usr/bin/env python3
"""Development-only generator. The resulting Shortcut runs only native actions."""
import plistlib
from pathlib import Path
from build_single_entry_shortcut import ROOT
from build_raw_backup_shortcut import build as build_raw
from build_ledger_shortcut import build_ledger


def build():
    workflow = build_ledger(build_raw(include_import=True), include_search=True)
    for action in workflow['WFWorkflowActions']:
        if action['WFWorkflowActionIdentifier'] == 'is.workflow.actions.comment':
            action['WFWorkflowActionParameters']['WFCommentActionText'] = (
                'ORIGINAL STOIC ZIP → JOURNAL. Native Shortcuts actions only. '
                'Preview is the default; import requires registry selection, batch preview '
                'and confirmation. Up to 10 new review-cleared records per run. '
                'Unassigned answers and unresolved scales are excluded. Receipt is not '
                'proof of Journal persistence. Run on one device at a time. '
                'Integration is not runtime-verified. Journal descriptor adapted from '
                'jeffd/DayOneToJournal (MIT; UPSTREAM-LICENSE).')
    return workflow


if __name__ == '__main__':
    workflow = build()
    (ROOT / 'shortcuts/StoicToJournal.plist').write_bytes(plistlib.dumps(workflow))
    Path('/private/tmp/StoicToJournal-unsigned.shortcut').write_bytes(plistlib.dumps(workflow, fmt=plistlib.FMT_BINARY))
    print('Generated unified original-ZIP workflow source. Signing and runtime QA still required.')
