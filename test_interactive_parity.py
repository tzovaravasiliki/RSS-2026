"""Cross-language contract for the isolated browser training simulator.
Uses synthetic fixtures only. Node is optional; no network, provider, or disk writes.
"""
from __future__ import annotations
import copy
import json
from pathlib import Path
import random
import shutil
import subprocess
import unittest
import catalog
import contracts
import engine
import temporal_core as core

ROOT=Path(__file__).resolve().parent
POLICIES=('cost_aware','always_reverify','cost_blind')
TASK_KEYS=('subject','now','deadline','aliases','probability_knows','available_at','query_cost','attempted','received_answer')

def expected_trace(case,policy=None,seed=0):
    scenario=catalog.scenario(case)
    env=core.Environment(scenario)
    messages=contracts.initial_messages(scenario,case)
    history=[]
    rng=random.Random(seed)
    def snapshot(done=False):
        view=env.view
        task={k:copy.deepcopy(getattr(view,k)) for k in TASK_KEYS}
        task['attempted']=list(task['attempted'])
        return {'task':task,'messages':copy.deepcopy(messages),'value':core.current_evidence(view),
                'questions':sum(e['action']=='ask' for e in history),
                'cost':sum(e.get('cost',0) for e in history),
                'last':copy.deepcopy(history[-1]) if history else None,'done':done}
    frames=[snapshot()]
    actions=[]
    limit=8 if policy else 4
    for _ in range(limit):
        view=env.view
        if policy:
            action=engine.choose(policy,view)
        else:
            choices=[{'action':'dispatch','recipient':None},{'action':'escalate','recipient':None}]
            if view.now+1<=view.deadline:
                for human in view.sources:
                    if human in view.attempted:continue
                    choices.append({'action':'wait','recipient':human})
                    if view.available_at[human]<=view.now:choices.append({'action':'ask','recipient':human})
            action=rng.choice(choices)
        event=contracts.advance(env,messages,action)
        event={k:v for k,v in event.items() if k!='actual_verified'}
        actions.append(action);history.append(event)
        done=event['result'] in ('delivered','escalated','dispatch_blocked','deadline_missed')
        if len(history)>=8 and not done:event['limit_reached']=True;done=True
        frames.append(snapshot(done))
        if done:break
    return {'case':case,'policy':policy,'actions':actions,'frames':frames}

class InteractiveParityTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('node'),'Node is optional; browser training parity skipped')
    def test_browser_training_matches_backend_rollouts_and_manual_paths(self):
        cases=[c for c in catalog.load_builtin()['cases'] if c['split']=='development']
        traces=[expected_trace(c,p) for c in cases for p in POLICIES]
        traces.extend(expected_trace(c,seed=seed) for c in cases for seed in range(4))
        source=(ROOT/'web/app.js').read_text(encoding='utf-8')
        begin=source.index('/* Interactive lab:')
        end=source.index('function simulationSnapshot(',begin)
        helper_end=source.index('function simulationBoard(',end)
        module=source[begin:end]+source[end:helper_end]
        runner=module+r'''
const assert=require('node:assert/strict');
let input='';
process.stdin.setEncoding('utf8');
process.stdin.on('data',chunk=>input+=chunk);
process.stdin.on('end',()=>{
 const traces=JSON.parse(input);let transitions=0;
 function check(model,expected,label){
  const actual=model.snapshot(),task={};
  for(const key of Object.keys(expected.task))task[key]=actual.publicInput.task[key];
  assert.deepEqual(JSON.parse(JSON.stringify(task)),expected.task,label+' public task');
  assert.deepEqual(actual.publicInput.messages,expected.messages,label+' messages');
  for(const key of ['value','questions','cost','last','done'])assert.deepEqual(actual[key],expected[key],label+' '+key);
 }
 for(const trace of traces){
  const frozen=JSON.stringify(trace.case),model=new InteractiveSim.Sandbox(trace.case);
  check(model,trace.frames[0],trace.case.id+' initial');
  for(let i=0;i<trace.actions.length;i++){
   if(trace.policy)assert.deepEqual(model.recommendation(trace.policy),trace.actions[i],trace.case.id+' policy');
   model.apply(trace.actions[i]);transitions++;
   check(model,trace.frames[i+1],trace.case.id+' step '+i);
  }
  assert.equal(JSON.stringify(trace.case),frozen,'Original dataset must remain unchanged');
 }
 console.log('Interactive parity PASS: '+traces.length+' synthetic traces, '+transitions+' transitions; all three policies and manual choices.');
});
'''
        proc=subprocess.run(['node','-e',runner],input=json.dumps(traces,ensure_ascii=False),
                            text=True,capture_output=True,timeout=15)
        self.assertEqual(proc.returncode,0,proc.stdout+proc.stderr)
        self.assertIn('Interactive parity PASS',proc.stdout)
        print(proc.stdout.strip())

if __name__=='__main__':
    unittest.main()
