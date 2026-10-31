#!/usr/bin/env python3
"""Open prepared test ZIPs, find payload and media, preview or import."""
import copy
import plistlib
from pathlib import Path
from build_single_entry_shortcut import ROOT,uid,ref,token
from build_batch_shortcut import build as build_batch
from build_single_photo_shortcut import build_photo


def build():
    workflow=build_batch();actions=[]
    def add(name,**p):
        p.setdefault('UUID',uid())
        action={'WFWorkflowActionIdentifier':'is.workflow.actions.'+name,'WFWorkflowActionParameters':p}
        actions.append(action);return p['UUID']
    def condition(subject,code,**extra):
        group=uid();add('conditional',WFControlFlowMode=0,GroupingIdentifier=group,WFCondition=code,
                       WFInput={'Type':'Variable','Variable':subject},**extra);return group
    def end(group):add('conditional',WFControlFlowMode=2,GroupingIdentifier=group)
    def stop(message):
        add('alert',WFAlertActionTitle='Импорт остановлен',WFAlertActionMessage=message,WFAlertActionCancelButtonShown=False)
        add('exit')
    def filter_files(input,prop,value,extension=None):
        filters=[dict(Operator=8,Property=prop,Removable=True,Values={'String':value,'Unit':4})]
        if extension:filters.append(dict(Operator=4,Property='File Extension',Removable=True,Values={'String':extension,'Unit':4}))
        return add('filter.files',WFContentItemInputParameter=input,WFContentItemLimitEnabled=False,
            WFContentItemFilter={'Value':dict(WFActionParameterFilterPrefix=1,WFActionParameterFilterTemplates=filters,WFContentPredicateBoundedDate=False),'WFSerializationType':'WFContentPredicateTableTemplate'})
    def require_one(files,message):
        count=add('count',WFInput=ref(files,'Files'),Input=ref(files,'Files'))
        group=condition(ref(count,'Count'),5,WFNumberValue=1);stop(message);end(group)
    add('comment',WFCommentActionText='Prepared test ZIP only. One archive picker. Native Extract Archive; find one stoic-*.json and matching photo automatically. Preview-only mode performs NO Journal writes. No AI/network/ledger; repeated import can duplicate records. Journal descriptor: jeffd/DayOneToJournal MIT.')
    picked=add('file.select',WFPickingMode='Files',WFSelectMultiple=False)
    extracted=add('unzip',WFArchive=ref(picked,'File'))
    payload=filter_files(ref(extracted,'Files'),'Name','stoic-',extension='json')
    require_one(payload,'В ZIP должен быть ровно один подготовленный stoic-*.json. Исходный ZIP Stoic этой версией не поддерживается. Используйте подготовленный тестовый ZIP.')
    dictionary=add('detect.dictionary',WFInput=ref(payload,'Files'))
    schema=add('getvalueforkey',WFDictionaryKey='schema',WFInput=ref(dictionary))
    schema_text=add('gettext',WFTextActionText=token(schema,'Dictionary Value'))
    def checked_photo(expected):
        # Name may omit an extension on macOS. Check the actual extension with
        # Filter Files, then compare stems using explicit Text values.
        extension=add('text.replace', WFInput=token(expected,'Dictionary Value'),
                      WFReplaceTextFind=r'^.*\.', WFReplaceTextReplace='', WFReplaceTextRegularExpression=True)
        matched=filter_files(ref(extracted,'Files'),'Name','stoic-test-photo',extension=token(extension,'Updated Text'))
        require_one(matched,'Не найдено ровно одно фото с расширением из JSON. Импорт остановлен до создания записи.')
        name=add('getitemname',WFInput=ref(matched,'Files'))
        actual_stem=add('text.replace', WFInput=token(name,'Name'),
                        WFReplaceTextFind=r'\.[^.]+$', WFReplaceTextReplace='', WFReplaceTextRegularExpression=True)
        expected_stem=add('text.replace', WFInput=token(expected,'Dictionary Value'),
                          WFReplaceTextFind=r'\.[^.]+$', WFReplaceTextReplace='', WFReplaceTextRegularExpression=True)
        name_text=add('gettext',WFTextActionText=token(actual_stem,'Updated Text'))
        expected_text=add('gettext',WFTextActionText=token(expected_stem,'Updated Text'))
        group=condition(ref(name_text,'Text'),5,WFConditionalActionString=token(expected_text,'Text'))
        stop('Базовое имя найденного фото не совпадает с JSON. Импорт остановлен.');end(group)
        return matched
    # Preview is the default, explicit no-write option for already imported tests.
    menu=uid()
    add('choosefrommenu',WFControlFlowMode=0,GroupingIdentifier=menu,WFMenuPrompt='Архив распакован. Что сделать?',WFMenuItems=['Только проверить архив','Импортировать записи'])
    add('choosefrommenu',WFControlFlowMode=1,GroupingIdentifier=menu,WFMenuItemTitle='Только проверить архив')
    preview=add('getvalueforkey',WFDictionaryKey='preview',WFInput=ref(dictionary))
    group=condition(ref(preview,'Dictionary Value'),100)
    add('previewdocument',WFInput=ref(preview,'Dictionary Value'))
    add('conditional',WFControlFlowMode=1,GroupingIdentifier=group)
    text=add('getvalueforkey',WFDictionaryKey='text',WFInput=ref(dictionary))
    add('previewdocument',WFInput=ref(text,'Dictionary Value'))
    end(group)
    # If present, preview the matching image in no-write mode too.
    group=condition(ref(schema_text,'Text'),4,WFConditionalActionString='stoic-single-entry-v1')
    expected_photo=add('getvalueforkey',WFDictionaryKey='attachmentFileName',WFInput=ref(dictionary))
    photo=checked_photo(expected_photo)
    add('previewdocument',WFInput=ref(photo,'Files'));end(group)
    add('alert',WFAlertActionTitle='Проверка завершена',WFAlertActionMessage='JSON найден автоматически. Если фото было в архиве, оно показано в предпросмотре. Ни одной записи в Journal не создано.',WFAlertActionCancelButtonShown=False)
    add('exit')
    add('choosefrommenu',WFControlFlowMode=1,GroupingIdentifier=menu,WFMenuItemTitle='Импортировать записи')
    def replace_ref(obj,old,new):
        if isinstance(obj,dict):
            if obj.get('OutputUUID')==old:obj.update(OutputUUID=new,OutputName='Files')
            for v in obj.values():replace_ref(v,old,new)
        elif isinstance(obj,list):
            for v in obj:replace_ref(v,old,new)
    def embedded_photo():
        body=copy.deepcopy(build_photo()['WFWorkflowActions'])
        first=next(a for a in body if a['WFWorkflowActionIdentifier']=='is.workflow.actions.file.select')
        replace_ref(body,first['WFWorkflowActionParameters']['UUID'],payload)
        body.remove(first);body.pop(0)
        picker=next(a for a in body if a['WFWorkflowActionIdentifier']=='is.workflow.actions.file.select')
        picker_id=picker['WFWorkflowActionParameters']['UUID'];position=body.index(picker)
        # Prefix operations use the shared native extraction result.
        original_len=len(actions)
        expected=next(a['WFWorkflowActionParameters']['UUID'] for a in body if a['WFWorkflowActionIdentifier']=='is.workflow.actions.getvalueforkey' and a['WFWorkflowActionParameters'].get('WFDictionaryKey')=='attachmentFileName')
        matched=checked_photo(expected)
        auto=actions[original_len:];del actions[original_len:]
        replace_ref(body,picker_id,matched)
        body[position:position+1]=auto
        for a in body:
            p=a['WFWorkflowActionParameters']
            if p.get('WFAlertActionTitle')=='Next: select this photo file':p['WFAlertActionTitle']='Фото будет найдено автоматически'
        return body
    batch_group=condition(ref(schema_text,'Text'),4,WFConditionalActionString='stoic-test-batch-v1')
    batch=copy.deepcopy(build_batch()['WFWorkflowActions'])
    picker=next(a for a in batch if a['WFWorkflowActionIdentifier']=='is.workflow.actions.file.select')
    replace_ref(batch,picker['WFWorkflowActionParameters']['UUID'],payload)
    batch.remove(picker);batch.pop(0);actions.extend(batch)
    add('conditional',WFControlFlowMode=1,GroupingIdentifier=batch_group)
    photo_group=condition(ref(schema_text,'Text'),4,WFConditionalActionString='stoic-single-entry-v1')
    actions.extend(embedded_photo())
    add('conditional',WFControlFlowMode=1,GroupingIdentifier=photo_group)
    stop('Неизвестный формат подготовленного JSON. Импорт не выполнялся.')
    end(photo_group);end(batch_group)
    add('choosefrommenu',WFControlFlowMode=2,GroupingIdentifier=menu)
    workflow['WFWorkflowActions']=actions;return workflow

if __name__=='__main__':
    p=build();(ROOT/'shortcuts/ImportStoicZIP.plist').write_bytes(plistlib.dumps(p))
    Path('/private/tmp/ImportStoicZIP-unsigned.shortcut').write_bytes(plistlib.dumps(p,fmt=plistlib.FMT_BINARY))
    print('Generated ZIP importer with preview-only mode and automatic photo lookup.')
