import sys
import tempfile
import json
import unittest
import zipfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
import build_batch_shortcut as builder
from prepare_batch import prepare,optional_title

class Stopped(Exception):pass

class OfflineBatch:
    """Small evaluator for this workflow only. Does not model Apple persistence."""
    def __init__(self,payload):self.payload=payload;self.outputs={};self.item=None;self.writes=[];self.variables={};self.alerts=[]
    def value(self,v):
        if not isinstance(v,dict):return v
        if 'WFSerializationType' in v:return self.value(v['Value'])
        if v.get('Type')=='ActionOutput':return self.outputs.get(v['OutputUUID'])
        if v.get('Type')=='Variable':return self.item if v['VariableName']=='Repeat Item' else self.variables.get(v['VariableName'])
        if 'string' in v:
            value = self.value(next(iter(v['attachmentsByRange'].values())))
            return v['string'].replace('\ufffc', '' if value is None else str(value))
        return v
    def dictionary_input(self,value):return self.payload
    def dictionary_value(self, value):
        # A lone variable in this field supplies the original typed content.
        if isinstance(value, dict) and value.get('WFSerializationType') == 'WFTextTokenString':
            text = value['Value']
            if text.get('string') == '\ufffc' and set(text.get('attachmentsByRange', {})) == {'{0, 1}'}:
                return self.value(text['attachmentsByRange']['{0, 1}'])
        return self.value(value)
    def external(self,ident,p):raise AssertionError(ident)
    def journal_write(self,p):
        self.writes.append({k:self.value(v) for k,v in p.items() if k in ['title','entryDate','message','mediaItems']})
    def menu_choice(self,p):return p['WFMenuItems'][0]
    def run(self,actions):
        i=0
        while i<len(actions):
            a=actions[i];p=a['WFWorkflowActionParameters'];kind=a['WFWorkflowActionIdentifier'].split('.')[-1]
            ident=a['WFWorkflowActionIdentifier'];result=None
            if kind=='choosefrommenu':
                group=p['GroupingIdentifier'];j=i+1;branches=[]
                while j<len(actions):
                    ep=actions[j]['WFWorkflowActionParameters']
                    if ep.get('GroupingIdentifier')==group:
                        if ep.get('WFControlFlowMode')==1:branches.append(j)
                        if ep.get('WFControlFlowMode')==2:break
                    j+=1
                choice=self.menu_choice(p)
                for index,branch in enumerate(branches):
                    if actions[branch]['WFWorkflowActionParameters']['WFMenuItemTitle']==choice:
                        self.run(actions[branch+1:(branches[index+1] if index+1<len(branches) else j)])
                        break
                i=j+1;continue
            if ident.endswith('repeat.each') or kind=='conditional':
                group=p['GroupingIdentifier'];end=i+1;other=None
                while end<len(actions):
                    ep=actions[end]['WFWorkflowActionParameters']
                    if ep.get('GroupingIdentifier')==group:
                        if ep.get('WFControlFlowMode')==1:other=end
                        if ep.get('WFControlFlowMode')==2:break
                    end+=1
                if ident.endswith('repeat.each'):
                    for item in self.value(p['WFInput']):
                        self.item=item;self.run(actions[i+1:end])
                else:
                    v=self.value(p['WFInput']['Variable']);code=p['WFCondition']
                    present=v is not None and v!='' and v!=[]
                    expected=self.value(p.get('WFConditionalActionString',p.get('WFNumberValue')))
                    if code in [0,1,2,3]:
                        left,right=float(v),float(expected)
                        check={0:left<right,1:left<=right,2:left>right,3:left>=right}[code]
                    else:check=present if code==100 else (not present if code==101 else (v==expected if code==4 else v!=expected))
                    if check:self.run(actions[i+1:(other if other else end)])
                    elif other is not None:self.run(actions[other+1:end])
                i=end+1;continue
            if kind=='select':result='selected-folder' if p.get('WFPickingMode')=='Folders' else 'selected-file'
            elif ident=='is.workflow.actions.dictionary':result={}
            elif kind=='dictionary':result=self.dictionary_input(self.value(p['WFInput']))
            elif kind=='getvalueforkey':result=self.value(p['WFInput']).get(self.value(p['WFDictionaryKey']))
            elif kind=='setvariable':self.variables[p['WFVariableName']]=self.value(p['WFInput'])
            elif kind=='setvalueforkey':
                result=dict(self.value(p['WFDictionary']));result[self.value(p['WFDictionaryKey'])]=self.dictionary_value(p['WFDictionaryValue'])
            elif kind=='gettext':result=self.value(p['WFTextActionText'])
            elif kind=='count':result=len(self.value(p['WFInput']))
            elif ident=='com.apple.journal.CreateEntryIntent':
                self.journal_write(p)
            elif kind=='alert':self.alerts.append(self.value(p.get('WFAlertActionMessage','')))
            elif kind=='exit':raise Stopped()
            elif kind not in ['comment','previewdocument','alert','delay','nothing']:result=self.external(ident,p)
            if p.get('UUID'):self.outputs[p['UUID']]=result
            i+=1

