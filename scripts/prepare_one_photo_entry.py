#!/usr/bin/env python3
"""Prepare one complete routine with exactly one photo; no private data in logs."""
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import zipfile
from prepare_one_entry import exclusive_write, render_answers, make_title, split_title_body, DEFAULT_TITLE_MAX_LENGTH


def prepare(archive_path, title_max_length=DEFAULT_TITLE_MAX_LENGTH):
    with zipfile.ZipFile(archive_path) as archive:
        members = archive.infolist()
        def read(name):
            found = [i for i in members if i.filename == name or i.filename.endswith('/' + name)]
            if len(found) != 1 or found[0].file_size > 32 * 1024 * 1024:
                raise ValueError('Invalid JSON members')
            return json.loads(archive.read(found[0]))
        answers, assets, routines = read('answers.json'), read('assets.json'), read('routines.json')
        asset_map = {a['uuid']: a for a in assets}
        if len(asset_map) != len(assets):
            raise ValueError('Duplicate assets')
        grouped = {}
        for answer in answers:
            grouped.setdefault(answer.get('routine'), []).append(answer)
        candidates = []
        for routine in routines:
            linked = grouped.get(routine['uuid'], [])
            # Retain source order where the export supplies it.
            questions = routine.get('questions', [])
            linked.sort(key=lambda a: (questions.index(a.get('question')) if a.get('question') in questions else len(questions), a.get('timestamp', 0), a['uuid']))
            refs = [ref for a in linked for ref in a.get('assets', [])]
            if len(refs) != 1 or refs[0] not in asset_map:
                continue
            asset = asset_map[refs[0]]
            if asset.get('type') != 'image' or asset.get('answer') not in {a['uuid'] for a in linked}:
                continue
            text, unresolved = render_answers(linked)
            if text.strip():
                candidates.append((max(a['timestamp'] for a in linked), routine, linked, asset, text, unresolved))
        if not candidates:
            raise ValueError('No complete single-photo routine')
        _, routine, linked, asset, text, unresolved = max(candidates, key=lambda c: c[0])
        owner = next(a for a in linked if a['uuid'] == asset['answer'])
        stamp = owner['timestamp']
        instant = dt.datetime.fromtimestamp(stamp / 1000, dt.timezone.utc)
        relative = asset['relativePath']
        if not relative or relative.startswith('/') or '..' in relative.split('/') or '\\' in relative:
            raise ValueError('Unsafe attachment path')
        matches = [i for i in members if i.filename == relative or i.filename.endswith('/' + relative)]
        if len(matches) != 1 or matches[0].is_dir() or matches[0].file_size > 32 * 1024 * 1024:
            raise ValueError('Missing/ambiguous/oversized photo')
        if (matches[0].external_attr >> 16) & 0o170000 == 0o120000:
            raise ValueError('Attachment is a symlink')
        photo = archive.read(matches[0])  # ZIP reader verifies CRC; never extract a supplied path.
        extension = Path(relative).suffix.lower()
        if extension not in {'.jpg', '.jpeg', '.png', '.heic'}:
            raise ValueError('Unsupported image extension')
        filename = 'stoic-test-photo' + extension
        title, body = split_title_body(text, title_max_length)
        payload = {
            'schema': 'stoic-single-entry-v1', 'sourceID': routine['uuid'],
            'title': title,
            'date': instant.isoformat(timespec='milliseconds').replace('+00:00', 'Z'),
            'sourceCalendarDate': routine['date'], 'sourceTimestampMilliseconds': stamp,
            'timestampPolicy': 'Original timestamp of the photo-owning answer; original timezone unknown.',
            'text': body, 'sourceText': text, 'attachmentCount': 1, 'attachmentFileName': filename,
            'attachmentSHA256': hashlib.sha256(photo).hexdigest(),
            'unresolvedStructuredAnswers': unresolved,
        }
        return payload, photo


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive'); parser.add_argument('--output', required=True)
    parser.add_argument('--title-max-length', type=int, default=DEFAULT_TITLE_MAX_LENGTH)
    args = parser.parse_args()
    if args.title_max_length < 1:
        parser.error('--title-max-length must be positive')
    try:
        payload, photo = prepare(args.archive, args.title_max_length)
        output = Path(args.output)
        # Entirely new directory prevents collisions or mixing prepared batches.
        output.mkdir(mode=0o700, parents=True, exist_ok=False)
        exclusive_write(output / 'stoic-one-photo-entry.json', json.dumps(payload, ensure_ascii=False, indent=2) + '\n')
        descriptor = os.open(output / payload['attachmentFileName'], os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, 'wb') as f: f.write(photo)
        exclusive_write(output / 'preview.md', '# ' + payload['title'] + '\n\n' + payload['text'] +
                        '\n\n![Photo](' + payload['attachmentFileName'] + ')\n')
        print('Prepared one routine and exactly one original photo. Private files: mode 0600.')
        print('Source calendar date: ' + payload['sourceCalendarDate'])
        print('Original photo-answer instant (UTC): ' + payload['date'])
        print('Photo file: ' + payload['attachmentFileName'])
    except Exception:
        parser.exit(1, 'Preparation failed. Check archive and choose a new output directory. No private text logged.\n')


if __name__ == '__main__': main()
