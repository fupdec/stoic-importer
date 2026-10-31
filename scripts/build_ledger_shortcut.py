#!/usr/bin/env python3
"""Add durable source-UUID receipts to the prepared ZIP workflow."""
import copy
import plistlib
from pathlib import Path
from build_single_entry_shortcut import ROOT,uid,ref,token
from build_zip_shortcut import build as build_zip

LEDGER_NAME='stoic-import-ledger.json'
LEDGER_SCHEMA='stoic-import-ledger-v1'


def build_ledger(workflow=None, include_search=True, verification_only=False):
    if verification_only and not include_search:
        raise ValueError('Verification requires manual review with Journal search')
    workflow=copy.deepcopy(workflow if workflow is not None else build_zip())
    original=workflow['WFWorkflowActions'];by_id={a['WFWorkflowActionParameters'].get('UUID'):a for a in original}
    def variable(name):return {'Value':{'Type':'Variable','VariableName':name},'WFSerializationType':'WFTextTokenAttachment'}
    actions=[]
    def add(name,**p):
        p.setdefault('UUID',uid());actions.append(dict(WFWorkflowActionIdentifier='is.workflow.actions.'+name,WFWorkflowActionParameters=p));return p['UUID']
    def set_variable(name,value):add('setvariable',WFVariableName=name,WFInput=value)
    def condition(value,code,**p):
        group=uid();add('conditional',GroupingIdentifier=group,WFControlFlowMode=0,WFCondition=code,WFInput={'Type':'Variable','Variable':value},**p);return group
    def end(group):add('conditional',GroupingIdentifier=group,WFControlFlowMode=2)
    def stop(message):
        add('alert',WFAlertActionTitle='Нужна проверка реестра',WFAlertActionMessage=message,WFAlertActionCancelButtonShown=False);add('exit')
    def set_text(name,text):
        value=add('gettext',WFTextActionText=text);set_variable(name,ref(value,'Text'))
    def save():
        # Explicit dictionary serialization mirrors the upstream file-writing route.
        add('documentpicker.save',WFInput=variable('StoicLedger'),WFFolder=variable('StoicLedgerFolder'),
            WFAskWhereToSave=False,WFFileDestinationPath=LEDGER_NAME,WFSaveFileOverwrite=True)
    def update(key,status):
        changed=add('setvalueforkey',WFDictionary=variable('StoicLedger'),WFDictionaryKey=token(key,'Text'),WFDictionaryValue=status)
        set_variable('StoicLedger',ref(changed));save()
    def setup():
        add('alert',WFAlertActionTitle='Папка реестра импорта',WFAlertActionMessage='Выберите постоянную папку. В ней хранится stoic-import-ledger.json с UUID и статусами. При следующих запусках выбирайте ту же папку. Старые импорты без реестра автоматически не обнаруживаются. Запускайте только одну копию команды одновременно.',WFAlertActionCancelButtonShown=True)
        folder=add('file.select',WFPickingMode='Folders');set_variable('StoicLedgerFolder',ref(folder,'Folder'))
        loaded=add('documentpicker.open',WFFile=variable('StoicLedgerFolder'),WFGetFilePath=LEDGER_NAME,WFFileErrorIfNotFound=False)
        present=condition(ref(loaded,'File'),100)
        parsed=add('detect.dictionary',WFInput=ref(loaded,'File'));set_variable('StoicLedger',ref(parsed))
        schema=add('getvalueforkey',WFDictionaryKey='__schema__',WFInput=variable('StoicLedger'))
        text=add('gettext',WFTextActionText=token(schema,'Dictionary Value'))
        invalid=condition(ref(text,'Text'),5,WFConditionalActionString=LEDGER_SCHEMA)
        stop('Существующий файл реестра имеет неизвестный формат. Он не перезаписан, импорт не выполнялся.');end(invalid)
        add('conditional',GroupingIdentifier=present,WFControlFlowMode=1)
        empty=add('dictionary',WFItems={'Value':{'WFDictionaryFieldValueItems':[]},'WFSerializationType':'WFDictionaryFieldValue'})
        marked=add('setvalueforkey',WFDictionary=ref(empty),WFDictionaryKey='__schema__',WFDictionaryValue=LEDGER_SCHEMA)
        set_variable('StoicLedger',ref(marked));end(present)
        # Prove the destination is writable before requesting any Journal write.
        save()
        if include_search:
            mode=uid()
            add('choosefrommenu',GroupingIdentifier=mode,WFControlFlowMode=0,WFMenuPrompt='Как проверять существующие записи?',WFMenuItems=['Также открыть поиск Journal перед новой записью','Только UUID-реестр'])
            add('choosefrommenu',GroupingIdentifier=mode,WFControlFlowMode=1,WFMenuItemTitle='Только UUID-реестр')
            set_text('StoicSearchFirst','no')
            add('choosefrommenu',GroupingIdentifier=mode,WFControlFlowMode=1,WFMenuItemTitle='Также открыть поиск Journal перед новой записью')
            set_text('StoicSearchFirst','yes')
            add('choosefrommenu',GroupingIdentifier=mode,WFControlFlowMode=2)
        else:
            set_text('StoicSearchFirst','no')
    def create_with_receipt(key,action):
        if verification_only:
            stop('Проверочная команда не создаёт записи. UUID не отмечен как импортированный. Для новой записи используйте импортёр после проверки реестра.')
            return
        update(key,'pending');actions.append(action);update(key,'action-returned')
    is_zip=any(a['WFWorkflowActionIdentifier']=='is.workflow.actions.unzip' for a in original)
    if not is_zip:setup()
    for a in original:
        p=a['WFWorkflowActionParameters'];ident=a['WFWorkflowActionIdentifier']
        if ident=='is.workflow.actions.choosefrommenu' and p.get('WFMenuItemTitle')=='Импортировать записи':
            actions.append(a);setup();continue
        if ident!='com.apple.journal.CreateEntryIntent':
            actions.append(a);continue
        # Trace the message getter's input to the SAME source record used by Journal.
        message=p['message']['Value']['attachmentsByRange']['{0, 1}']['OutputUUID']
        record=by_id[message]['WFWorkflowActionParameters']['WFInput']
        source=add('getvalueforkey',WFDictionaryKey='sourceID',WFInput=record)
        key=add('gettext',WFTextActionText=token(source,'Dictionary Value'))
        missing=condition(ref(key,'Text'),101);stop('Отсутствует UUID исходной записи. Импорт остановлен.');end(missing)
        reserved=condition(ref(key,'Text'),4,WFConditionalActionString='__schema__');stop('Недопустимый ID записи. Реестр не изменён.');end(reserved)
        status=add('getvalueforkey',WFDictionaryKey=token(key,'Text'),WFInput=variable('StoicLedger'))
        fresh=condition(ref(status,'Dictionary Value'),101)
        set_text('StoicShouldCreate','create')
        if include_search:
            manual=condition(variable('StoicSearchFirst'),4,WFConditionalActionString='yes')
            # SearchEntriesIntent only shows results; a HUMAN decides whether an entry exists.
            query=p.get('title')
            if query is None:
                lines=add('text.split',text=copy.deepcopy(p['message']),WFTextSeparator='New Lines')
                first=add('getitemfromlist',WFInput=ref(lines,'Split Text'),WFItemSpecifier='First Item')
                query=token(first,'Item from List')
            actions.append(dict(WFWorkflowActionIdentifier='com.apple.journal.SearchEntriesIntent',WFWorkflowActionParameters={
                'UUID':uid(),'AppIntentDescriptor':{'AppIntentIdentifier':'SearchEntriesIntent','BundleIdentifier':'com.apple.journal','Name':'Journal','TeamIdentifier':'0000000000'},'criteria':copy.deepcopy(query)}))
            review=uid()
            absent='Совпадений нет — остановить' if verification_only else 'Совпадений нет — создать'
            add('choosefrommenu',GroupingIdentifier=review,WFControlFlowMode=0,WFMenuPrompt='Проверьте результаты поиска Journal: совпадают дата и текст? Поиск не сообщает результат команде автоматически.',WFMenuItems=['Остановить и проверить','Запись уже есть — пропустить',absent])
            add('choosefrommenu',GroupingIdentifier=review,WFControlFlowMode=1,WFMenuItemTitle='Остановить и проверить');add('exit')
            add('choosefrommenu',GroupingIdentifier=review,WFControlFlowMode=1,WFMenuItemTitle='Запись уже есть — пропустить')
            update(key,'manual-confirmed');set_text('StoicShouldCreate','skip')
            add('choosefrommenu',GroupingIdentifier=review,WFControlFlowMode=1,WFMenuItemTitle=absent);add('nothing')
            add('choosefrommenu',GroupingIdentifier=review,WFControlFlowMode=2);end(manual)
        should_create=condition(variable('StoicShouldCreate'),4,WFConditionalActionString='create')
        create_with_receipt(key,a);end(should_create)
        add('conditional',GroupingIdentifier=fresh,WFControlFlowMode=1)
        status_text=add('gettext',WFTextActionText=token(status,'Dictionary Value'))
        uncertain=condition(ref(status_text,'Text'),5,WFConditionalActionString='action-returned')
        unconfirmed=condition(ref(status_text,'Text'),5,WFConditionalActionString='manual-confirmed')
        add('alert',WFAlertActionTitle='UUID требует проверки',WFAlertActionMessage=token(key,'Text'),WFAlertActionCancelButtonShown=False)
        stop('UUID есть в реестре с незавершённым или неизвестным статусом. Проверьте Journal и реестр перед повтором. Автоматический повтор отключён, чтобы не создать дубликат.');end(unconfirmed);end(uncertain)
        # An action-returned receipt means skip; do not touch existing Journal entries.
        end(fresh)
    for item in actions:
        params=item['WFWorkflowActionParameters']
        if item['WFWorkflowActionIdentifier']=='is.workflow.actions.comment':
            params['WFCommentActionText']='Prepared ZIP importer with source UUID ledger. Choose one persistent registry folder. Preview-only does not access the ledger. No AI or network. Pending receipts stop for manual review; action-returned receipts skip. Descriptor: jeffd/DayOneToJournal MIT.'
        if params.get('WFAlertActionTitle')=='Создать 10 записей?':
            params['WFAlertActionTitle']='Проверить 10 записей без создания?' if verification_only else 'Обработать 10 записей с проверкой реестра?'
            params['WFAlertActionMessage']=('Создание записей отключено. После ручной проверки существующей записи её UUID можно отметить в реестре. Неподтверждённые записи останавливают проверку.' if verification_only else 'UUID со статусом action-returned будут пропущены. Новые записи будут добавлены. Записи pending требуют проверки. Держите устройство разблокированным. Импорты старых версий без реестра не обнаруживаются.')
    workflow['WFWorkflowActions']=actions
    if verification_only:
        for item in actions:
            params=item['WFWorkflowActionParameters']
            if item['WFWorkflowActionIdentifier']=='is.workflow.actions.comment':
                params['WFCommentActionText']='REGISTRY VERIFICATION ONLY. No Journal CreateEntryIntent actions. Manually confirm an existing entry after search, then repeat with the same registry to verify skipping. No AI or network.'
    return workflow

if __name__=='__main__':
    p=build_ledger();(ROOT/'shortcuts/ImportStoicZIPLedger.plist').write_bytes(plistlib.dumps(p))
    Path('/private/tmp/ImportStoicZIPLedger-unsigned.shortcut').write_bytes(plistlib.dumps(p,fmt=plistlib.FMT_BINARY))
    probe=build_ledger(verification_only=True)
    (ROOT/'shortcuts/VerifyStoicZIPLedger.plist').write_bytes(plistlib.dumps(probe))
    Path('/private/tmp/VerifyStoicZIPLedger-unsigned.shortcut').write_bytes(plistlib.dumps(probe,fmt=plistlib.FMT_BINARY))
    print('Generated ZIP importer with persistent source-UUID receipts and pending-write guard.')
