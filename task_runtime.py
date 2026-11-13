"""One-shot recovery and persistent local scheduler; tasks run only while app is open."""
from __future__ import annotations
import asyncio
import sqlite3
import time
import uuid
from contextlib import contextmanager
from datetime import datetime,timezone,timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

class BrowserTimedOut(TimeoutError):pass

async def recover_once(invoke,reopen,emit=lambda message:None,sleep=asyncio.sleep):
    try:return await invoke(False)
    except BrowserTimedOut:
        emit('Browser timed out; recovery will restart the browser once after 60 seconds.')
        await sleep(60)
        await reopen()
        emit('Reopened browser. Rechecking page state; no automatic resubmission.')
        return await invoke(True)

def scheduled_timestamp(when:str,zone:str='America/New_York',now:float|None=None):
    if zone=='EST (fixed UTC-5)':tz=timezone(timedelta(hours=-5))
    elif zone=='UTC':tz=timezone.utc
    else:tz=ZoneInfo(zone)
    try:naive=datetime.strptime(when,'%Y-%m-%d %H:%M')
    except ValueError as exc:raise ValueError('Use YYYY-MM-DD HH:MM') from exc
    candidates=[]
    for fold in (0,1):
        local=naive.replace(tzinfo=tz,fold=fold)
        back=local.astimezone(timezone.utc).astimezone(tz)
        if back.replace(tzinfo=None)==naive:
            candidates.append(local.utcoffset())
    if not candidates:raise ValueError('This time does not exist in the selected time zone')
    if len(set(candidates))>1:raise ValueError('This time is ambiguous due to daylight saving time')
    stamp=naive.replace(tzinfo=tz).timestamp()
    if stamp<= (time.time() if now is None else now):raise ValueError('Schedule must be in the future')
    return stamp

class ScheduleStore:
    def __init__(self,path):
        self.path=Path(path)
        with self.connect() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY, due REAL NOT NULL, zone TEXT NOT NULL,
                task TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending',
                result TEXT NOT NULL DEFAULT '')''')
    @contextmanager
    def connect(self):
        self.path.parent.mkdir(parents=True,exist_ok=True)
        db=sqlite3.connect(self.path,timeout=10)
        db.row_factory=sqlite3.Row
        try:
            with db:yield db
        finally:db.close()
    def add(self,when,zone,task):
        if not task.strip():raise ValueError('Task cannot be empty')
        due=scheduled_timestamp(when,zone)
        key=uuid.uuid4().hex[:12]
        with self.connect() as db:
            db.execute('INSERT INTO jobs(id,due,zone,task,status,result) VALUES(?,?,?,?,?,?)',(key,due,zone,task,'pending',''))
        return key
    def listing(self):
        with self.connect() as db:
            return [dict(r) for r in db.execute('SELECT * FROM jobs ORDER BY rowid DESC')]
    def claim(self,now=None):
        now=time.time() if now is None else now
        with self.connect() as db:
            db.execute("UPDATE jobs SET status='missed',result='Scheduled run missed by over 15 minutes' WHERE status='pending' AND due<?",(now-900,))
            row=db.execute("SELECT * FROM jobs WHERE status='pending' AND due<=? ORDER BY due LIMIT 1",(now,)).fetchone()
            if not row:return None
            updated=db.execute("UPDATE jobs SET status='running' WHERE id=? AND status='pending'",(row['id'],))
            return dict(row) if updated.rowcount==1 else None
    def cancel(self,identity):
        with self.connect() as db:
            cur=db.execute("UPDATE jobs SET status='cancelled' WHERE id=? AND status='pending'",(identity,))
        return 'Cancelled.' if cur.rowcount else 'No pending task matches that ID.'
    def finish(self,identity,status,result):
        if status not in ('finished','failed','interrupted'):
            raise ValueError('Unexpected job status')
        with self.connect() as db:
            db.execute("UPDATE jobs SET status=?,result=? WHERE id=? AND status='running'",(status,str(result)[:20000],identity))
    def interrupt_running(self):
        with self.connect() as db:
            db.execute("UPDATE jobs SET status='interrupted',result='Previous app run ended before confirmation.' WHERE status='running'")
