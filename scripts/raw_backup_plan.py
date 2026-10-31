"""Generate native actions linking Stoic records. Never executes on the user's device."""
from build_single_entry_shortcut import uid, ref, token, text_input


def append_plan(actions, collections, extracted):
    def add(name, **p):
        if name in ('text.match', 'text.split') and 'text' in p:
            p['text'] = text_input(p['text'])
        if name == 'text.replace' and 'WFInput' in p:
            p['WFInput'] = text_input(p['WFInput'])
        p.setdefault('UUID', uid())
        actions.append(dict(WFWorkflowActionIdentifier='is.workflow.actions.' + name, WFWorkflowActionParameters=p))
        return p['UUID']

    def var(name):
        return {'Value': {'Type': 'Variable', 'VariableName': name}, 'WFSerializationType': 'WFTextTokenAttachment'}

    def put(name, value): add('setvariable', WFVariableName=name, WFInput=value)
    def get(key, value): return add('getvalueforkey', WFDictionaryKey=text_input(key), WFInput=value)
    def text(value): return add('gettext', WFTextActionText=value)
    def empty_dict(name):
        value = add('dictionary', WFItems={'Value': {'WFDictionaryFieldValueItems': []}, 'WFSerializationType': 'WFDictionaryFieldValue'})
        put(name, ref(value))
    def empty_list(name): put(name, ref(add('list', WFItems=[]), 'List'))
    def update(name, key, value):
        result = add('setvalueforkey', WFDictionary=var(name), WFDictionaryKey=text_input(key),
                     WFDictionaryValue=text_input(value))
        put(name, ref(result))
    def condition(subject, code, **p):
        group = uid()
        add('conditional', GroupingIdentifier=group, WFControlFlowMode=0, WFCondition=code,
            WFInput={'Type': 'Variable', 'Variable': subject}, **p)
        return group
    def end(group): add('conditional', GroupingIdentifier=group, WFControlFlowMode=2)
    def loop(value):
        group = uid(); add('repeat.each', GroupingIdentifier=group, WFControlFlowMode=0, WFInput=value)
        return group
    def end_loop(group): add('repeat.each', GroupingIdentifier=group, WFControlFlowMode=2)
    def stop(message):
        add('alert', WFAlertActionTitle='Нужна проверка архива', WFAlertActionMessage=message, WFAlertActionCancelButtonShown=False)
        add('exit')
    def require(value, message):
        group = condition(value, 101); stop(message); end(group)
    def equal(left, right, message):
        group = condition(left, 5, WFConditionalActionString=right); stop(message); end(group)
    def append(name, value): add('appendvariable', WFVariableName=name, WFInput=value)
    def replace(value, pattern, replacement=''):
        return add('text.replace', WFInput=value, WFReplaceTextFind=pattern,
                   WFReplaceTextReplace=replacement, WFReplaceTextRegularExpression=True)
    def match(value, pattern):
        return add('text.match', text=value, WFMatchTextPattern=pattern)
    def formatted(template, *outputs):
        attachments = {}; position = 0
        for output in outputs:
            position = template.index('\ufffc', position)
            attachments[f'{{{position}, 1}}'] = {'Type': 'ActionOutput', 'OutputUUID': output, 'OutputName': 'Text'}
            position += 1
        return text({'Value': {'string': template, 'attachmentsByRange': attachments}, 'WFSerializationType': 'WFTextTokenString'})
    def checked_stamp(value):
        rendered = text(value)
        valid = match(ref(rendered, 'Text'), r'^[0-9]+(?:\.[0-9]+)?$')
        require(ref(valid, 'Matches'), 'Нужна неотрицательная числовая метка времени в миллисекундах. Дата не будет угадана.')
    def key_of(record):
        value = get('uuid', record)
        result = text(token(value, 'Dictionary Value'))
        require(ref(result, 'Text'), 'У объекта отсутствует исходный UUID.')
        return result

    # Explicit dictionaries avoid repeated searches for referenced answer/asset IDs.
    empty_dict('AnswersByRoutine')
    for collection, name in [('answers', 'AnswersByID'), ('assets', 'AssetsByID')]:
        empty_dict(name)
        group = loop(ref(collections[collection], 'Dictionary Value'))
        put('IndexedRecord', var('Repeat Item'))
        key = key_of(var('IndexedRecord'))
        previous = get(token(key, 'Text'), var(name))
        duplicate = condition(ref(previous, 'Dictionary Value'), 100)
        stop('Повторяющийся UUID ответа или вложения. Сборка остановлена.'); end(duplicate)
        update(name, token(key, 'Text'), var('IndexedRecord'))
        if collection == 'answers':
            routine = get('routine', var('IndexedRecord'))
            routine_text = text(token(routine, 'Dictionary Value'))
            grouped = condition(ref(routine_text, 'Text'), 100)
            bucket = get(token(routine_text, 'Text'), var('AnswersByRoutine'))
            existing = condition(ref(bucket, 'Dictionary Value'), 100)
            put('RoutineBucket', ref(bucket, 'Dictionary Value'))
            add('conditional', GroupingIdentifier=existing, WFControlFlowMode=1)
            empty_list('RoutineBucket'); end(existing)
            append('RoutineBucket', var('IndexedRecord'))
            update('AnswersByRoutine', token(routine_text, 'Text'), var('RoutineBucket'))
            end(grouped)
        end_loop(group)

    empty_dict('SeenSources'); empty_dict('UsedAnswers'); empty_list('StoicPlan')

    def begin_source(kind):
        put('SourceRecord', var('Repeat Item'))
        source_key = key_of(var('SourceRecord'))
        put('SourceKey', ref(source_key, 'Text'))
        previous = get(var('SourceKey'), var('SeenSources'))
        duplicate = condition(ref(previous, 'Dictionary Value'), 100)
        stop('Одинаковый UUID у нескольких исходных записей. Сборка остановлена.'); end(duplicate)
        update('SeenSources', var('SourceKey'), kind)
        empty_list('SourceAnswers'); empty_list('SourcePhotos'); empty_list('SourcePaths'); empty_list('SourceBlocks')
        empty_dict('OrderedInSource')
        put('SourceStamp', ref(text(''), 'Text'))
        empty_dict('PlannedEntry')
        update('PlannedEntry', 'sourceID', var('SourceKey'))
        update('PlannedEntry', 'sourceKind', kind)
        update('PlannedEntry', 'needsReview', kind == 'orphan-answer')
        update('PlannedEntry', 'reviewStatus', 'required' if kind == 'orphan-answer' else 'ready')
        update('PlannedEntry', 'source', var('SourceRecord'))

    def attach_answer(record):
        put('LinkedAnswer', record)
        answer_key = key_of(var('LinkedAnswer'))
        previous = get(token(answer_key, 'Text'), var('UsedAnswers'))
        duplicate = condition(ref(previous, 'Dictionary Value'), 100)
        stop('Один ответ связан с несколькими записями. Автоматическое дублирование отключено.'); end(duplicate)
        update('UsedAnswers', token(answer_key, 'Text'), var('SourceKey'))
        update('OrderedInSource', token(answer_key, 'Text'), 'included')
        append('SourceAnswers', var('LinkedAnswer'))
        stamp = get('timestamp', var('LinkedAnswer'))
        checked_stamp(token(stamp, 'Dictionary Value'))
        first_stamp = condition(var('SourceStamp'), 101)
        put('SourceStamp', ref(stamp, 'Dictionary Value'))
        add('conditional', GroupingIdentifier=first_stamp, WFControlFlowMode=1)
        earlier = condition(var('SourceStamp'), 2, WFNumberValue=ref(stamp, 'Dictionary Value'))
        put('SourceStamp', ref(stamp, 'Dictionary Value')); end(earlier); end(first_stamp)
        body = get('text', var('LinkedAnswer'))
        has_text = condition(ref(body, 'Dictionary Value'), 100)
        question = get('question', var('LinkedAnswer'))
        question_text = text(token(question, 'Dictionary Value'))
        heading = replace(ref(question_text, 'Text'),
                          r'(?i)^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$')
        has_heading = condition(ref(heading, 'Updated Text'), 100)
        body_text = text(token(body, 'Dictionary Value'))
        heading_text = text(token(heading, 'Updated Text'))
        block = formatted('\ufffc\n\n\ufffc', heading_text, body_text)
        append('SourceBlocks', ref(block, 'Text'))
        add('conditional', GroupingIdentifier=has_heading, WFControlFlowMode=1)
        # Preserve structured values literally; definitions are not inferred from UUIDs.
        append('SourceBlocks', ref(body, 'Dictionary Value')); end(has_heading)
        unresolved_heading = condition(ref(heading, 'Updated Text'), 101)
        body_value_text = text(token(body, 'Dictionary Value'))
        structured = match(ref(body_value_text, 'Text'), r'(?i)^\s*(?:[\[{]|-?[0-9]+(?:\.[0-9]+)?\s*$|true\s*$|false\s*$|null\s*$)')
        unresolved = condition(ref(structured, 'Matches'), 100)
        update('PlannedEntry', 'needsReview', True)
        update('PlannedEntry', 'reviewStatus', 'required'); end(unresolved); end(unresolved_heading); end(has_text)
        assets = get('assets', var('LinkedAnswer'))
        has_assets = condition(ref(assets, 'Dictionary Value'), 100)
        media_loop = loop(ref(assets, 'Dictionary Value'))
        asset = get(var('Repeat Item'), var('AssetsByID'))
        require(ref(asset, 'Dictionary Value'), 'Ответ ссылается на отсутствующее вложение.')
        owner = get('answer', ref(asset))
        owner_text = text(token(owner, 'Dictionary Value'))
        equal(ref(owner_text, 'Text'), token(answer_key, 'Text'), 'Вложение принадлежит другому ответу.')
        media_type = get('type', ref(asset))
        type_text = text(token(media_type, 'Dictionary Value'))
        equal(ref(type_text, 'Text'), 'image', 'Обнаружено вложение не типа image. Оно не будет молча пропущено.')
        path = get('relativePath', ref(asset))
        path_text = text(token(path, 'Dictionary Value'))
        require(ref(path_text, 'Text'), 'У вложения отсутствует путь.')
        unsafe = add('text.match', text=ref(path_text, 'Text'), WFMatchTextPattern=r'(^/|\\|(^|/)\.\.(/|$))')
        bad_path = condition(ref(unsafe, 'Matches'), 100)
        stop('Небезопасный путь вложения. Сборка остановлена.'); end(bad_path)
        filename = add('text.replace', WFInput=ref(path_text, 'Text'), WFReplaceTextFind=r'^.*/',
                       WFReplaceTextReplace='', WFReplaceTextRegularExpression=True)
        extension = add('text.replace', WFInput=ref(filename, 'Updated Text'), WFReplaceTextFind=r'^.*\.',
                        WFReplaceTextReplace='', WFReplaceTextRegularExpression=True)
        stem = add('text.replace', WFInput=ref(filename, 'Updated Text'), WFReplaceTextFind=r'\.[^.]+$',
                   WFReplaceTextReplace='', WFReplaceTextRegularExpression=True)
        found = add('filter.files', WFContentItemInputParameter=ref(extracted, 'Files'), WFContentItemLimitEnabled=False,
            WFContentItemFilter={'Value': {'WFActionParameterFilterPrefix': 1,
                'WFActionParameterFilterTemplates': [
                    {'Operator': 8, 'Property': 'Name', 'Removable': True, 'Values': {'String': token(stem, 'Updated Text'), 'Unit': 4}},
                    {'Operator': 4, 'Property': 'File Extension', 'Removable': True, 'Values': {'String': token(extension, 'Updated Text'), 'Unit': 4}}],
                'WFContentPredicateBoundedDate': False}, 'WFSerializationType': 'WFContentPredicateTableTemplate'})
        count = add('count', WFInput=ref(found, 'Files'), Input=ref(found, 'Files'))
        count_text = text(token(count, 'Count'))
        equal(ref(count_text, 'Text'), '1', 'Файл фотографии отсутствует или имя неоднозначно.')
        actual_name = add('getitemname', WFInput=ref(found, 'Files'))
        actual_stem = add('text.replace', WFInput=token(actual_name, 'Name'), WFReplaceTextFind=r'\.[^.]+$',
                          WFReplaceTextReplace='', WFReplaceTextRegularExpression=True)
        equal(ref(actual_stem, 'Updated Text'), token(stem, 'Updated Text'), 'Имя фотографии не совпадает с описанием вложения.')
        append('SourcePhotos', ref(found, 'Files')); append('SourcePaths', ref(path_text, 'Text'))
        end_loop(media_loop); end(has_assets)

    def finish_source(kind):
        combined = add('text.combine', WFTextSeparator='Custom', WFTextCustomSeparator='\n\n', text=var('SourceBlocks'))
        update('PlannedEntry', 'sourceText', ref(combined, 'Combined Text'))
        update('PlannedEntry', 'text', ref(combined, 'Combined Text'))
        prose = match(ref(combined, 'Combined Text'), r'\S')
        empty_body = condition(ref(prose, 'Matches'), 101)
        update('PlannedEntry', 'needsReview', True)
        update('PlannedEntry', 'reviewStatus', 'required'); end(empty_body)
        update('PlannedEntry', 'title', '')
        # Promote only an eligible first line and only when a nonempty body remains.
        normalized = replace(ref(combined, 'Combined Text'), r'\A(?:[ \t]*(?:\r\n|\r|\n))*')
        first_line = replace(ref(normalized, 'Updated Text'), r'[\r\n][\s\S]*\Z')
        clean = replace(ref(first_line, 'Updated Text'), r'^\s*(?:#{1,6}\s+|[-*+]\s+|\d+[.)]\s+)', '')
        collapsed = replace(ref(clean, 'Updated Text'), r'\s+', ' ')
        candidate = replace(ref(collapsed, 'Updated Text'), r'^\s+|\s+$')
        eligible = match(ref(candidate, 'Updated Text'), r'^.{1,79}$')
        body = replace(ref(normalized, 'Updated Text'), r'\A[^\r\n]*(?:\r\n|\r|\n)(?:[ \t]*(?:\r\n|\r|\n))*')
        remaining = match(ref(body, 'Updated Text'), r'\S')
        # One-line entries must never become an empty body, even though replace
        # leaves an unmatched one-line string unchanged.
        newline = match(ref(normalized, 'Updated Text'), r'[\r\n]')
        has_title = condition(ref(eligible, 'Matches'), 100)
        has_newline = condition(ref(newline, 'Matches'), 100)
        has_body = condition(ref(remaining, 'Matches'), 100)
        structured = match(ref(candidate, 'Updated Text'), r'(?i)^(?:[\[{]|-?[0-9]+(?:\.[0-9]+)?$|true$|false$|null$|[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$)')
        plain = condition(ref(structured, 'Matches'), 101)
        update('PlannedEntry', 'title', ref(candidate, 'Updated Text'))
        update('PlannedEntry', 'text', ref(body, 'Updated Text'))
        end(plain); end(has_body); end(has_newline); end(has_title)
        if kind != 'routine':
            stamp = get('timestamp', var('SourceRecord'))
            checked_stamp(token(stamp, 'Dictionary Value'))
            put('SourceStamp', ref(stamp, 'Dictionary Value'))
        update('PlannedEntry', 'sourceTimestampMilliseconds', var('SourceStamp'))
        seconds = add('math', WFInput=var('SourceStamp'), WFMathOperation='/', WFMathOperand=1000)
        seconds_text = text(token(seconds, 'Calculation Result'))
        whole_seconds = replace(ref(seconds_text, 'Text'), r'\..*$', '')
        stamp_text = text({'Value': {'string': '\ufffc', 'attachmentsByRange': {
            '{0, 1}': {'Type': 'Variable', 'VariableName': 'SourceStamp'}}},
            'WFSerializationType': 'WFTextTokenString'})
        milliseconds = replace(ref(stamp_text, 'Text'), r'^.*?([0-9]{1,3})(?:\.[0-9]+)?$', '$1')
        milliseconds_text = text(token(milliseconds, 'Updated Text'))
        padded = formatted('000\ufffc', milliseconds_text)
        milliseconds_padded = replace(ref(padded, 'Text'), r'^.*([0-9]{3})$', '$1')
        epoch = text('1970-01-01T00:00:00Z')
        date = add('adjustdate', WFDate=ref(epoch, 'Text'),
                   WFDuration={'Value': {'Unit': 'sec', 'Magnitude': token(whole_seconds, 'Updated Text')},
                               'WFSerializationType': 'WFQuantityFieldValue'})
        prefix = add('format.date', WFDate=ref(date, 'Adjusted Date'), WFLocale='en_US_POSIX',
                     WFDateFormatStyle='Custom', WFDateFormat="yyyy-MM-dd'T'HH:mm:ss")
        zone = add('format.date', WFDate=ref(date, 'Adjusted Date'), WFLocale='en_US_POSIX',
                   WFDateFormatStyle='Custom', WFDateFormat='XXX')
        prefix_text = text(token(prefix, 'Formatted Date'))
        zone_text = text(token(zone, 'Formatted Date'))
        fraction_text = text(token(milliseconds_padded, 'Updated Text'))
        iso_date = formatted('\ufffc.\ufffc\ufffc', prefix_text, fraction_text, zone_text)
        update('PlannedEntry', 'date', ref(iso_date, 'Text'))
        update('PlannedEntry', 'datePolicy', 'earliest-answer-timestamp' if kind == 'routine' else 'source-timestamp')
        update('PlannedEntry', 'answers', var('SourceAnswers'))
        update('PlannedEntry', 'attachmentPaths', var('SourcePaths'))
        # Keep file objects out of the textual plan. A later writer must resolve paths again.
        append('StoicPlan', var('PlannedEntry'))

    group = loop(ref(collections['journal-entries'], 'Dictionary Value'))
    begin_source('journal-entry')
    own_text = get('text', var('SourceRecord'))
    has_own_text = condition(ref(own_text, 'Dictionary Value'), 100)
    append('SourceBlocks', ref(own_text, 'Dictionary Value')); end(has_own_text)
    links = get('answers', var('SourceRecord'))
    has_links = condition(ref(links, 'Dictionary Value'), 100)
    linked_loop = loop(ref(links, 'Dictionary Value'))
    linked = get(var('Repeat Item'), var('AnswersByID'))
    require(ref(linked, 'Dictionary Value'), 'Отдельная запись ссылается на отсутствующий ответ.')
    attach_answer(ref(linked)); end_loop(linked_loop); end(has_links)
    blocks = add('count', WFInput=var('SourceBlocks'), Input=var('SourceBlocks'))
    no_text = condition(ref(blocks, 'Count'), 4, WFNumberValue=0)
    stop('У отдельной записи нет поддерживаемого текста. Возможен rich-text-only формат; он не будет молча пропущен.'); end(no_text)
    finish_source('journal-entry'); end_loop(group)

    group = loop(ref(collections['routines'], 'Dictionary Value'))
    begin_source('routine')
    bucket = get(var('SourceKey'), var('AnswersByRoutine'))
    put('RoutineAnswers', ref(bucket, 'Dictionary Value'))
    has_bucket = condition(ref(bucket, 'Dictionary Value'), 100)
    def attach_unordered():
        put('OrderedCandidate', var('Repeat Item'))
        candidate_key = key_of(var('OrderedCandidate'))
        already = get(token(candidate_key, 'Text'), var('OrderedInSource'))
        unseen = condition(ref(already, 'Dictionary Value'), 101)
        attach_answer(var('OrderedCandidate')); end(unseen)
    questions = get('questions', var('SourceRecord'))
    has_questions = condition(ref(questions, 'Dictionary Value'), 100)
    question_loop = loop(ref(questions, 'Dictionary Value'))
    # Compare locally instead of using arbitrary question text as dictionary keys:
    # dots in a prompt must not be interpreted as a Dictionary key path.
    put('QuestionOrderKey', var('Repeat Item'))
    answer_loop = loop(var('RoutineAnswers'))
    candidate_question = get('question', var('Repeat Item'))
    candidate_question_text = text(token(candidate_question, 'Dictionary Value'))
    matching_question = condition(ref(candidate_question_text, 'Text'), 4, WFConditionalActionString=var('QuestionOrderKey'))
    attach_unordered(); end(matching_question); end_loop(answer_loop)
    end_loop(question_loop); end(has_questions)
    # Unlisted/missing question keys still retain their answers, in export order.
    linked_loop = loop(var('RoutineAnswers'))
    attach_unordered(); end_loop(linked_loop); end(has_bucket)
    count = add('count', WFInput=var('SourceAnswers'), Input=var('SourceAnswers'))
    has_answers = condition(ref(count, 'Count'), 5, WFNumberValue=0)
    finish_source('routine'); end(has_answers); end_loop(group)

    # Orphans are explicit plan entries with their original data, never silently discarded.
    group = loop(ref(collections['answers'], 'Dictionary Value'))
    put('OrphanCandidate', var('Repeat Item'))
    key = key_of(var('OrphanCandidate'))
    used = get(token(key, 'Text'), var('UsedAnswers'))
    orphan = condition(ref(used, 'Dictionary Value'), 101)
    begin_source('orphan-answer'); attach_answer(var('OrphanCandidate')); finish_source('orphan-answer')
    end(orphan); end_loop(group)
    return var('StoicPlan')
