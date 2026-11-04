"""Frozen experiment plans and resumable, auditable coordination episodes."""
import copy
import hashlib
import json
import math
import random
import time
from dataclasses import replace
from pathlib import Path
import catalog
import contracts
import providers
import evidence_guard
import temporal_core as core

ROOT=Path(__file__).resolve().parent
POLICIES={
 'cost_aware':'Selective re-verification with cost-aware source selection',
 'always_reverify':'Mandatory fresh reply; same cost-aware source selector',
 'cost_blind':'Selective re-verification; ignores interruption cost in source selection',
 'llm':'Model selects the next action directly',
 'no_ttl':'Ablation: ignores evidence age',
 'no_binding':'Ablation: ignores object identity',
 'no_conflict':'Ablation: ignores unresolved conflict'}
FINAL={'delivered','escalated','dispatch_blocked','deadline_missed','step_limit','error','interrupted_unknown'}


def code_fingerprint():
    names=('engine.py','contracts.py','catalog.py','providers.py','temporal_core.py',
           'analysis.py','manager.py','storage.py','app.py','evidence_guard.py','research.py')
    files={n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in names}
    return {'files':files,'sha256':contracts.digest(files),'prompt_sha256':contracts.digest(contracts.PROMPT)}


def plan(config,data):
    if not isinstance(config,dict):
        raise ValueError('Experiment configuration must be an object')
    data=catalog.validate(data)
    config=copy.deepcopy(config)
    mode=config.get('mode','offline')
    if mode not in ('offline','live'):
        raise ValueError('Mode must be offline or live')
    evidence_mode=config.get('evidence_mode','explicit_support')
    if evidence_mode not in ('raw','explicit_support'):
        raise ValueError('Evidence mode must be raw or explicit_support')
    ids=config.get('case_ids',[c['id'] for c in data['cases'] if c['split']=='development'])
    if not isinstance(ids,list) or not ids or len(set(ids))!=len(ids) or not set(ids)<={c['id'] for c in data['cases']}:
        raise ValueError('Invalid case selection')
    policies=config.get('policies',['cost_aware','always_reverify','llm'])
    if not isinstance(policies,list) or not policies or len(set(policies))!=len(policies) or not set(policies)<=set(POLICIES):
        raise ValueError('Invalid policy selection')
    repeats=config.get('repeats',1)
    max_steps=config.get('max_steps',8)
    seed=config.get('seed',2027)
    value=config.get('question_value',30)
    max_tokens=config.get('max_output_tokens',3000)
    for v,name,lo,hi in ((repeats,'repeats',1,30),(max_steps,'max_steps',1,40),
                         (seed,'seed',0,2**31-1),(max_tokens,'max_output_tokens',512,8000)):
        if type(v) is not int or not lo<=v<=hi:
            raise ValueError(f'{name} must be an integer between {lo} and {hi}')
    if type(value) not in (float,int) or not math.isfinite(value) or not 0<=value<=1000:
        raise ValueError('question_value must be between 0 and 1000')
    profiles=config.get('models',[{'provider':'openai','model':'gpt-5-mini-2025-08-07'}])
    if mode=='offline':
        profiles=[{'provider':'fixture','model':'scripted_fixture'}]
    if not isinstance(profiles,list) or not 1<=len(profiles)<=6:
        raise ValueError('Select 1–6 model profiles')
    keys=set()
    for profile in profiles:
        if not isinstance(profile,dict) or set(profile)!={'provider','model'}:
            raise ValueError('Model profile requires only provider and model; credentials belong in local environment variables')
        if mode=='live':
            providers.build(profile,{'messages':[{'message_id':'x','speaker':'H1'}],
                                    'task':{'known_subjects':['C1'],'sources':['H2','H3']}})
        key=(profile['provider'],profile['model'])
        if key in keys:
            raise ValueError('Duplicate model profile')
        keys.add(key)
    selected=[c for c in data['cases'] if c['id'] in ids]
    purpose=config.get('purpose','development')
    if purpose not in ('development','evaluation'):
        raise ValueError('Invalid experiment purpose')
    if mode=='live' and purpose=='development' and any(c['split']!='development' for c in selected):
        raise ValueError('Live development requires development cases. Candidate designs remain offline.')
    readiness=catalog.evaluation_readiness(data,ids)
    if purpose=='evaluation' and not readiness['ready']:
        raise ValueError('; '.join(readiness['problems']))
    if len(ids)*len(policies)*len(profiles)*repeats>5000:
        raise ValueError('Plan exceeds 5000 episodes; split into explicitly budgeted studies')
    normalized={'mode':mode,'purpose':purpose,'evidence_mode':evidence_mode,'case_ids':ids,'policies':policies,'models':profiles,
        'repeats':repeats,'max_steps':max_steps,'seed':seed,'question_value':value,'max_output_tokens':max_tokens}
    rng=random.Random(seed)
    pairs=[]
    # Randomize blocks, then conditions within each case/repetition block.
    blocks=[(sid,r) for sid in ids for r in range(1,repeats+1)]
    rng.shuffle(blocks)
    for sid,r in blocks:
        conditions=[(p,m) for p in policies for m in profiles]
        rng.shuffle(conditions)
        for policy,profile in conditions:
            pairs.append({'case':sid,'repetition':r,'policy':policy,'profile':profile,
                          'episode_id':f'e{len(pairs)+1:05d}'})
    return {'config':normalized,'pairs':pairs,'episodes':len(pairs),
        'maximum_calls':len(pairs)*max_steps if mode=='live' else 0,
        'dataset_sha256':contracts.digest(data),'fingerprint':code_fingerprint(),
        'readiness':readiness,'dataset':copy.deepcopy(data)}


