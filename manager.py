"""One local worker, finite per-batch budgets, pause/resume and frozen records."""
import copy
import platform
import threading
import time
import uuid
import catalog
import engine
import providers
import contracts


def now():
    return time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())


class Manager:
    def __init__(self,store,call=providers.infer):
        self.store=store
        self.call=call
        self.lock=threading.RLock()
        self.thread=None
        self.active=None
        self.stop=threading.Event()
        # A process interruption never causes an automatic billed retry.
        for item in store.listing():
            s=store.get(item['id'])
            if s['status']=='running':
                s.update(status='paused_restart',updated_at=now())
                store.save(s)

    def create(self,config,name='New experiment',dataset=None,study_design=None):
        draft=engine.plan(config,self.store.dataset() if dataset is None else dataset)
        session={'id':uuid.uuid4().hex,'version':'1.2','name':str(name).strip()[:120] or 'New experiment',
            'created_at':now(),'updated_at':now(),'status':'ready','config':draft['config'],
            'plan':draft['pairs'],'dataset':draft['dataset'],'dataset_sha256':draft['dataset_sha256'],
            'fingerprint':draft['fingerprint'],'readiness':draft['readiness'],'runs':[],'batches':[],
            'prompt':contracts.PROMPT,'research_status':'engineering/development unless independently reviewed evaluation',
            'oracle_gate':'Simulator knows truth and labels. Count proposals before the gate; no clinical safety claim.'}
        if study_design is not None:
            session['study_design']=copy.deepcopy(study_design)
        session['protocol_documents']={p.name:p.read_text(encoding='utf-8') for p in (engine.ROOT/'docs').glob('*.md')}
        session['protocol_sha256']=contracts.digest(session['protocol_documents'])
        session['runtime']={'python':platform.python_version(),'platform':platform.system(),'architecture':platform.machine()}
        self.store.save(session)
        return session

    def start(self,eid,cap=6):
        if type(cap) is not int or not 1<=cap<=10000:
            raise ValueError('Call cap must be an integer from 1 to 10000')
        with self.lock:
            if self.thread and self.thread.is_alive():
                raise ValueError('Another experiment is running; pause it before starting a new one')
            session=self.store.get(eid)
            if session['fingerprint']!=engine.code_fingerprint() or session['dataset_sha256']!=contracts.digest(session['dataset']):
                raise ValueError('Frozen code or dataset changed; create a new experiment')
            if session['status']=='completed':
                raise ValueError('Experiment is already complete; completed attempts are never repeated')
            if session['config']['mode']=='live':
                missing=[providers.KEYS[p['provider']] for p in session['config']['models'] if not providers.read_key(p['provider'])]
                if missing:
                    raise ValueError('Missing local keys: '+', '.join(sorted(set(missing))))
            self.stop.clear()
            self.active=eid
            session['batches'].append({'started_at':now(),'call_cap':cap if session['config']['mode']=='live' else 0,'calls_used':0})
            session.update(status='running',updated_at=now())
            self.store.save(session)
            self.thread=threading.Thread(target=self._work,args=(session,cap),daemon=True)
            self.thread.start()
        return {'id':eid,'status':'running'}

    def pause(self,eid):
        with self.lock:
            if eid!=self.active or not self.thread or not self.thread.is_alive():
                raise ValueError('Experiment is not running')
            self.stop.set()
        return {'status':'pause_requested','note':'The current request may finish and be billed. No further request will start.'}

    def _work(self,session,cap):
        budget={'used':0,'cap':cap}
        cases={c['id']:c for c in session['dataset']['cases']}
        try:
            for condition in session['plan']:
                i=next((i for i,r in enumerate(session['runs']) if r['episode_id']==condition['episode_id']),None)
                old=session['runs'][i] if i is not None else None
                if old and old['status'] in engine.FINAL:
                    continue
                if self.stop.is_set():
                    session['status']='paused_user'
                    break
                if session['config']['mode']=='live' and budget['used']>=cap:
                    session['status']='paused_budget'
                    break
                if i is None:
                    i=len(session['runs'])
                    session['runs'].append({})
                def checkpoint(row):
                    session['runs'][i]=copy.deepcopy(row)
                    session['batches'][-1]['calls_used']=budget['used']
                    session['updated_at']=now()
                    self.store.save(session)
                row=engine.episode(cases[condition['case']],condition,session['config'],budget,
                    previous=old,call=self.call,checkpoint=checkpoint,should_stop=self.stop.is_set)
                if row['status'] in ('paused_budget','paused_user'):
                    session['status']=row['status']
                    break
                if row['status']=='error' and row['steps'][-1]['stage']=='provider':
                    session['status']='paused_provider_error'
                    break
            else:
                session['status']='completed'
        except Exception as error:
            # Keep previous checkpoints; deliberately avoid untrusted exception text.
            session.update(status='paused_internal_error',internal_error_type=type(error).__name__)
        finally:
            session['batches'][-1].update(calls_used=budget['used'],finished_at=now())
            session['updated_at']=now()
            self.store.save(session)
            with self.lock:
                self.active=None
