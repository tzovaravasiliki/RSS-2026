"""Local RSS2027 workbench. Bind to loopback only; Python 3.10+, standard library."""
from __future__ import annotations
import argparse
import io
import json
import secrets
import threading
import webbrowser
import zipfile
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit,parse_qs
import analysis
import catalog
import contracts
import engine
from manager import Manager
import providers
from storage import Store,WorkspaceLock

ROOT=Path(__file__).resolve().parent
DOCS={'README_GR.md':ROOT/'README_GR.md',**{p.name:p for p in (ROOT/'docs').glob('*.md')}}


def export(session,kind):
    if kind=='session':
        return json.dumps(session,ensure_ascii=False,indent=2).encode(),'application/json','session.json'
    if kind=='csv':
        return analysis.csv_export(session).encode(),'text/csv; charset=utf-8','episodes.csv'
    if kind=='events':
        return analysis.csv_export(session,True).encode(),'text/csv; charset=utf-8','events.csv'
    if kind=='report':
        return analysis.html_report(session).encode(),'text/html; charset=utf-8','report.html'
    if kind=='latex':
        return analysis.latex_export(session).encode(),'text/plain; charset=utf-8','results.tex'
    if kind!='zip':
        raise ValueError('Unknown export format')
    out=io.BytesIO()
    with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
        for k in ('session','csv','events','report','latex'):
            content,mime,name=export(session,k)
            z.writestr(name,content)
        z.writestr('summary.json',json.dumps(analysis.summarize(session),ensure_ascii=False,indent=2))
        z.writestr('frozen_dataset.json',json.dumps(session['dataset'],ensure_ascii=False,indent=2))
        for name,path in DOCS.items():
            z.writestr('docs/'+name,session.get('protocol_documents',{}).get(name,path.read_text(encoding='utf-8')))
    return out.getvalue(),'application/zip','RSS2027_'+session['id'][:8]+'.zip'


