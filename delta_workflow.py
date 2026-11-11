"""Helpers operate only on controls discovered in the current visible page."""
import asyncio
import json
import re
import sqlite3
from contextlib import contextmanager
from pathlib import Path

ADD = re.compile(r'^(?:add\s+(?:(?:another|a|new|second|2nd)\s+)?(?:solution|answer)|(?:additional|another|second|2nd)\s+(?:solution|answer)|\+\s*(?:add\s+)?(?:solution|answer))\s*\+?$',re.I)
EXAMPLE = re.compile(r'^(?:(?:show|view)\s+)?examples?$',re.I)

async def click_discovered(page, snapshot, pattern):
    choices=[b for b in snapshot.get('buttons',[]) if not b.get('disabled') and pattern.fullmatch(b.get('text','').strip())]
    if len(choices)!=1: raise ValueError('Expected one matching visible control; inspect a screenshot instead of guessing.')
    locator=page.locator(choices[0]['selector'])
    if await locator.count()!=1: raise ValueError('Control is stale. Read the page again.')
    await locator.click(timeout=5000)

async def enter_solution_set(delta, page, snapshot_token, answers):
    if not isinstance(answers,list) or not 1<=len(answers)<=8 or any(not isinstance(a,str) or not a.strip() or len(a)>2000 for a in answers):
        raise ValueError('Supply 1–8 nonempty solution strings for a single-variable equation.')
    if not delta.latest or delta.latest['token']!=snapshot_token or delta.latest['page'] is not page:
        raise ValueError('Read the current question first; snapshot is stale.')
    original=delta.latest['signature']
    snapshot=await delta.inspect(page)
    if snapshot['signature']!=original: raise ValueError('Question changed. Solve the new question.')
    while len(snapshot['fields'])<len(answers):
        before=len(snapshot['fields'])
        await click_discovered(page,snapshot,ADD)
        # The button may update the page asynchronously; allow a short bounded poll.
        for _ in range(10):
            snapshot=await delta.inspect(page)
            if len(snapshot['fields'])>before: break
            await asyncio.sleep(.2)
        if len(snapshot['fields'])<=before: raise ValueError('Add solution did not create a field. Inspect a screenshot; no answer was entered.')
        if snapshot['signature']!=original: raise ValueError('Question changed while adding fields. Inspect before entering.')
    if len(snapshot['fields'])!=len(answers):
        raise ValueError('Field count differs from solution count. Inspect labels; do not guess field mapping.')
    results=[]
    for field,answer in zip(snapshot['fields'],answers):
        result=await delta.enter(page,snapshot['snapshot_token'],field['id'],answer,'latex' if field['kind']=='mathquill' else 'text')
        results.append(result)
        if result.get('requires_visual_verification'):
            # Continue entering the known set, but never submit it here.
            pass
    return {'entries':results,'submitted':False,'requires_visual_verification':True,
            'next':'Inspect a screenshot of ALL solution fields, then check website feedback after submission.'}

class ExampleNotes:
    def __init__(self,path): self.path=Path(path)
    @contextmanager
    def connect(self):
        self.path.parent.mkdir(parents=True,exist_ok=True)
        db=sqlite3.connect(self.path)
        try:
            with db:
                db.execute('CREATE TABLE IF NOT EXISTS observed_examples(topic TEXT PRIMARY KEY, note TEXT)')
                yield db
        finally:db.close()
    def save(self,topic,note):
        with self.connect() as db: db.execute('INSERT OR REPLACE INTO observed_examples VALUES(?,?)',(topic[:300],json.dumps(note)))
    def search(self,query):
        words=set(re.findall(r'[a-z]+',query.lower()))
        with self.connect() as db: rows=db.execute('SELECT topic,note FROM observed_examples').fetchall()
        scored=[(len(words & set(re.findall(r'[a-z]+',topic.lower()))),topic,note) for topic,note in rows]
        return [{'topic':topic,'example':json.loads(note),'verification':'Observed example interpreted by AI; reuse the method, not its answer.'} for score,topic,note in sorted(scored,reverse=True)[:3] if score>=2]
