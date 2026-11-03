"""Command-line alternative to the local workbench UI."""
import argparse
import json
from pathlib import Path
import sys
import app
from manager import Manager
from storage import Store,WorkspaceLock

ROOT=Path(__file__).resolve().parent


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--live',action='store_true')
    p.add_argument('--suite',action='store_true')
    p.add_argument('--case',default='D01')
    p.add_argument('--policies',nargs='+',default=['cost_aware'])
    p.add_argument('--model',default='gpt-5-mini-2025-08-07')
    p.add_argument('--provider',choices=('openai','anthropic','gemini'),default='openai')
    p.add_argument('--repeats',type=int,default=1)
    p.add_argument('--max-calls',type=int,default=6)
    p.add_argument('--seed',type=int,default=2027)
    p.add_argument('--config',type=Path,help='Explicit JSON experiment configuration')
    p.add_argument('--resume',help='Existing experiment ID in this workspace')
    p.add_argument('--workspace',type=Path,default=ROOT/'workspace')
    args=p.parse_args()
    lock=WorkspaceLock(args.workspace)
    try:
        lock.acquire()
    except ValueError as error:
        p.exit(1,str(error)+'\n')
    store=Store(args.workspace)
    manager=Manager(store)
    try:
        if args.resume:
            session=store.get(args.resume)
        else:
            config=json.loads(args.config.read_text(encoding='utf-8-sig')) if args.config else {
                'mode':'live' if args.live else 'offline',
                'case_ids':[c['id'] for c in store.dataset()['cases'] if c['split']=='development'] if args.suite else [args.case],
                'policies':args.policies if not args.suite or args.policies!=['cost_aware'] else ['cost_aware','always_reverify','llm'],
                'models':[{'provider':args.provider,'model':args.model}],
                'repeats':args.repeats,'seed':args.seed}
            session=manager.create(config,'CLI experiment')
        manager.start(session['id'],args.max_calls)
    except (ValueError,KeyError,OSError) as e:
        p.exit(1,str(e)+'\n')
    print('Experiment:',session['id'])
    print('Mode:',session['config']['mode'],'| Additional call cap:',args.max_calls if session['config']['mode']=='live' else 0)
    seen=set()
    try:
        while manager.thread.is_alive():
            manager.thread.join(.2)
            current=store.get(session['id'])
            for r in current['runs']:
                if r['episode_id'] not in seen and r['status'] in __import__('engine').FINAL:
                    seen.add(r['episode_id'])
                    print(f"{r['case']} / {r['policy']} / {r['profile']['model']}: {r['status']}; calls={r['api_calls']}")
    except KeyboardInterrupt:
        manager.stop.set()
        print('Pause requested; waiting for the current request to finish.')
        while manager.thread.is_alive():
            manager.thread.join(.2)
    current=store.get(session['id'])
    folder=store.path(session['id']).parent/'exports'
    folder.mkdir(exist_ok=True)
    for kind in ('csv','events','report','latex'):
        content,mime,name=app.export(current,kind)
        (folder/name).write_bytes(content)
    print('Status:',current['status'])
    print('Share:',store.path(session['id']))
    print('Report:',folder/'report.html')
    lock.release()
    return 0 if current['status']=='completed' else 2


if __name__=='__main__':
    sys.exit(main())
