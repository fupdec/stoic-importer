import copy
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
from build_ledger_shortcut import build_ledger,LEDGER_SCHEMA
from build_batch_shortcut import build as build_batch
from test_batch import OfflineBatch,Stopped

class RegistrySim(OfflineBatch):
    def __init__(self,payload,ledger=None,fail_save=None):
        super().__init__(payload);self.disk=copy.deepcopy(ledger);self.saves=0;self.fail_save=fail_save;self.manual=False;self.searches=[];self.review='Запись уже есть — пропустить'
    def dictionary_input(self,value):
        return copy.deepcopy(self.disk) if value=='ledger-file' else self.payload
    def menu_choice(self,p):
        if 'Как проверять' in p.get('WFMenuPrompt',''):
            return 'Также открыть поиск Journal перед новой записью' if self.manual else 'Только UUID-реестр'
        return self.review
    def external(self,ident,p):
        if ident=='com.apple.journal.SearchEntriesIntent':self.searches.append(self.value(p['criteria']));return None
        if ident.endswith('documentpicker.open'):return 'ledger-file' if self.disk is not None else None
        if ident.endswith('documentpicker.save'):
            self.saves+=1
            if self.saves==self.fail_save:raise OSError('synthetic save failure')
            self.disk=copy.deepcopy(self.value(p['WFInput']));return 'ledger-file'
        raise AssertionError(ident)

