"""Descriptive summaries and scenario-clustered paired cost intervals."""
import csv
import html
import io
import json
import random
import statistics
from collections import defaultdict
import engine


def group_key(row):
    return row['profile']['provider']+' / '+row['profile']['model']+' / '+row['policy']


def summarize(session):
    by_id={r['episode_id']:r for r in session['runs']}
    groups={}
    for p in session['plan']:
        key=group_key(p)
        g=groups.setdefault(key,{'condition':key,'assigned':0,'finished':0,'errors':0,'outcome_met':0,
            'delivered':0,'escalated':0,'blocked':0,'unsafe_episodes':0,'unsupported_episodes':0,
            'questions':0,'query_cost':0,'api_calls':0,'input_tokens':0,'output_tokens':0,
            'extraction_error_turns':0,'accepted_extraction_error_turns':0,
            'rejected_evidence':0,'guard_changed_controller_turns':0,'api_seconds':0})
        g['assigned']+=1
        r=by_id.get(p['episode_id'])
        if not r:
            continue
        if r['status'] in engine.FINAL:
            g['finished']+=1
            g['errors']+=r['status'] in ('error','interrupted_unknown','step_limit','deadline_missed')
            g['outcome_met']+=bool(r.get('expected_outcome_met'))
        g['delivered']+=r['status']=='delivered'
        g['escalated']+=r['status']=='escalated'
        g['blocked']+=r['status']=='dispatch_blocked'
        g['unsafe_episodes']+=r.get('unsafe_proposals',0)>0
        g['unsupported_episodes']+=r.get('unsupported_proposals',0)>0
        for name in ('questions','query_cost','api_calls','input_tokens','output_tokens','extraction_error_turns',
                     'accepted_extraction_error_turns','rejected_evidence','guard_changed_controller_turns','api_seconds'):
            g[name]+=r.get(name,r.get('extraction_error_turns',0) if name=='accepted_extraction_error_turns' else 0)
    return {'mode':session['config']['mode'],'purpose':session['config']['purpose'],
        'evidence_mode':session['config'].get('evidence_mode','raw'),
        'complete':all(p['episode_id'] in by_id and by_id[p['episode_id']]['status'] in engine.FINAL for p in session['plan']),
        'groups':list(groups.values()),'paired_cost':paired_cost(session),
        'notes':['Offline fixture rows are software checks, not LLM performance.',
        'Costs are synthetic human-interruption units, not API currency. Tokens are provider-reported, not directly equivalent across providers.',
        'Raw extraction errors remain recorded. Explicit-support filtering is a bounded Greek/English lexical guard, not a general semantic verifier. LLM actions remain model-selected.',
        'Outcome reference and dispatch filter use hidden simulator truth. Zero executed unsafe actions is not a safety result.',
        'Costs/tokens include attempted partial or failed episodes. Interpret partial coverage before comparing conditions.',
        'Paired intervals are exploratory, clustered by scenario, and do not establish non-inferiority or clinical safety.']}


def paired_cost(session):
    models={r['profile']['provider']+'/'+r['profile']['model'] for r in session['runs']}
    contrasts=[]
    for model in sorted(models):
        matched=defaultdict(dict)
        for r in session['runs']:
            if r['profile']['provider']+'/'+r['profile']['model']!=model or r['policy'] not in ('cost_aware','always_reverify'):
                continue
            if r['status'] not in ('delivered','escalated','dispatch_blocked'):
                continue
            matched[(r['case'],r['repetition'])][r['policy']]=r
        per_case=defaultdict(list)
        outcome_disagreements=0
        for (case,rep),pairs in matched.items():
            if set(pairs)!={'cost_aware','always_reverify'}:
                continue
            a,b=pairs['cost_aware'],pairs['always_reverify']
            per_case[case].append(a['query_cost']-b['query_cost'])
            outcome_disagreements+=a['expected_outcome_met']!=b['expected_outcome_met']
        values=[statistics.mean(v) for k,v in sorted(per_case.items())]
        if not values:
            continue
        interval=None
        if len(values)>=2:
            rng=random.Random(2027)
            boot=sorted(statistics.mean(rng.choices(values,k=len(values))) for _ in range(2000))
            interval=[boot[49],boot[1949]]
        contrasts.append({'model':model,'contrast':'cost_aware minus always_reverify',
            'scenario_clusters':len(values),'paired_repetitions':sum(len(v) for v in per_case.values()),
            'mean_cost_difference':statistics.mean(values),'exploratory_95_percentile_interval':interval,
            'outcome_disagreements':outcome_disagreements,
            'exclusion':'Only matched technically completed episodes; all technical failures remain in the main table. Scenario independence must be justified by study design.'})
    return contrasts


