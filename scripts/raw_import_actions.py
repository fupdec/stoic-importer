"""Generate a bounded native import branch; the ledger wrapper supplies receipts."""
import copy
import plistlib
from build_single_entry_shortcut import ROOT, uid, ref, token, text_input


def append_import(actions, plan, extracted):
    def add(name, **p):
        if name == 'text.replace' and 'WFInput' in p:
            p['WFInput'] = text_input(p['WFInput'])
        p.setdefault('UUID', uid())
        actions.append(dict(WFWorkflowActionIdentifier='is.workflow.actions.' + name, WFWorkflowActionParameters=p))
        return p['UUID']
    def var(name): return {'Value': {'Type': 'Variable', 'VariableName': name}, 'WFSerializationType': 'WFTextTokenAttachment'}
    def put(name, value): add('setvariable', WFVariableName=name, WFInput=value)
    def get(key, value): return add('getvalueforkey', WFDictionaryKey=text_input(key), WFInput=value)
    def condition(value, code, **p):
        group = uid(); add('conditional', GroupingIdentifier=group, WFControlFlowMode=0,
            WFCondition=code, WFInput={'Type': 'Variable', 'Variable': value}, **p)
        return group
    def end(group): add('conditional', GroupingIdentifier=group, WFControlFlowMode=2)
    def loop(value):
        group = uid(); add('repeat.each', GroupingIdentifier=group, WFControlFlowMode=0, WFInput=value)
        return group
    def end_loop(group): add('repeat.each', GroupingIdentifier=group, WFControlFlowMode=2)
    def stop(message):
        add('alert', WFAlertActionTitle='Импорт остановлен', WFAlertActionMessage=message, WFAlertActionCancelButtonShown=False)
        add('exit')
    def require(value, message):
        missing = condition(value, 101); stop(message); end(missing)
    def empty_list(name): put(name, ref(add('list', WFItems=[]), 'List'))
    def as_text(value, name='Dictionary Value'):
        return add('gettext', WFTextActionText=token(value, name))

    menu = uid()
    add('choosefrommenu', GroupingIdentifier=menu, WFControlFlowMode=0,
        WFMenuPrompt='Следующий шаг: только предпросмотр или партия до 10 записей. '
            'Шкалы без расшифровки и ответы без связи исключены из импорта. Старые импорты без реестра автоматически не обнаруживаются.',
        WFMenuItems=['Только предпросмотр', 'Импортировать записи'])
    add('choosefrommenu', GroupingIdentifier=menu, WFControlFlowMode=1, WFMenuItemTitle='Только предпросмотр')
    add('exit')
    # build_ledger inserts folder selection/registry loading at this exact branch.
    add('choosefrommenu', GroupingIdentifier=menu, WFControlFlowMode=1, WFMenuItemTitle='Импортировать записи')
    empty_list('ImportCandidates'); empty_list('ReviewRecords')
    empty = add('dictionary', WFItems={'Value': {'WFDictionaryFieldValueItems': []}, 'WFSerializationType': 'WFDictionaryFieldValue'})
    put('ImportSeenIDs', ref(empty))
    scan = loop(plan)
    put('ScannedEntry', var('Repeat Item'))
    identifier = get('sourceID', var('ScannedEntry'))
    identifier_text = as_text(identifier)
    require(ref(identifier_text, 'Text'), 'В плане нет исходного UUID. Ни одной записи не создано.')
    reserved = condition(ref(identifier_text, 'Text'), 4, WFConditionalActionString='__schema__')
    stop('Недопустимый исходный UUID.'); end(reserved)
    duplicate = get(token(identifier_text, 'Text'), var('ImportSeenIDs'))
    repeated = condition(ref(duplicate, 'Dictionary Value'), 100)
    stop('В плане повторяется исходный UUID. Ни одной записи не создано.'); end(repeated)
    changed = add('setvalueforkey', WFDictionary=var('ImportSeenIDs'),
        WFDictionaryKey=token(identifier_text, 'Text'), WFDictionaryValue='seen')
    put('ImportSeenIDs', ref(changed))
    review = get('reviewStatus', var('ScannedEntry'))
    review_text = as_text(review)
    ready = condition(ref(review_text, 'Text'), 4, WFConditionalActionString='ready')
    for field in ['date', 'text']:
        value = get(field, var('ScannedEntry'))
        require(ref(value, 'Dictionary Value'), 'В готовой записи отсутствуют дата или текст. Ни одной записи не создано.')
    status = get(token(identifier_text, 'Text'), var('StoicLedger'))
    fresh = condition(ref(status, 'Dictionary Value'), 101)
    count = add('count', WFInput=var('ImportCandidates'), Input=var('ImportCandidates'))
    slot = condition(ref(count, 'Count'), 0, WFNumberValue=10)
    add('appendvariable', WFVariableName='ImportCandidates', WFInput=var('ScannedEntry')); end(slot)
    add('conditional', GroupingIdentifier=fresh, WFControlFlowMode=1)
    status_text = as_text(status)
    unknown = condition(ref(status_text, 'Text'), 5, WFConditionalActionString='action-returned')
    unconfirmed = condition(ref(status_text, 'Text'), 5, WFConditionalActionString='manual-confirmed')
    stop('В реестре есть pending или неизвестный статус. Проверьте Journal перед продолжением. Ни одной новой записи не создано.')
    end(unconfirmed); end(unknown); end(fresh)
    add('conditional', GroupingIdentifier=ready, WFControlFlowMode=1)
    add('appendvariable', WFVariableName='ReviewRecords', WFInput=var('ScannedEntry'))
    end(ready); end_loop(scan)
    count = add('count', WFInput=var('ImportCandidates'), Input=var('ImportCandidates'))
    none = condition(ref(count, 'Count'), 4, WFNumberValue=0)
    stop('Новых записей без отметки «нужна проверка» нет. Подтверждённые UUID пропущены. Непроверенные записи не импортированы.'); end(none)
    add('previewdocument', WFInput=var('ImportCandidates'))
    excluded = add('count', WFInput=var('ReviewRecords'), Input=var('ReviewRecords'))
    confirmation = ('В партии: \ufffc.\nТребуют проверки и исключены: \ufffc.\n'
        'Будут обработаны только показанные записи, не более 10. '
        'Реестр не обнаруживает старые импорты без квитанций. После действия Journal проверьте фактическое сохранение. '
        'Держите устройство разблокированным и не запускайте второй импорт с этим реестром.')
    attachments = {}; offset = 0
    for output in [count, excluded]:
        position = confirmation.index('\ufffc', offset)
        attachments[f'{{{position}, 1}}'] = {'Type': 'ActionOutput', 'OutputUUID': output, 'OutputName': 'Count'}
        offset = position + 1
    add('alert', WFAlertActionTitle='Создать показанную партию в Journal?',
        WFAlertActionMessage={'Value': {'string': confirmation, 'attachmentsByRange': attachments},
                              'WFSerializationType': 'WFTextTokenString'}, WFAlertActionCancelButtonShown=True)
    descriptor = plistlib.loads((ROOT / 'shortcuts/HistoricalDateProbe.plist').read_bytes())['WFWorkflowActions'][0]
    writing = loop(var('ImportCandidates'))
    put('ImportRecord', var('Repeat Item'))
    empty_list('ImportMedia')
    paths = get('attachmentPaths', var('ImportRecord'))
    has_paths = condition(ref(paths, 'Dictionary Value'), 100)
    photos = loop(ref(paths, 'Dictionary Value'))
    path_text = add('gettext', WFTextActionText={'Value': {'string': '\ufffc', 'attachmentsByRange': {
        '{0, 1}': {'Type': 'Variable', 'VariableName': 'Repeat Item'}}}, 'WFSerializationType': 'WFTextTokenString'})
    filename = add('text.replace', WFInput=ref(path_text, 'Text'), WFReplaceTextFind=r'^.*/', WFReplaceTextReplace='', WFReplaceTextRegularExpression=True)
    extension = add('text.replace', WFInput=ref(filename, 'Updated Text'), WFReplaceTextFind=r'^.*\.', WFReplaceTextReplace='', WFReplaceTextRegularExpression=True)
    stem = add('text.replace', WFInput=ref(filename, 'Updated Text'), WFReplaceTextFind=r'\.[^.]+$', WFReplaceTextReplace='', WFReplaceTextRegularExpression=True)
    matched = add('filter.files', WFContentItemInputParameter=ref(extracted, 'Files'), WFContentItemLimitEnabled=False,
        WFContentItemFilter={'Value': {'WFActionParameterFilterPrefix': 1, 'WFActionParameterFilterTemplates': [
            {'Operator': 8, 'Property': 'Name', 'Removable': True, 'Values': {'String': token(stem, 'Updated Text'), 'Unit': 4}},
            {'Operator': 4, 'Property': 'File Extension', 'Removable': True, 'Values': {'String': token(extension, 'Updated Text'), 'Unit': 4}}],
            'WFContentPredicateBoundedDate': False}, 'WFSerializationType': 'WFContentPredicateTableTemplate'})
    media_count = add('count', WFInput=ref(matched, 'Files'), Input=ref(matched, 'Files'))
    bad = condition(ref(media_count, 'Count'), 5, WFNumberValue=1)
    stop('Фотография стала недоступна или имя неоднозначно. Текущая запись ещё не создана.'); end(bad)
    add('appendvariable', WFVariableName='ImportMedia', WFInput=ref(matched, 'Files'))
    end_loop(photos); end(has_paths)
    values = {field: get(field, var('ImportRecord')) for field in ['title', 'text', 'date']}
    title = as_text(values['title'])
    titled = condition(ref(title, 'Text'), 100)
    def create(with_title):
        action = copy.deepcopy(descriptor); p = action['WFWorkflowActionParameters']
        p.update(UUID=uid(), message=token(values['text'], 'Dictionary Value'),
                 entryDate=token(values['date'], 'Dictionary Value'), mediaItems=var('ImportMedia'))
        if with_title: p['title'] = token(title, 'Text')
        else: p.pop('title', None)
        actions.append(action)
    create(True)
    add('conditional', GroupingIdentifier=titled, WFControlFlowMode=1)
    create(False); end(titled)
    add('delay', WFDelayTime=2.0)
    end_loop(writing)
    add('alert', WFAlertActionTitle='Партия обработана — проверьте Journal',
        WFAlertActionMessage='Проверьте записи, даты и фотографии. action-returned означает только возврат действия Journal. '
            'Повторный запуск с тем же реестром пропустит обработанные UUID и предложит следующую партию. '
            'Записи с отметкой проверки остаются исключёнными.', WFAlertActionCancelButtonShown=False)
    add('choosefrommenu', GroupingIdentifier=menu, WFControlFlowMode=2)