def make_server(workspace,port=8765,call=providers.infer):
    store=Store(workspace)
    manager=Manager(store,call)
    token=secrets.token_hex(32)
    class Handler(BaseHTTPRequestHandler):
        server_version='RSS2027/1.1'
        def log_message(self,*args):
            pass

        def allowed(self,post=False):
            actual=self.server.server_address[1]
            valid={'127.0.0.1:'+str(actual),'localhost:'+str(actual)}
            if self.headers.get('Host') not in valid:
                return False
            if post:
                origin=self.headers.get('Origin')
                if origin and origin not in {'http://'+h for h in valid}:
                    return False
                return secrets.compare_digest(self.headers.get('X-Workbench-Token',''),token)
            return True

        def send(self,body,status=200,mime='application/json; charset=utf-8',filename=None):
            if not isinstance(body,(bytes,bytearray)):
                body=json.dumps(body,ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header('Content-Type',mime)
            self.send_header('Content-Length',str(len(body)))
            self.send_header('Cache-Control','no-store')
            self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('Referrer-Policy','no-referrer')
            self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; object-src 'none'")
            if filename:
                self.send_header('Content-Disposition','attachment; filename="'+filename+'"')
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError,ConnectionResetError):
                pass

        def do_GET(self):
            if not self.allowed():
                return self.send({'error':'Local origin required'},403)
            parsed=urlsplit(self.path)
            path=parsed.path
            try:
                if path=='/':
                    body=(ROOT/'web/index.html').read_text(encoding='utf-8').replace('__CSRF__',token).encode()
                    return self.send(body,mime='text/html; charset=utf-8')
                if path in ('/web/app.js','/web/style.css'):
                    return self.send((ROOT/path[1:]).read_bytes(),mime='application/javascript' if path.endswith('.js') else 'text/css')
                if path=='/favicon.ico':
                    return self.send(b'',204,'image/x-icon')
                if path=='/api/state':
                    data=store.dataset()
                    return self.send({'version':'1.1','keys':providers.key_status(),'experiments':store.listing(),
                        'case_count':len(data['cases']),'dataset_name':data['name'],'policies':engine.POLICIES,
                        'active':manager.active,'workspace':str(store.root),'documents':list(DOCS)})
                if path=='/api/dataset':
                    return self.send(store.dataset())
                if path.startswith('/api/docs/'):
                    name=path.rsplit('/',1)[-1]
                    if name not in DOCS:
                        raise ValueError('Document not found')
                    return self.send({'name':name,'text':DOCS[name].read_text(encoding='utf-8')})
                parts=path.strip('/').split('/')
                if len(parts)>=3 and parts[:2]==['api','experiments']:
                    s=store.get(parts[2])
                    if len(parts)==3:
                        return self.send({'session':s,'summary':analysis.summarize(s)})
                    if len(parts)==4 and parts[3]=='export':
                        body,mime,name=export(s,parse_qs(parsed.query).get('format',['zip'])[0])
                        return self.send(body,mime=mime,filename=name)
                return self.send({'error':'Not found'},404)
            except (ValueError,KeyError,TypeError,OSError) as error:
                return self.send({'error':str(error) if isinstance(error,ValueError) else 'Invalid or unavailable local resource'},400)

        def do_POST(self):
            if not self.allowed(True):
                return self.send({'error':'Local request token required'},403)
            try:
                length=int(self.headers.get('Content-Length','0'))
                if not 0<length<=8*1024*1024 or self.headers.get('Content-Type','').split(';')[0]!='application/json':
                    raise ValueError('Expected JSON body, maximum 8 MiB')
                body=json.loads(self.rfile.read(length))
                path=urlsplit(self.path).path
                if path=='/api/plan':
                    p=engine.plan(body['config'],store.dataset())
                    del p['dataset']
                    return self.send(p)
                if path=='/api/dataset':
                    store.save_dataset(body['dataset'])
                    return self.send({'saved':True,'case_count':len(body['dataset']['cases'])})
                if path=='/api/import-session':
                    return self.send(store.import_archive(body['session']))
                if path=='/api/experiments':
                    return self.send(manager.create(body['config'],body.get('name','New experiment')))
                parts=path.strip('/').split('/')
                if len(parts)==4 and parts[:2]==['api','experiments']:
                    if parts[3]=='start':
                        return self.send(manager.start(parts[2],body.get('max_calls',6)))
                    if parts[3]=='pause':
                        return self.send(manager.pause(parts[2]))
                return self.send({'error':'Not found'},404)
            except (ValueError,KeyError,TypeError,OverflowError) as error:
                return self.send({'error':str(error) if isinstance(error,ValueError) else 'Missing or invalid request field'},400)
    server=ThreadingHTTPServer(('127.0.0.1',port),Handler)
    server.workbench_manager=manager
    server.workbench_store=store
    return server


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port',type=int,default=8765)
    parser.add_argument('--workspace',type=Path,default=ROOT/'workspace')
    parser.add_argument('--no-browser',action='store_true')
    args=parser.parse_args()
    if not 0<=args.port<=65535:
        parser.error('Invalid port')
    lock=WorkspaceLock(args.workspace)
    try:
        lock.acquire()
    except ValueError as error:
        parser.exit(1,str(error)+'\n')
    try:
        server=make_server(args.workspace,args.port)
    except OSError:
        if args.port!=8765:
            parser.exit(1,'Port unavailable; choose --port 0 for an available local port.\n')
        server=make_server(args.workspace,0)
    url='http://127.0.0.1:'+str(server.server_address[1])
    print('RSS2027 Research Workbench 1.1 — explicit evidence support')
    print('Open:',url)
    print('Workspace:',server.workbench_store.root)
    print('Offline by default. No API request is made by opening the application.')
    print('Keep this window open. Ctrl+C stops the server; in-flight API requests are never retried automatically.')
    if not args.no_browser:
        threading.Timer(.7,lambda:webbrowser.open(url)).start()
    try:
        server.serve_forever(poll_interval=.25)
    except KeyboardInterrupt:
        server.workbench_manager.stop.set()
    finally:
        server.server_close()
        lock.release()


if __name__=='__main__':
    main()
