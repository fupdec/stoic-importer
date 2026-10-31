import sys
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
from prepare_one_photo_entry import prepare
from build_single_photo_shortcut import build_photo

class PhotoTests(unittest.TestCase):
    def archive(self, folder, duplicate=False):
        p=Path(folder)/'synthetic.zip'
        with zipfile.ZipFile(p,'w') as z:
            z.writestr('answers.json',json.dumps([{'uuid':'a','routine':'r','timestamp':1735689600000,
                'text':'Synthetic photo memory','question':'What happened?','assets':['p'] * (2 if duplicate else 1)}]))
            z.writestr('routines.json',json.dumps([{'uuid':'r','date':'01/01/2025','questions':['What happened?']}]))
            z.writestr('assets.json',json.dumps([{'uuid':'p','answer':'a','relativePath':'photos/photo.jpg','type':'image'}]))
            z.writestr('photos/photo.jpg',b'synthetic-image-bytes')
        return p

    def test_photo_bytes_and_owner_instant_preserved(self):
        with tempfile.TemporaryDirectory() as folder:
            payload,photo=prepare(self.archive(folder))
            self.assertEqual(photo,b'synthetic-image-bytes')
            self.assertEqual(payload['date'],'2025-01-01T00:00:00.000Z')
            self.assertEqual(payload['attachmentCount'],1)
            self.assertEqual(payload['title'],'What happened?')
            self.assertEqual(payload['text'],'Synthetic photo memory')
            self.assertEqual(payload['sourceText'],'What happened?\n\nSynthetic photo memory')

    def test_multiple_media_refs_not_silently_truncated(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(ValueError): prepare(self.archive(folder,True))

    def test_photo_selection_preview_and_final_confirmation_precede_single_write(self):
        a=build_photo()['WFWorkflowActions']
        writes=[i for i,x in enumerate(a) if x['WFWorkflowActionIdentifier']=='com.apple.journal.CreateEntryIntent']
        self.assertEqual(len(writes),2)
        from test_batch import OfflineBatch
        for title in ['Synthetic title', '']:
            sim=OfflineBatch(dict(schema='stoic-single-entry-v1',title=title,date='2001-02-04T12:00:00Z',text='Body',attachmentCount=1,attachmentFileName='synthetic.jpg'))
            sim.run(a)
            self.assertEqual(len(sim.writes),1)
            self.assertEqual('title' in sim.writes[0],bool(title))
            self.assertEqual(sim.writes[0]['mediaItems'],'selected-file')
        write=writes[0]
        media=a[write]['WFWorkflowActionParameters']['mediaItems']['Value']['OutputUUID']
        picker=next(i for i,x in enumerate(a) if x['WFWorkflowActionParameters'].get('UUID')==media)
        self.assertEqual(a[picker]['WFWorkflowActionIdentifier'],'is.workflow.actions.file.select')
        preview=next(i for i,x in enumerate(a) if x['WFWorkflowActionIdentifier']=='is.workflow.actions.previewdocument')
        self.assertNotIn('is.workflow.actions.quicklook', [x['WFWorkflowActionIdentifier'] for x in a])
        self.assertEqual(a[preview]['WFWorkflowActionParameters']['WFInput']['Value']['OutputUUID'], media)
        self.assertLess(picker,preview)
        self.assertLess(preview,write)
        self.assertEqual(a[write-2]['WFWorkflowActionIdentifier'],'is.workflow.actions.alert')
        self.assertTrue(a[write-2]['WFWorkflowActionParameters']['WFAlertActionCancelButtonShown'])
        ids=[x['WFWorkflowActionIdentifier'] for x in a]
        self.assertEqual(ids.count('is.workflow.actions.file.select'),2)
        self.assertFalse(any('askllm' in x or 'download' in x or 'repeat' in x for x in ids))

if __name__=='__main__':unittest.main()
