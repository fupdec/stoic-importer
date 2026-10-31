#!/usr/bin/env python3
"""A bounded text-only batch importer with preflight and optional titles."""
import copy
import plistlib
from pathlib import Path
from build_single_entry_shortcut import ROOT,uid,ref,token


def build():
    workflow=plistlib.loads((ROOT/'shortcuts/HistoricalDateProbe.plist').read_bytes())
    descriptor=copy.deepcopy(workflow['WFWorkflowActions'][0])
    actions=[]
    def add(name,**params):
        params.setdefault('UUID',uid())
        actions.append(dict(WFWorkflowActionIdentifier='is.workflow.actions.'+name,WFWorkflowActionParameters=params))
        return params['UUID']
    def variable(name):
        return {'Value':{'Type':'Variable','VariableName':name},'WFSerializationType':'WFTextTokenAttachment'}
    def get(key,input):return add('getvalueforkey',WFDictionaryKey=key,WFInput=input)
    def stop_if(subject,condition,message,**values):
        group=uid()
        add('conditional',WFControlFlowMode=0,GroupingIdentifier=group,WFCondition=condition,
            WFInput={'Type':'Variable','Variable':subject},**values)
        add('alert',WFAlertActionTitle='Импорт остановлен',WFAlertActionMessage=message,WFAlertActionCancelButtonShown=False)
        add('exit')
        add('conditional',WFControlFlowMode=2,GroupingIdentifier=group)
    add('comment',WFCommentActionText='Test batch of 10 text-only sessions. Pick stoic-batch-10.json, NOT ZIP. No AI/network. No ledger: never rerun without checking Journal. Journal descriptor: jeffd/DayOneToJournal MIT.')
    file=add('file.select',WFPickingMode='Files',WFSelectMultiple=False)
    data=add('detect.dictionary',WFInput=ref(file,'File'))
    schema=get('schema',ref(data))
    text=add('gettext',WFTextActionText=token(schema,'Dictionary Value'))
    stop_if(ref(text,'Text'),5,'Выберите stoic-batch-10.json из распакованной папки.',WFConditionalActionString='stoic-test-batch-v1')
    entries=get('entries',ref(data))
    count=add('count',WFInput=ref(entries,'Dictionary Value'),Input=ref(entries,'Dictionary Value'))
    stop_if(ref(count,'Count'),5,'Тестовая партия должна содержать ровно 10 записей.',WFNumberValue=10)
    # Validate every record BEFORE any write; title is optional.
    group=uid()
    add('repeat.each',WFControlFlowMode=0,GroupingIdentifier=group,WFInput=ref(entries,'Dictionary Value'))
    for key in ['sourceID','date','text']:
        value=get(key,variable('Repeat Item'))
        stop_if(ref(value,'Dictionary Value'),101,'В партии отсутствуют ID, дата или текст. Ни одной записи не создано.')
    media=get('attachmentCount',variable('Repeat Item'))
    media_text=add('gettext',WFTextActionText=token(media,'Dictionary Value'))
    stop_if(ref(media_text,'Text'),5,'Эта партия поддерживает только текстовые записи без фото.',WFConditionalActionString='0')
    add('repeat.each',WFControlFlowMode=2,GroupingIdentifier=group)
    preview=get('preview',ref(data))
    add('previewdocument',WFInput=ref(preview,'Dictionary Value'))
    add('alert',WFAlertActionTitle='Создать 10 записей?',WFAlertActionMessage='Прочитайте предпросмотр. Продолжить — создать 10 новых записей без фотографий. Держите iPhone разблокированным около двух минут. Повторный запуск создаст дубликаты. При сбое сначала проверьте Journal.',WFAlertActionCancelButtonShown=True)
    group=uid()
    add('repeat.each',WFControlFlowMode=0,GroupingIdentifier=group,WFInput=ref(entries,'Dictionary Value'))
    values={key:get(key,variable('Repeat Item')) for key in ['title','date','text']}
    title=add('gettext',WFTextActionText=token(values['title'],'Dictionary Value'))
    condition=uid()
    add('conditional',WFControlFlowMode=0,GroupingIdentifier=condition,WFCondition=100,WFInput={'Type':'Variable','Variable':ref(title,'Text')})
    def write(with_title):
        action=copy.deepcopy(descriptor)
        p=action['WFWorkflowActionParameters']
        p.update(UUID=uid(),entryDate=token(values['date'],'Dictionary Value'),message=token(values['text'],'Dictionary Value'))
        if with_title:p['title']=token(title,'Text')
        else:p.pop('title',None)
        actions.append(action)
    write(True)
    add('conditional',WFControlFlowMode=1,GroupingIdentifier=condition)
    write(False)
    add('conditional',WFControlFlowMode=2,GroupingIdentifier=condition)
    add('delay',WFDelayTime=10.0)
    add('repeat.each',WFControlFlowMode=2,GroupingIdentifier=group)
    add('alert',WFAlertActionTitle='Проверьте Journal',WFAlertActionMessage='Действия создания завершились. Проверьте наличие всех 10 записей, даты, текст и заголовки. Успех действия не гарантирует сохранение всех записей. Не запускайте повторно без проверки.',WFAlertActionCancelButtonShown=False)
    workflow['WFWorkflowActions']=actions
    return workflow

if __name__=='__main__':
    p=build()
    (ROOT/'shortcuts/ImportStoicBatch10.plist').write_bytes(plistlib.dumps(p))
    Path('/private/tmp/ImportStoicBatch10-unsigned.shortcut').write_bytes(plistlib.dumps(p,fmt=plistlib.FMT_BINARY))
    print('Generated generic batch workflow; no private diary data embedded.')
