#!/usr/bin/env python3
"""Read-only ZIP preview with labelled checks before dynamic dictionary lookups."""
import plistlib
from pathlib import Path

from build_raw_backup_shortcut import build as build_preview
from build_single_entry_shortcut import ROOT, ref, text_input, token, uid


def build():
    workflow = build_preview(include_import=False)
    actions = []
    lookup = 0

    def add(name, **parameters):
        parameters.setdefault('UUID', uid())
        actions.append({'WFWorkflowActionIdentifier': 'is.workflow.actions.' + name,
                        'WFWorkflowActionParameters': parameters})
        return parameters['UUID']

    for action in workflow['WFWorkflowActions']:
        parameters = action['WFWorkflowActionParameters']
        if action['WFWorkflowActionIdentifier'] == 'is.workflow.actions.getvalueforkey':
            lookup += 1
            key = parameters['WFDictionaryKey']
            if isinstance(key, dict):
                attachment = next(iter(text_input(key)['Value']['attachmentsByRange'].values()))
                source = attachment.get('VariableName', attachment.get('OutputName', 'key'))
                label = f'K{lookup:02d} ({source})'
                add('comment', WFCommentActionText='KEY DIAGNOSTIC ' + label)
                rendered = add('gettext', WFTextActionText=text_input(key))
                group = uid()
                add('conditional', GroupingIdentifier=group, WFControlFlowMode=0,
                    WFCondition=101, WFInput={'Type': 'Variable', 'Variable': ref(rendered, 'Text')})
                add('alert', WFAlertActionTitle='Пустой ключ: ' + label,
                    WFAlertActionMessage='Диагностика V6. Запишите код из заголовка. '
                    'Переменная ключа пуста до чтения словаря. Импорт отключён.',
                    WFAlertActionCancelButtonShown=False)
                add('exit')
                add('conditional', GroupingIdentifier=group, WFControlFlowMode=2)
                # The dictionary action now reads a concrete Text action output,
                # rather than an implicit Repeat Item / named-variable binding.
                parameters['WFDictionaryKey'] = token(rendered, 'Text')
        actions.append(action)
    workflow['WFWorkflowActions'] = actions
    return workflow


if __name__ == '__main__':
    workflow = build()
    (ROOT / 'shortcuts/StoicKeyDiagnosticV6.plist').write_bytes(plistlib.dumps(workflow))
    Path('/tmp/StoicKeyDiagnosticV6-unsigned.shortcut').write_bytes(
        plistlib.dumps(workflow, fmt=plistlib.FMT_BINARY))
    print('Generated read-only V6 key diagnostic. No Journal or registry writes.')