class LedgerTests(unittest.TestCase):
    def payload(self):
        return dict(schema='stoic-test-batch-v1',preview='Synthetic',entries=[dict(sourceID=f'00000000-0000-4000-8000-{i:012d}',date='2001-02-04T12:00:00Z',title='',text=f'Synthetic {i}',attachmentCount=0) for i in range(10)])
    def workflow(self):return build_ledger(build_batch())['WFWorkflowActions']
    def test_first_run_records_ids_second_run_skips_every_write(self):
        first=RegistrySim(self.payload());first.run(self.workflow())
        self.assertEqual(len(first.writes),10)
        self.assertEqual(len(first.disk),11)
        self.assertEqual(first.saves,21)
        self.assertEqual(first.disk['__schema__'],LEDGER_SCHEMA)
        self.assertTrue(all(first.disk[e['sourceID']]=='action-returned' for e in self.payload()['entries']))
        second=RegistrySim(self.payload(),first.disk);second.run(self.workflow())
        self.assertEqual(second.writes,[])
    def test_pending_or_unknown_receipt_stops_before_retry(self):
        for status in ['pending','unexpected']:
            key=self.payload()['entries'][0]['sourceID']
            sim=RegistrySim(self.payload(),{'__schema__':LEDGER_SCHEMA,key:status})
            with self.assertRaises(Stopped):sim.run(self.workflow())
            self.assertEqual(sim.writes,[])
    def test_failed_pending_save_causes_no_journal_write(self):
        sim=RegistrySim(self.payload(),fail_save=2)
        with self.assertRaises(OSError):sim.run(self.workflow())
        self.assertEqual(sim.writes,[])
    def test_failed_post_write_save_leaves_pending_and_blocks_retry(self):
        sim=RegistrySim(self.payload(),fail_save=3)
        with self.assertRaises(OSError):sim.run(self.workflow())
        self.assertEqual(len(sim.writes),1)
        key=self.payload()['entries'][0]['sourceID'];self.assertEqual(sim.disk[key],'pending')
        retry=RegistrySim(self.payload(),sim.disk)
        with self.assertRaises(Stopped):retry.run(self.workflow())
        self.assertEqual(retry.writes,[])
    def test_invalid_ledger_is_not_overwritten(self):
        sim=RegistrySim(self.payload(),{'wrong':'file'})
        with self.assertRaises(Stopped):sim.run(self.workflow())
        self.assertEqual(sim.saves,0);self.assertEqual(sim.disk,{'wrong':'file'})
    def test_zip_preview_branch_does_not_read_or_write_registry(self):
        actions=build_ledger()['WFWorkflowActions']
        menu_id=next(a['WFWorkflowActionParameters']['GroupingIdentifier'] for a in actions if a['WFWorkflowActionIdentifier']=='is.workflow.actions.choosefrommenu')
        branches=[i for i,a in enumerate(actions) if a['WFWorkflowActionIdentifier']=='is.workflow.actions.choosefrommenu' and a['WFWorkflowActionParameters']['GroupingIdentifier']==menu_id]
        preview=actions[branches[1]:branches[2]]
        self.assertFalse(any('documentpicker' in a['WFWorkflowActionIdentifier'] or a['WFWorkflowActionIdentifier']=='com.apple.journal.CreateEntryIntent' for a in preview))
        # Every action reference must point to an earlier output, including both media branches.
        seen=set()
        def refs(v):
            if isinstance(v,dict):
                if 'OutputUUID' in v:yield v['OutputUUID']
                for x in v.values():yield from refs(x)
            elif isinstance(v,list):
                for x in v:yield from refs(x)
        for a in actions:
            p=a['WFWorkflowActionParameters']
            for reference in refs(p):self.assertIn(reference,seen)
            seen.add(p['UUID'])

    def test_manual_search_confirmation_records_skip_without_creating(self):
        payload=self.payload()
        for e in payload['entries']:e['title']='Synthetic search title'
        sim=RegistrySim(payload);sim.manual=True;sim.run(self.workflow())
        self.assertEqual(sim.writes,[])
        self.assertEqual(len(sim.searches),10)
        self.assertTrue(all(sim.disk[e['sourceID']]=='manual-confirmed' for e in payload['entries']))
        second=RegistrySim(payload,sim.disk);second.run(self.workflow())
        self.assertEqual(second.writes,[])

    def test_registry_only_variant_has_no_journal_search(self):
        actions=build_ledger(build_batch(), include_search=False)['WFWorkflowActions']
        self.assertFalse(any(a['WFWorkflowActionIdentifier']=='com.apple.journal.SearchEntriesIntent' for a in actions))
        sim=RegistrySim(self.payload());sim.run(actions)
        self.assertEqual(len(sim.writes),10)
        retry=RegistrySim(self.payload(),sim.disk);retry.run(actions)
        self.assertEqual(retry.writes,[])

    def test_verification_has_no_create_actions_and_repeat_skips(self):
        workflow=build_ledger(build_batch(),verification_only=True)['WFWorkflowActions']
        self.assertFalse(any(a['WFWorkflowActionIdentifier']=='com.apple.journal.CreateEntryIntent' for a in workflow))
        payload=self.payload()
        for e in payload['entries']:e['title']='Existing synthetic entry'
        sim=RegistrySim(payload);sim.manual=True;sim.run(workflow)
        self.assertEqual(len(sim.searches),10)
        self.assertEqual(sim.writes,[])
        self.assertTrue(all(sim.disk[e['sourceID']]=='manual-confirmed' for e in payload['entries']))
        retry=RegistrySim(payload,sim.disk);retry.run(workflow)
        self.assertEqual(retry.searches,[])
        self.assertEqual(retry.writes,[])

    def test_verification_absent_entry_stops_without_receipt(self):
        workflow=build_ledger(build_batch(),verification_only=True)['WFWorkflowActions']
        payload=self.payload()
        for e in payload['entries']:e['title']='Missing synthetic entry'
        sim=RegistrySim(payload);sim.manual=True;sim.review='Совпадений нет — остановить'
        with self.assertRaises(Stopped):sim.run(workflow)
        self.assertEqual(sim.disk,{'__schema__':LEDGER_SCHEMA})
        self.assertEqual(sim.writes,[])

    def test_verification_requires_manual_review(self):
        with self.assertRaises(ValueError):build_ledger(include_search=False,verification_only=True)

if __name__=='__main__':unittest.main()