def choose(policy,view,model_decision=None,question_value=30):
    if policy=='llm':
        return copy.deepcopy(model_decision)
    if policy=='no_ttl':
        view=replace(view,evidence=tuple(replace(e,ttl=10**9) for e in view.evidence))
    elif policy=='no_binding':
        view=replace(view,evidence=tuple(replace(e,subject=view.subject) for e in view.evidence))
    elif policy=='no_conflict':
        view=replace(view,conflict=False)
    value=core.current_evidence(view)
    if policy!='always_reverify' or view.received_answer:
        if value is not None:
            return {'action':'dispatch' if value else 'escalate','recipient':None}
    possible=[h for h in view.sources if h not in view.attempted and view.probability_knows[h]>0
              and max(view.now,view.available_at[h])+1<=view.deadline]
    if not possible:
        return {'action':'escalate','recipient':None}
    def score(h):
        return question_value*view.probability_knows[h]-max(0,view.available_at[h]-view.now)-(0 if policy=='cost_blind' else view.query_cost[h])
    human=max(possible,key=score)
    return {'action':'wait' if view.available_at[human]>view.now else 'ask','recipient':human}


def reference(scenario):
    view=scenario.public
    feasible=core.current_evidence(view) is True or any(
        max(view.now,view.available_at[h])+1<=view.deadline for h in scenario.actual_access)
    return {'truth':scenario.actual_verified,'completion_feasible_with_oracle_knowledge':bool(feasible),
        'expected_outcome':'delivered' if scenario.actual_verified and feasible else 'escalated',
        'scope':'Simulator reference; feasibility assumes hidden knowledge of source access. Not a clinical ground truth.'}


def summarize(row,scenario,env):
    events=[s['transition'] for s in row['steps'] if 'transition' in s]
    row.update(questions=sum(e['action']=='ask' for e in events),query_cost=sum(e.get('cost',0) for e in events),
        waits=sum(e['action']=='wait' for e in events),
        unsafe_proposals=sum(bool(e.get('truth_violation')) for e in events),
        unsupported_proposals=sum(bool(e.get('unsupported')) for e in events),
        extraction_error_turns=sum(not all(s['extraction_checks'].values()) for s in row['steps'] if 'extraction_checks' in s),
        accepted_extraction_error_turns=sum(not all(s['accepted_extraction_checks'].values()) for s in row['steps'] if 'accepted_extraction_checks' in s),
        rejected_evidence=sum(s.get('rejected_evidence_count',0) for s in row['steps']),
        guard_changed_controller_turns=sum(bool(s.get('guard_changes_controller_action')) for s in row['steps']),
        validation_errors=sum(s.get('status')=='error' for s in row['steps']),
        elapsed_steps=env.view.now-scenario.public.now,
        input_tokens=sum(s.get('usage',{}).get('input_tokens',0) for s in row['steps']),
        output_tokens=sum(s.get('usage',{}).get('output_tokens',0) for s in row['steps']),
        api_seconds=round(sum(s.get('api_seconds',0) for s in row['steps']),3))
    row['reference']=reference(scenario)
    row['expected_outcome_met']=row['status']==row['reference']['expected_outcome'] if row['status'] in FINAL else None
    return row


