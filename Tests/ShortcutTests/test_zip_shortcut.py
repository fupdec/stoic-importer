import sys
import unittest
import re
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
from build_zip_shortcut import build

class ZIPTests(unittest.TestCase):
    def test_one_picker_and_correct_native_unpack_input(self):
        actions=build()['WFWorkflowActions']
        pickers=[a for a in actions if a['WFWorkflowActionIdentifier']=='is.workflow.actions.file.select']
        self.assertEqual(len(pickers),1)
        extract=next(a for a in actions if a['WFWorkflowActionIdentifier']=='is.workflow.actions.unzip')
        self.assertEqual(extract['WFWorkflowActionParameters']['WFArchive']['Value']['OutputUUID'],pickers[0]['WFWorkflowActionParameters']['UUID'])
        self.assertNotIn('WFInput',extract['WFWorkflowActionParameters'])

    def test_preview_only_branch_has_no_write(self):
        actions=build()['WFWorkflowActions']
        choices=[i for i,a in enumerate(actions) if a['WFWorkflowActionIdentifier']=='is.workflow.actions.choosefrommenu']
        self.assertEqual(len(choices),4)
        preview=actions[choices[1]+1:choices[2]]
        self.assertFalse(any(a['WFWorkflowActionIdentifier']=='com.apple.journal.CreateEntryIntent' for a in preview))
        self.assertEqual(preview[-1]['WFWorkflowActionIdentifier'],'is.workflow.actions.exit')
        self.assertTrue(any(a['WFWorkflowActionIdentifier']=='is.workflow.actions.previewdocument' for a in preview))
        self.assertTrue(any(a['WFWorkflowActionIdentifier']=='is.workflow.actions.getitemname' for a in preview))
        self.assertTrue(any(a['WFWorkflowActionIdentifier']=='is.workflow.actions.text.replace' for a in preview))

    def test_photo_and_preview_use_automatically_filtered_file(self):
        actions=build()['WFWorkflowActions']
        photo=next(a for a in actions if a['WFWorkflowActionIdentifier']=='com.apple.journal.CreateEntryIntent' and 'mediaItems' in a['WFWorkflowActionParameters'])
        media_id=photo['WFWorkflowActionParameters']['mediaItems']['Value']['OutputUUID']
        filtered=next(a for a in actions if a['WFWorkflowActionParameters']['UUID']==media_id)
        self.assertEqual(filtered['WFWorkflowActionIdentifier'],'is.workflow.actions.filter.files')
        self.assertTrue(any(a['WFWorkflowActionIdentifier']=='is.workflow.actions.previewdocument' and a['WFWorkflowActionParameters']['WFInput']['Value'].get('OutputUUID')==media_id for a in actions))
        self.assertTrue(any(a['WFWorkflowActionIdentifier']=='is.workflow.actions.getitemname' and a['WFWorkflowActionParameters']['WFInput']['Value'].get('OutputUUID')==media_id for a in actions))

    def test_all_action_references_point_to_existing_prior_outputs(self):
        actions=build()['WFWorkflowActions'];seen=set()
        def refs(v):
            if isinstance(v,dict):
                if 'OutputUUID' in v:yield v['OutputUUID']
                for x in v.values():yield from refs(x)
            elif isinstance(v,list):
                for x in v:yield from refs(x)
        for a in actions:
            p=a['WFWorkflowActionParameters']
            for reference in refs(p):self.assertIn(reference,seen)
            self.assertNotIn(p['UUID'],seen);seen.add(p['UUID'])
        identifiers={a['WFWorkflowActionIdentifier'] for a in actions}
        self.assertFalse(any('download' in i or 'askllm' in i or 'runshell' in i for i in identifiers))

    def test_name_normalization_preserves_mismatch_detection(self):
        actions=build()['WFWorkflowActions']
        replacements=[a['WFWorkflowActionParameters'] for a in actions if a['WFWorkflowActionIdentifier']=='is.workflow.actions.text.replace']
        extension=next(p for p in replacements if p['WFReplaceTextFind']==r'^.*\.')
        stem=next(p for p in replacements if p['WFReplaceTextFind']==r'\.[^.]+$')
        replace=lambda p,text:re.sub(p['WFReplaceTextFind'],p['WFReplaceTextReplace'],text)
        expected='stoic-test-photo.heic'
        self.assertEqual(replace(extension,expected),'heic')
        for actual in ['stoic-test-photo','stoic-test-photo.heic']:
            self.assertEqual(replace(stem,actual),replace(stem,expected))
        self.assertNotEqual(replace(stem,'other-stoic-test-photo.heic'),replace(stem,expected))
        filtered=[a['WFWorkflowActionParameters'] for a in actions if a['WFWorkflowActionIdentifier']=='is.workflow.actions.filter.files']
        self.assertTrue(any(any(t['Property']=='File Extension' and isinstance(t['Values']['String'],dict)
                                for t in p['WFContentItemFilter']['Value']['WFActionParameterFilterTemplates']) for p in filtered))

if __name__=='__main__':unittest.main()