class BatchTests(unittest.TestCase):
    def payload(self):
        return dict(schema='stoic-test-batch-v1',preview='Synthetic preview',entries=[dict(
            sourceID=str(i),date='2001-02-04T12:00:00Z',title=('A title' if i%2 else ''),text=f'Synthetic {i}',attachmentCount=0) for i in range(10)])
    def test_ten_writes_optional_titles_and_preserved_values(self):
        sim=OfflineBatch(self.payload());sim.run(builder.build()['WFWorkflowActions'])
        self.assertEqual(len(sim.writes),10)
        for i,w in enumerate(sim.writes):
            self.assertEqual(w['message'],f'Synthetic {i}')
            self.assertEqual(w['entryDate'],'2001-02-04T12:00:00Z')
            self.assertEqual('title' in w,bool(i%2))
    def test_bad_last_record_stops_before_any_write(self):
        payload=self.payload();payload['entries'][-1]['text']=''
        sim=OfflineBatch(payload)
        with self.assertRaises(Stopped):sim.run(builder.build()['WFWorkflowActions'])
        self.assertEqual(sim.writes,[])
    def test_wrong_count_and_media_are_rejected(self):
        for mode in ['count','media','schema']:
            p=self.payload()
            if mode=='count':p['entries'].pop()
            if mode=='media':p['entries'][-1]['attachmentCount']=1
            if mode=='schema':p['schema']='wrong'
            sim=OfflineBatch(p)
            with self.assertRaises(Stopped):sim.run(builder.build()['WFWorkflowActions'])
            self.assertEqual(sim.writes,[])
    def test_title_limit_omits_title_without_truncating(self):
        self.assertEqual(optional_title('я'*79),'я'*79)
        self.assertEqual(optional_title('я'*80),'')
        self.assertEqual(optional_title('Первое событие\nВторое событие'), 'Первое событие')
    def test_prepare_ten_latest_sessions_excludes_prior_test_ids(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'synthetic.zip';answers=[];routines=[]
            for i in range(12):
                routines.append(dict(uuid=f'r{i}',date='01/01/2025',isCompleted=True,questions=['q']))
                answers.append(dict(uuid=f'a{i}',routine=f'r{i}',question='q',text=f'Synthetic {i}',timestamp=1735689600000+i*1000))
            with zipfile.ZipFile(p,'w') as z:
                z.writestr('answers.json',json.dumps(answers));z.writestr('routines.json',json.dumps(routines))
            entries=prepare(p,excluded_ids={'r11'})
            self.assertEqual(len(entries),10)
            self.assertEqual(entries[0]['sourceID'],'r1');self.assertEqual(entries[-1]['sourceID'],'r10')

if __name__=='__main__':unittest.main()
