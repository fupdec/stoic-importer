#!/usr/bin/env python3
"""Prepare ONE real Stoic standalone entry locally. Never logs diary text."""
import argparse
import datetime as dt
import json
import os
import uuid
import re
from pathlib import Path
import zipfile


DEFAULT_TITLE_MAX_LENGTH = 80


def make_title(text, max_length=DEFAULT_TITLE_MAX_LENGTH):
    """Use only the first line when strictly shorter than the configured limit."""
    if max_length < 1:
        raise ValueError('Title limit must be positive')
    normalized = text.replace('\r\n', '\n').replace('\r', '\n').strip()
    paragraph = normalized.split('\n', 1)[0]
    paragraph = re.sub(r'^\s*(?:#{1,6}\s+|[-*+]\s+|\d+[.)]\s+)', '', paragraph)
    title = ' '.join(paragraph.split())
    if title and len(title) < max_length and not is_reference(title) and not is_structured_value(title):
        return title
    return 'Запись дневника'


def split_title_body(text, max_length=DEFAULT_TITLE_MAX_LENGTH):
    """Promote first line only if it leaves nonempty body; retain all source text."""
    title = make_title(text, max_length)
    if title == 'Запись дневника':
        return '', text
    lines = text.splitlines(keepends=True)
    first = next((i for i, line in enumerate(lines) if line.strip()), None)
    if first is None:
        return '', text
    body = ''.join(lines[first + 1:])
    body = re.sub(r'^(?:[ \t]*\r?\n)+', '', body)
    if not body.strip():
        # Avoid empty-body writes when the entire entry is a single short line.
        return '', text
    return title, body


def is_reference(value):
    try:
        uuid.UUID(value)
        return True
    except (ValueError, TypeError, AttributeError):
        return False


def is_structured_value(text):
    # Unresolved built-in prompts may encode scales/choices as JSON. Preserve
    # them separately rather than inventing their meaning in the journal body.
    try:
        value = json.loads(text)
    except (ValueError, TypeError):
        return False
    return isinstance(value, (int, float, bool, list, dict)) or value is None


def render_answers(linked):
    blocks, unresolved = [], []
    for answer in linked:
        text = answer.get('text', '')
        if not text.strip():
            continue
        question = answer.get('question', '')
        if is_reference(question) and is_structured_value(text):
            unresolved.append({'answerID': answer['uuid'], 'questionID': question,
                               'rawValue': text, 'context': answer.get('context')})
            continue
        # A UUID is a foreign key, never the question's human-readable title.
        heading = question if question and not is_reference(question) else ''
        blocks.append((heading + '\n\n' if heading else '') + text)
    return '\n\n'.join(blocks), unresolved


def prepare(archive_path, title_max_length=DEFAULT_TITLE_MAX_LENGTH):
    with zipfile.ZipFile(archive_path) as archive:
        def read(name):
            members = [i for i in archive.infolist() if i.filename == name or i.filename.endswith('/' + name)]
            if len(members) != 1 or members[0].file_size > 32 * 1024 * 1024:
                raise ValueError('Missing, ambiguous, or oversized JSON member')
            return json.loads(archive.read(members[0]))
        answers = read('answers.json')
        lookup = {a['uuid']: a for a in answers}
        if len(lookup) != len(answers):
            raise ValueError('Duplicate answer IDs')
        entries = read('journal-entries.json')
        candidates = []
        for entry in entries:
            refs = entry.get('answers', [])
            if not refs or any(i not in lookup for i in refs):
                continue
            linked = [lookup[i] for i in refs]
            # The first test deliberately excludes media and rich-text-only content.
            if any(a.get('assets') for a in linked):
                continue
            if not any(a.get('text', '').strip() for a in linked):
                continue
            rendered, _ = render_answers(linked)
            if rendered.strip():
                candidates.append((entry, linked))
        if not candidates:
            raise ValueError('No complete text-only standalone entry available')
        entry, linked = max(candidates, key=lambda pair: pair[0]['timestamp'])
        instant = dt.datetime.fromtimestamp(entry['timestamp'] / 1000, dt.timezone.utc)
        text, unresolved = render_answers(linked)
        title, body = split_title_body(text, title_max_length)
        return {
            'schema': 'stoic-single-entry-v1',
            'sourceID': entry['uuid'],
            'date': instant.isoformat(timespec='milliseconds').replace('+00:00', 'Z'),
            'sourceTimestampMilliseconds': entry['timestamp'],
            'sourceCalendarDate': entry['calendarDate'],
            'title': title,
            'text': body,
            'sourceText': text,
            'unresolvedStructuredAnswers': unresolved,
            'attachmentCount': 0,
        }


def exclusive_write(path, text):
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, 'w', encoding='utf-8') as file:
        file.write(text)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive')
    parser.add_argument('--output', required=True)
    parser.add_argument('--title-max-length', type=int, default=DEFAULT_TITLE_MAX_LENGTH)
    args = parser.parse_args()
    if args.title_max_length < 1:
        parser.error('--title-max-length must be positive')
    # No exception repr/tracebacks: malformed input may contain diary strings.
    try:
        payload = prepare(args.archive, args.title_max_length)
        output = Path(args.output)
        output.mkdir(mode=0o700, parents=True, exist_ok=True)
        exclusive_write(output / 'stoic-one-entry.json', json.dumps(payload, ensure_ascii=False, indent=2) + '\n')
        preview = (f"# {payload['title']}\n\n"
                   f"Source calendar date: {payload['sourceCalendarDate']}\n\n"
                   f"Original instant (UTC): {payload['date']}\n\n"
                   "Timezone of the original device is not present in this entry. Journal may display this instant in the iPhone's current timezone.\n\n"
                   f"Unresolved structured answers kept separately in JSON: {len(payload['unresolvedStructuredAnswers'])}. They are excluded from the Journal body because their prompt definitions are absent.\n\n"
                   f"{payload['text']}\n")
        exclusive_write(output / 'preview.md', preview)
        print('Prepared exactly one text-only entry. Private JSON and preview saved with mode 0600.')
        print('Source calendar date: ' + payload['sourceCalendarDate'])
        print('Original instant (UTC): ' + payload['date'])
    except Exception:
        parser.exit(1, 'Preparation failed; check archive structure and choose a new output directory. No diary text logged.\n')


if __name__ == '__main__':
    main()