def csv_export(session,events=False):
    out=io.StringIO(newline='')
    if events:
        keys=('episode_id','case','policy','provider','model','repetition','step','action','recipient','result','cost','time','error','error_stage')
        rows=[]
        for r in session['runs']:
            for i,s in enumerate(r['steps'],1):
                rows.append(dict(episode_id=r['episode_id'],case=r['case'],policy=r['policy'],
                    provider=r['profile']['provider'],model=r['profile']['model'],repetition=r['repetition'],
                    step=i,error=s.get('error',''),error_stage=s.get('stage',''),**{k:v for k,v in s.get('transition',{}).items() if k in keys}))
    else:
        keys=('episode_id','case','family','policy','provider','model','repetition','status','expected_outcome_met',
              'questions','query_cost','waits','elapsed_steps','unsafe_proposals','unsupported_proposals',
              'extraction_error_turns','accepted_extraction_error_turns','rejected_evidence',
              'guard_changed_controller_turns','validation_errors','api_calls','input_tokens','output_tokens','api_seconds')
        rows=[dict(r,provider=r['profile']['provider'],model=r['profile']['model']) for r in session['runs']]
    writer=csv.DictWriter(out,fieldnames=keys,extrasaction='ignore')
    writer.writeheader()
    for row in rows:
        # Prevent spreadsheet formula interpretation of editable scenario/model names.
        clean={k:('\''+v if isinstance(v,str) and v.startswith(('=','+','-','@')) else v) for k,v in row.items()}
        writer.writerow(clean)
    return '\ufeff'+out.getvalue()


def latex_export(session):
    def escape(text):
        return ''.join({'\\':r'\textbackslash{}','_':r'\_','&':r'\&','%':r'\%','$':r'\$','#':r'\#','{':r'\{','}':r'\}'}.get(c,c) for c in str(text))
    lines=['% Exploratory simulator results; no clinical validation.',r'\begin{tabular}{lrrrr}',
           r'Condition & Finished/assigned & Cost & Unsafe proposals (episodes) & Errors \\',r'\hline']
    for g in summarize(session)['groups']:
        lines.append(f"{escape(g['condition'])} & {g['finished']}/{g['assigned']} & {g['query_cost']:g} & {g['unsafe_episodes']} & {g['errors']} \\\\")
    lines.append(r'\end{tabular}')
    return '\n'.join(lines)+'\n'


def html_report(session):
    report=summarize(session)
    keys=('condition','assigned','finished','outcome_met','query_cost','extraction_error_turns',
          'accepted_extraction_error_turns','rejected_evidence','unsafe_episodes','unsupported_episodes','errors','api_calls','input_tokens','output_tokens')
    esc=lambda value:html.escape(str(value))
    rows=''.join('<tr>'+''.join('<td>'+esc(g[k])+'</td>' for k in keys)+'</tr>' for g in report['groups'])
    heading='LIVE API' if report['mode']=='live' else 'OFFLINE FIXTURE — NOT LLM RESULTS'
    doc='<!doctype html><html lang="en"><meta charset="utf-8"><title>RSS2027 experiment report</title><style>body{font:15px system-ui;max-width:1300px;margin:40px auto;padding:0 20px;color:#233247}table{border-collapse:collapse}th,td{padding:10px;border-bottom:1px solid #ddd;text-align:left}pre{white-space:pre-wrap;background:#f3f5f8;padding:18px}.scroll{overflow:auto}details{margin:18px 0}</style>'
    doc+='<h1>'+esc(session['name'])+'</h1><p>'+heading+' · '+esc(session['created_at'])+' · '+esc(session['status'])+'</p>'
    doc+='<p>'+esc(' | '.join(report['notes']))+'</p><div class="scroll"><table><tr>'+''.join('<th>'+esc(k)+'</th>' for k in keys)+'</tr>'+rows+'</table></div>'
    doc+='<h2>Exploratory paired costs</h2><pre>'+esc(json.dumps(report['paired_cost'],ensure_ascii=False,indent=2))+'</pre>'
    doc+='<h2>Frozen configuration</h2><pre>'+esc(json.dumps(session['config'],ensure_ascii=False,indent=2))+'</pre>'
    for r in session['runs']:
        doc+='<details><summary>'+esc(r['case']+' / '+r['policy']+' / '+r['status'])+'</summary><pre>'+esc(json.dumps(r,ensure_ascii=False,indent=2))+'</pre></details>'
    return doc+'</html>'
