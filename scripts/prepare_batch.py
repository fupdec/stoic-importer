#!/usr/bin/env python3
"""Prepare 10 text-only Stoic sessions; keep private source data out of logs."""
import argparse
import datetime as dt
import json
from pathlib import Path
import zipfile
from prepare_one_entry import render_answers, make_title, split_title_body, exclusive_write


def optional_title(text, limit=80):
    title = make_title(text, limit)
    return '' if title == 'Запись дневника' else title


def prepare(archive_path, limit=10, excluded_ids=()):
    if not 1 <= limit <= 10:
        raise ValueError('Batch must contain 1–10 records')
    with zipfile.ZipFile(archive_path) as archive:
        def read(name):
            members=[i for i in archive.infolist() if i.filename==name or i.filename.endswith('/'+name)]
            if len(members)!=1 or members[0].file_size>32*1024*1024:
                raise ValueError('Invalid JSON members')
            return json.loads(archive.read(members[0]))
        answers=read('answers.json'); routines=read('routines.json')
        if len({a['uuid'] for a in answers})!=len(answers): raise ValueError('Duplicate answers')
        grouped={}
        for a in answers: grouped.setdefault(a.get('routine'),[]).append(a)
        result=[]
        for routine in routines:
            if routine['uuid'] in excluded_ids or not routine.get('isCompleted'): continue
            linked=grouped.get(routine['uuid'],[])
            if not linked or any(a.get('assets') for a in linked):continue
            questions=routine.get('questions',[])
            linked.sort(key=lambda a:(questions.index(a.get('question')) if a.get('question') in questions else len(questions),a['timestamp'],a['uuid']))
            text,unresolved=render_answers(linked)
            if not text.strip(): continue
            stamp=min(a['timestamp'] for a in linked)
            instant=dt.datetime.fromtimestamp(stamp/1000,dt.timezone.utc)
            title, body = split_title_body(text)
            result.append(dict(sourceID=routine['uuid'],date=instant.isoformat(timespec='milliseconds').replace('+00:00','Z'),
                sourceCalendarDate=routine['date'],title=title,text=body,sourceText=text,attachmentCount=0,
                sourceAnswerTimestamps=[{'id':a['uuid'],'timestampMilliseconds':a['timestamp']} for a in linked],
                unresolvedStructuredAnswers=unresolved))
        result.sort(key=lambda e:(e['date'],e['sourceID']))
        return result[-limit:]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive');parser.add_argument('--output',required=True)
    args=parser.parse_args()
    try:
        excluded=set()
        # Avoid the explicit one-entry tests prepared in this workspace. This is
        # not a Journal query or a complete duplicate-prevention ledger.
        for p in Path('private').glob('**/*.json'):
            obj=json.loads(p.read_text())
            if isinstance(obj,dict) and 'sourceID' in obj: excluded.add(obj['sourceID'])
        entries=prepare(args.archive,excluded_ids=excluded)
        if len(entries)!=10: raise ValueError('Not enough complete text-only sessions')
        folder=Path(args.output);folder.mkdir(mode=0o700,parents=True,exist_ok=False)
        preview='\n\n'.join(f"{i}. {e['sourceCalendarDate']} — {e['title'] or '(без заголовка)'}\n\n{e['text']}" for i,e in enumerate(entries,1))
        payload=dict(schema='stoic-test-batch-v1',entries=entries,preview=preview)
        exclusive_write(folder/'stoic-batch-10.json',json.dumps(payload,ensure_ascii=False,indent=2)+'\n')
        exclusive_write(folder/'preview.txt',preview+'\n')
        print(f'Prepared {len(entries)} text-only sessions; {entries[0]["sourceCalendarDate"]} to {entries[-1]["sourceCalendarDate"]}.')
        print('Private payload and preview: mode 0600. No Journal writes performed.')
    except Exception:parser.exit(1,'Batch preparation failed. No diary content logged.\n')

if __name__=='__main__':main()
