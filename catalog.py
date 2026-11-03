"""Dataset validation, public/private separation and immutable snapshots."""
import copy
import json
import math
import re
from pathlib import Path
import temporal_core as core

ROOT=Path(__file__).resolve().parent


def number(value, name, minimum=0, integer=False):
    if type(value) not in (int,float) or not math.isfinite(value) or value<minimum or (integer and type(value) is not int):
        raise ValueError('Invalid numeric field: '+name)


def validate(data):
    if not isinstance(data,dict) or not isinstance(data.get('cases'),list) or not 1<=len(data['cases'])<=500:
        raise ValueError('Dataset must contain 1–500 cases')
    ids=set()
    for case in data['cases']:
        sid=case.get('id','')
        if not isinstance(sid,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,48}',sid) or sid in ids:
            raise ValueError('Case ID must be unique and contain letters, digits, underscores or hyphens')
        ids.add(sid)
        for key in ('title','family','split'):
            if not isinstance(case.get(key),str) or not case[key].strip():
                raise ValueError(sid+': missing '+key)
        if case['split'] not in ('development','candidate','evaluation'):
            raise ValueError(sid+': invalid split')
        number(case['initial_ttl'],'initial_ttl',integer=True)
        p=case['public']
        if not isinstance(p['subject'],str) or not p['subject'] or len(p['subject'])>80:
            raise ValueError(sid+': invalid subject')
        for key in ('now','deadline'):
            number(p[key],key,integer=True)
        if p['deadline']<p['now']:
            raise ValueError(sid+': deadline before initial time')
        if not isinstance(p['aliases'],dict) or any(not isinstance(k,str) or not isinstance(v,str) or not k or not v for k,v in p['aliases'].items()):
            raise ValueError(sid+': invalid aliases')
        if any(v in p['aliases'] and p['aliases'][v]!=v for v in p['aliases'].values()):
            raise ValueError(sid+': alias chains/cycles are unsupported; use direct canonical names')
        for name in ('probability_knows','query_cost','available_at'):
            if set(p[name])!={'H2','H3'}:
                raise ValueError(sid+': source maps require H2 and H3')
            for v in p[name].values():
                number(v,name,integer=name=='available_at')
                if name=='probability_knows' and v>1:
                    raise ValueError(sid+': knowledge probability exceeds 1')
        if not isinstance(case['messages'],list) or not 1<=len(case['messages'])<=100:
            raise ValueError(sid+': requires 1–100 initial messages')
        mids=set()
        lookup={}
        for m in case['messages']:
            if not isinstance(m['message_id'],str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,48}',m['message_id']) or m['message_id'] in mids:
                raise ValueError(sid+': invalid/duplicate message ID')
            mids.add(m['message_id'])
            if m['speaker'] not in ('H1','H2','H3') or not isinstance(m['text'],str) or not 1<=len(m['text'])<=5000:
                raise ValueError(sid+': invalid message')
            number(m['time'],'message time',integer=True)
            if m['time']>p['now']:
                raise ValueError(sid+': initial message is from the future')
            lookup[(m['speaker'],m['time'])]=True
        annotations=case['annotations']
        if type(annotations['conflict']) is not bool or not isinstance(annotations['evidence'],list):
            raise ValueError(sid+': invalid annotations')
        if annotations['conflict'] and len(annotations['evidence'])<2:
            raise ValueError(sid+': conflict requires at least two claims')
        for e in annotations['evidence']:
            if set(e)!={'subject','value','source','timestamp','ttl'} or type(e['value']) is not bool:
                raise ValueError(sid+': invalid evidence item')
            if (e['source'],e['timestamp']) not in lookup or not isinstance(e['subject'],str) or not e['subject']:
                raise ValueError(sid+': evidence has no source/time provenance')
            number(e['ttl'],'evidence ttl',integer=True)
            if e['ttl']!=case['initial_ttl']:
                raise ValueError(sid+': initial evidence TTL must equal initial_ttl')
        private=case['private']
        if type(private['actual_verified']) is not bool or not isinstance(private['actual_access'],list) or not set(private['actual_access'])<={'H2','H3'}:
            raise ValueError(sid+': invalid simulator truth/access')
    # This checks structural provenance, not whether a human annotation is correct.
    return copy.deepcopy(data)


def load_builtin():
    return validate(json.loads((ROOT/'data/scenarios.json').read_text(encoding='utf-8')))


def scenario(case):
    p=case['public']
    view=core.PublicState(case['id'],p['subject'],p['now'],p['deadline'],
        tuple(core.Evidence(**e) for e in case['annotations']['evidence']),p['aliases'],
        case['annotations']['conflict'],('H2','H3'),p['probability_knows'],p['available_at'],p['query_cost'],(),False)
    return core.Scenario(view,case['private']['actual_verified'],tuple(case['private']['actual_access']),case['family'])


def evaluation_readiness(data, selected):
    cases=[c for c in data['cases'] if c['id'] in selected]
    review=data.get('review',{})
    reviewers=review.get('reviewers',[])
    if not isinstance(reviewers,list):
        reviewers=[]
    development={c['family'] for c in data['cases'] if c['split']=='development'}
    development|={c['family'] for c in load_builtin()['cases'] if c['split']=='development'}
    overlaps=sorted({c['family'] for c in cases}&development)
    problems=[]
    if any(c['split']!='evaluation' for c in cases):
        problems.append('All selected cases must be explicitly marked evaluation')
    if review.get('independently_reviewed') is not True or len({str(r).strip() for r in reviewers if str(r).strip()})<2:
        problems.append('Two named reviewers and an independent-review attestation are required')
    if overlaps:
        problems.append('Evaluation families overlap development: '+', '.join(overlaps))
    return {'ready':not problems,'problems':problems,'family_overlaps':overlaps,
            'note':'Reviewer statements are user attestations, not externally verified. Textual similarity still requires human review.'}