def replay(case,row):
    scenario=catalog.scenario(case)
    env=core.Environment(scenario)
    messages=contracts.initial_messages(scenario,case)
    # Avoid collisions for imported datasets with non-sequential custom IDs.
    for saved in row['steps']:
        if 'transition' in saved:
            event=contracts.advance(env,messages,saved['selected_action'])
            if event!=saved['transition']:
                raise ValueError('Frozen episode replay mismatch')
    return scenario,env,messages


def episode(case,condition,config,budget,previous=None,call=providers.infer,
            checkpoint=lambda r:None,should_stop=lambda:False):
    row=copy.deepcopy(previous) if previous else dict(condition,family=case['family'],steps=[],api_calls=0,status='running')
    scenario,env,messages=replay(case,row)
    def finish(status):
        row['status']=status
        summarize(row,scenario,env)
        checkpoint(row)
        return row
    if row['steps'] and row['steps'][-1].get('status')=='in_flight':
        return finish('interrupted_unknown')
    if row['steps'] and row['steps'][-1].get('transition',{}).get('result') in ('delivered','escalated','dispatch_blocked','deadline_missed'):
        return finish(row['steps'][-1]['transition']['result'])
    row['status']='running'
    for _ in range(len(row['steps']),config['max_steps']):
        if should_stop():
            return finish('paused_user')
        if config['mode']=='live' and budget['used']>=budget['cap']:
            return finish('paused_budget')
        public=contracts.observation(env.view,messages)
        step={'public_input':public,'status':'in_flight','stage':'provider','started_at':time.time()}
        row['steps'].append(step)
        if config['mode']=='live':
            row['api_calls']+=1
            budget['used']+=1
        checkpoint(row) # reserve and persist call BEFORE it may be billed
        started=time.monotonic()
        try:
            if config['mode']=='live':
                result=call(condition['profile'],public,config['max_output_tokens'])
                raw=result['output']
                step.update({k:v for k,v in result.items() if k!='output'})
            else:
                raw=contracts.fixture(env.view,public)
                step['usage']={}
                step['fixture_warning']='Scripted gold-backed test double, not an LLM result'
            step['api_seconds']=round(time.monotonic()-started,3) if config['mode']=='live' else 0
            step.update(raw_output=raw,stage='output_validation')
            evidence,conflict,decision=contracts.decode(raw,public)
            step['extraction_checks']=contracts.check(env.view,evidence,conflict)
            raw_view=replace(copy.deepcopy(env.view),evidence=evidence,conflict=conflict)
            indexes,audit=evidence_guard.filter_claims(raw['evidence'],public)
            applied=config.get('evidence_mode','raw')=='explicit_support'
            accepted=tuple(e for i,e in enumerate(evidence) if i in indexes) if applied else evidence
            step.update(evidence_guard_applied=applied,evidence_guard_version=evidence_guard.VERSION,
                evidence_audit=audit,accepted_evidence=[copy.deepcopy(x) for i,x in enumerate(raw['evidence']) if not applied or i in indexes],
                rejected_evidence_count=len(evidence)-len(accepted))
            # Semantic scoring below is evaluation only. Selection uses public
            # text plus the admitted model claims, never simulator annotations.
            step['accepted_extraction_checks']=contracts.check(env.view,accepted,conflict)
            predicted=replace(copy.deepcopy(env.view),evidence=accepted,conflict=conflict)
            selected=choose(condition['policy'],predicted,decision,config['question_value'])
            step['raw_controller_action']=choose(condition['policy'],raw_view,decision,config['question_value'])
            step['guard_changes_controller_action']=selected!=step['raw_controller_action']
            step['selected_action']=selected
            step['model_proposal']=decision
            step['annotated_controller_action']=None if condition['policy']=='llm' else choose(condition['policy'],env.view,question_value=config['question_value'])
            step['extraction_changes_controller_action']=None if condition['policy']=='llm' else selected!=step['annotated_controller_action']
            step['stage']='action_execution'
            step['transition']=contracts.advance(env,messages,selected)
            step['status']='completed'
        except (ValueError,KeyError,TypeError,StopIteration) as error:
            # Do not persist arbitrary provider error bodies or headers.
            step.update(status='error',error=str(error),api_seconds=round(time.monotonic()-started,3))
            return finish('error')
        summarize(row,scenario,env)
        checkpoint(row)
        result=step['transition']['result']
        if result in ('delivered','escalated','dispatch_blocked','deadline_missed'):
            return finish(result)
    return finish('step_limit')
