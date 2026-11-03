"""Atomic local persistence. No database or external service required."""
import copy
import json
import re
import threading
import uuid
from pathlib import Path
import catalog


class WorkspaceLock:
    """OS-owned lock; released after a crash, without stale lock deletion."""
    def __init__(self,root):
        self.root=Path(root).resolve()
        self.handle=None

    def acquire(self):
        try:
            self.root.mkdir(parents=True,exist_ok=True)
            handle=(self.root/'workspace.lock').open('a+b')
        except OSError:
            raise ValueError('Cannot open this workspace for writing. Check folder access permissions.') from None
        try:
            handle.seek(0)
            if __import__('os').name=='nt':
                import msvcrt
                # Windows byte locks may extend beyond EOF. Do not read a
                # byte before locking: another instance may already own it.
                msvcrt.locking(handle.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except OSError:
            handle.close()
            raise ValueError('This workspace is already open in another workbench/CLI process. Use that window, or close it first.') from None
        self.handle=handle

    def release(self):
        if self.handle:
            self.handle.close()
            self.handle=None


class Store:
    def __init__(self,root):
        self.root=Path(root).resolve()
        self.lock=threading.RLock()
        for d in ('experiments','archives'):
            (self.root/d).mkdir(parents=True,exist_ok=True)

    def write(self,path,value):
        with self.lock:
            path=Path(path)
            path.parent.mkdir(parents=True,exist_ok=True)
            tmp=path.with_suffix('.tmp')
            tmp.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
            tmp.replace(path)

    def read(self,path):
        with self.lock:
            return json.loads(Path(path).read_text(encoding='utf-8-sig'))

    def dataset(self):
        path=self.root/'dataset.json'
        return self.read(path) if path.exists() else catalog.load_builtin()

    def save_dataset(self,data):
        clean=catalog.validate(data)
        self.write(self.root/'dataset.json',clean)
        return clean

    def path(self,eid):
        if not isinstance(eid,str) or not re.fullmatch(r'[a-f0-9]{32}',eid):
            raise ValueError('Invalid experiment identifier')
        return self.root/'experiments'/eid/'session.json'

    def get(self,eid):
        try:
            return self.read(self.path(eid))
        except FileNotFoundError:
            raise ValueError('Experiment not found') from None

    def save(self,session):
        self.write(self.path(session['id']),session)

    def listing(self):
        rows=[]
        for p in (self.root/'experiments').glob('*/session.json'):
            try:
                s=self.read(p)
                rows.append({k:copy.deepcopy(s[k]) for k in ('id','name','created_at','updated_at','status','config','batches')})
                rows[-1].update(assigned=len(s['plan']),finished=sum(r['status'] in __import__('engine').FINAL for r in s['runs']),
                    calls=sum(r['api_calls'] for r in s['runs']))
            except (ValueError,OSError,KeyError):
                continue
        return sorted(rows,key=lambda r:r['created_at'],reverse=True)

    def import_archive(self,data):
        if not isinstance(data,dict) or not isinstance(data.get('runs'),list) or not isinstance(data.get('metadata'),dict):
            raise ValueError('Expected a previous session JSON with metadata and runs')
        if len(data['runs'])>5000:
            raise ValueError('Archive too large')
        # Previous versions are retained as read-only evidence, never re-scored or resumed.
        aid=uuid.uuid4().hex
        self.write(self.root/'archives'/(aid+'.json'),data)
        return {'archive_id':aid,'run_count':len(data['runs']),'note':'Read-only archive; original schema retained, no automatic conversion or scoring'}
