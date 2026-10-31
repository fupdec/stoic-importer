import unittest

from build_key_diagnostic_shortcut import build
import test_raw_backup as raw_backup
from test_batch import Stopped


class KeyDiagnosticTests(unittest.TestCase):
    def test_preview_has_no_import_or_file_writes(self):
        actions = build()['WFWorkflowActions']
        self.assertFalse(any(a['WFWorkflowActionIdentifier'].startswith('com.apple.journal.')
                             or a['WFWorkflowActionIdentifier'] == 'is.workflow.actions.documentpicker.save'
                             for a in actions))
        sim = raw_backup.RawSim(raw_backup.RawBackupTests().linked_files(), assemble=True)
        sim.run(actions)
        self.assertEqual(len(sim.variables['StoicPlan']), 3)
        self.assertEqual(sim.writes, [])

    def test_empty_dynamic_key_stops_with_operation_label(self):
        class EmptyKeySim(raw_backup.RawSim):
            def value(self, value):
                # A missing named-variable binding at native runtime.
                if isinstance(value, dict) and value.get('Type') == 'Variable' and value.get('VariableName') == 'SourceKey':
                    return None
                return super().value(value)

        actions = build()['WFWorkflowActions']
        sim = EmptyKeySim(raw_backup.RawBackupTests().linked_files(), assemble=True)
        with self.assertRaises(Stopped):
            sim.run(actions)
        self.assertIn('Переменная ключа пуста', sim.alerts[-1])
        self.assertEqual(sim.writes, [])
        titles = [a['WFWorkflowActionParameters'].get('WFAlertActionTitle', '') for a in actions]
        self.assertTrue(any(t.startswith('Пустой ключ: K') and 'SourceKey' in t for t in titles))
