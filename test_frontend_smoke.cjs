/* Browser-global and startup regression checks. Node only; no npm packages/network. */
'use strict';
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');

class Element {
 constructor(doc,id=''){this.doc=doc;this.id=id;this._html='';this._text='';this.value='';this.checked=false;this.disabled=false;this.dataset={};this.style={};this.children=[];this.classList={toggle(){}};}
 set innerHTML(html){this._html=String(html);this._text='';this.doc.parse(this._html);}
 get innerHTML(){return this._html;}
 set outerHTML(html){this.innerHTML=html;}
 get textContent(){return this._text+this._html.replace(/<[^>]*>/g,'')+this.children.map(c=>typeof c==='string'?c:c.textContent).join('');}
 set textContent(value){this._text=String(value);this._html='';this.children=[];}
 append(...children){this.children.push(...children);}
 replaceChildren(...children){this._text='';this._html='';this.children=children;}
 close(){} showModal(){} click(){} remove(){}
 querySelector(selector){if(selector.startsWith('#'))return this.doc.querySelector(selector);if(selector==='select')return {value:'openai'};if(selector==='input')return {value:'gpt-5-mini-2025-08-07'};return null;}
 querySelectorAll(selector){return this.doc.querySelectorAll(selector);}
 getAttribute(name){return this.attributes?.[name]??null;}
}
class Document {
 constructor(){this.elements=new Map();this.groups={};for(const id of ['main','global-key','breadcrumb','dialog','dialog-close','dialog-body','toast'])this.elements.set(id,new Element(this,id));}
 getElementById(id){return this.elements.get(id)||null;}
 createElement(){return new Element(this);}
 querySelector(selector){if(selector==='meta[name="workbench-token"]')return {content:'mock-local-token'};return selector.startsWith('#')?this.getElementById(selector.slice(1)):null;}
 querySelectorAll(selector){const match=selector.match(/^input\[name=([a-z_]+)\]:checked$/);if(match)return (this.groups['input[name='+match[1]+']']||[]).filter(el=>el.checked);return this.groups[selector]||[];}
 parse(html){
  for(const match of html.matchAll(/<([a-z][a-z0-9]*)\b([^>]*)>/g)){
   const attrs=match[2],id=attrs.match(/\bid="([^"]+)"/);
   if(id){const el=new Element(this,id[1]);el.disabled=/\sdisabled(?:\s|=|$)/.test(attrs);el.value=attrs.match(/\bvalue="([^"]*)"/)?.[1]||'';if(id[1]==='exp-mode')el.value='offline';if(id[1]==='exp-purpose')el.value='development';if(id[1]==='document-select')el.value='README_GR.md';this.elements.set(id[1],el);}
  }
  for(const match of html.matchAll(/<textarea\b[^>]*id="([^"]+)"[^>]*>([\s\S]*?)<\/textarea>/g)){const el=this.getElementById(match[1]);if(el)el.value=match[2];}
  for(const name of ['case','policy','study_case','study_policy']){
   const inputs=[...html.matchAll(new RegExp('<input\\b[^>]*name="'+name+'"[^>]*>','g'))].map(m=>{const el=new Element(this);el.value=m[0].match(/value="([^"]+)"/)[1];el.checked=/\bchecked\b/.test(m[0]);return el;});
   if(inputs.length){this.groups['input[name='+name+']']=inputs;this.groups['input[name='+name+']:checked']=inputs.filter(e=>e.checked);}
  }

  for(const name of ['ask','wait','person','inspect']){
   this.groups['[data-'+name+']']=[...html.matchAll(new RegExp('<[a-z][a-z0-9]*\\b[^>]*data-'+name+'="([^"]+)"[^>]*>','g'))].map(m=>{
    const el=new Element(this);el.dataset[name]=m[1];el.attributes=Object.fromEntries([...m[0].matchAll(/([a-z-]+)="([^"]*)"/g)].map(a=>[a[1],a[2]]));return el;
   });
  }

  if(html.includes('class="model-row"'))this.groups['.model-row']=[new Element(this)];
  if(html.includes('data-tab="'))this.groups['[data-tab]']=[...html.matchAll(/data-tab="([^"]+)"/g)].map(m=>{const el=new Element(this);el.dataset.tab=m[1];return el;});
  this.groups['[data-case]']=[...html.matchAll(/data-case="([^"]+)"/g)].map(m=>{const el=new Element(this);el.dataset.case=m[1];return el;});
 }
}

function fixture(){
 const data=JSON.parse(fs.readFileSync(path.join(__dirname,'data/scenarios.json'),'utf8'));
 const state={case_count:data.cases.length,experiments:[],dataset_name:data.name,workspace:'mock-workspace',dataset_sha256:'fixture-source',study:{question:'Research fixture question'},
   keys:Object.fromEntries(['openai','anthropic','gemini'].map(provider=>[provider,{available:false,variable:provider.toUpperCase()+'_API_KEY'}])),
   policies:{cost_aware:'test',always_reverify:'test',cost_blind:'test',llm:'test'},documents:['README_GR.md']};
 return {data,state};
}
async function boot(hash,fail=false,sourceFile=path.join(__dirname,'web/app.js'),experiment=null,exposeSimulation=false,requestHandler=null){
 const doc=new Document(),requests=[],listeners={};const {data,state}=fixture();
 const context={document:doc,location:{_hash:hash,get hash(){return this._hash;},set hash(value){this._hash=value.startsWith('#')?value:'#'+value;}},console,AbortController,structuredClone,Blob,URL,matchMedia:()=>({matches:true}),
   setTimeout,clearTimeout,addEventListener(name,fn){listeners[name]=fn;},
   fetch:async (url,options)=>{requests.push(url);if(requestHandler){const value=await requestHandler(url,options);if(value!==undefined)return {ok:true,status:200,json:async()=>value};}if(fail)throw Error('mock local server offline');return {ok:true,status:200,json:async()=>url==='/api/state'?state:url==='/api/dataset'?data:experiment&&url.startsWith('/api/experiments/')?experiment:{text:'# Test protocol',name:'README_GR.md'}};}};
 context.window=context;
 // Actual browser Window has non-configurable top, unlike a plain Node global.
 Object.defineProperty(context,'top',{get(){return context;},configurable:false});
 context.status='';
 let source=fs.readFileSync(sourceFile,'utf8');
 vm.runInNewContext(fs.readFileSync(path.join(__dirname,'web/research-ui.js'),'utf8'),context,{filename:'research-ui.js',timeout:2000});
 if(exposeSimulation)source=source.replace(/\}\)\(\);\s*$/, 'window.__simulationTest={simulationSnapshot,simulationBoard,InteractiveSim};})();');
 vm.runInNewContext(source,context,{filename:'app.js',timeout:2000});
 await new Promise(resolve=>setImmediate(resolve));
 await new Promise(resolve=>setImmediate(resolve));
 return {doc,requests,context,listeners};
}
async function main(){
 for(const [hash,expected] of [['#study','Μελέτη με LLMs'],['#simulation','Διαδραστικό εργαστήριο'],['#home','Από τον διάλογο στην απόφαση'],['#new','Σχεδίασε το επόμενο πείραμα'],
   ['#experiments','Πειράματα & αποτελέσματα'],['#scenarios','Σενάρια & ετικέτες'],
   ['#protocol','Πρωτόκολλο & βιβλιογραφία'],['#settings','Ρυθμίσεις περιβάλλοντος']]){
  const app=await boot(hash);
  assert.ok(app.doc.getElementById('main').textContent.includes(expected),'Route did not render: '+hash+' | '+app.doc.getElementById('main').textContent+' | '+app.doc.getElementById('toast').textContent);
  assert.equal(typeof app.context.top,'object');assert.equal(app.context.status,'');
  assert.ok(app.requests.every(url=>url.startsWith('/api/')));
 }
 const offline=await boot('#home',true);
 assert.ok(offline.doc.getElementById('main').textContent.includes('Δεν ήταν δυνατή η φόρτωση'));
 assert.ok(offline.doc.getElementById('main').textContent.includes('mock local server offline'));
 const home=await boot('#home');
 assert.deepEqual(home.requests,['/api/state']);
 assert.equal(home.context.pageHeader,undefined);
 assert.equal(home.context.api,undefined);
 const saved=JSON.parse(fs.readFileSync(path.join(__dirname,'regression/recorded_turns_v1.json'),'utf8'));
 const turn=saved.turns.find(t=>t.case==='D09'&&t.policy==='cost_blind');
 const step={public_input:turn.public_input,raw_output:turn.raw_output,extraction_checks:turn.raw_checks,
   accepted_evidence:[],evidence_guard_applied:true,evidence_audit:[{message_id:'m001',accepted:false,reason:'no_explicit_status'}],
   accepted_extraction_checks:{evidence_exact:true,conflict_correct:true,current_status_correct:true},
   selected_action:{action:'ask',recipient:'H2'},transition:{result:'answered'}};
 const {data}=fixture();
 const session={id:'mock-guard',name:'Guarded UI test',status:'paused_budget',dataset_sha256:'abc123',created_at:'test',
   config:{mode:'live',purpose:'development',evidence_mode:'explicit_support'},plan:[{}],dataset:data,batches:[],fingerprint:{},
   runs:[{episode_id:'e00001',case:'D09',policy:'cost_blind',profile:{model:'mock'},repetition:1,
     status:'paused_budget',api_calls:1,questions:1,query_cost:5,steps:[step]}]};
 const summary={complete:false,groups:[{condition:'mock / cost_blind',assigned:1,finished:0,outcome_met:0,questions:1,query_cost:5,
   unsafe_episodes:0,unsupported_episodes:0,extraction_error_turns:1,accepted_extraction_error_turns:0,rejected_evidence:1,errors:0,api_calls:1}],paired_cost:[]};
 const detail=await boot('#experiment/mock-guard',false,undefined,{session,summary});
 assert.ok(detail.doc.getElementById('detail-content').textContent.includes('ΑΠΟΡΡΙΨΕΙΣ ΦΙΛΤΡΟΥ'));
 const dialogue=detail.doc.groups['[data-tab]'].find(x=>x.dataset.tab==='dialogue');
 await dialogue.onclick();
 await new Promise(resolve=>setImmediate(resolve));
 await new Promise(resolve=>setImmediate(resolve));
 assert.ok(detail.doc.getElementById('episode-body'),detail.doc.getElementById('toast').textContent);
 assert.ok(detail.doc.getElementById('episode-body').textContent.includes('Συντηρητικό φίλτρο ενεργό'));
 assert.ok(detail.doc.getElementById('episode-body').textContent.includes('no_explicit_status'));
 assert.ok(detail.doc.getElementById('episode-body').textContent.includes('ask → H2'));
 assert.ok(detail.doc.getElementById('episode-body').textContent.includes('Άγνωστο / χωρίς αποδεκτή επιβεβαίωση'));

 const simulationTab=detail.doc.groups['[data-tab]'].find(x=>x.dataset.tab==='simulation');
 assert.ok(simulationTab,'Simulation tab is missing');
 await simulationTab.onclick();
 await new Promise(resolve=>setImmediate(resolve));
 await new Promise(resolve=>setImmediate(resolve));
 const scene=detail.doc.getElementById('detail-content');
 assert.ok(scene.textContent.includes('Ρομπότ συντονιστής'));
 assert.ok(scene.textContent.includes('Ποιον πρέπει να ρωτήσει το ρομπότ;'));
 assert.ok(scene.textContent.includes('H2'));
 assert.ok(detail.doc.getElementById('sim-prev'));
 assert.ok(detail.doc.getElementById('sim-next'));
 const probe=await boot('#home',false,undefined,null,true);
 const {simulationSnapshot:snapshot,simulationBoard:board}=probe.context.__simulationTest;
 const publicInput={task:{subject:'C1-east',aliases:{'C1-east':'C1'},now:4,deadline:8,sources:['H2','H3'],
   available_at:{H2:0,H3:6},probability_knows:{H2:.8,H3:.6},query_cost:{H2:5,H3:1},attempted:[]},
   messages:[{message_id:'m1',speaker:'H2',text:'Completed.',time:1,valid_for:2},
             {message_id:'m2',speaker:'H3',text:'Completed.',time:3,valid_for:2}]};
 const claims=[{message_id:'m1',subject:'C1',value:false},{message_id:'m2',subject:'C1',value:true}];
 const currentStep={accepted_evidence:claims,raw_output:{conflict:false},selected_action:{action:'ask',recipient:'H2'}};
 assert.equal(snapshot(publicInput,currentStep).value,true,'Aliases and freshness must bind to public message metadata');
 assert.equal(snapshot(publicInput,currentStep).current.length,1);
 assert.equal(snapshot(publicInput,currentStep).expired,1);
 assert.equal(snapshot(publicInput,{...currentStep,raw_output:{conflict:true}}).value,null);
 assert.equal(snapshot(publicInput,{...currentStep,accepted_evidence:[{message_id:'m2',subject:'C2',value:true}]}).value,null);
 assert.equal(snapshot(publicInput,{...currentStep,accepted_evidence:[claims[0]]}).value,null);
 assert.equal(snapshot({...publicInput,task:{...publicInput.task,now:3}},{...currentStep,accepted_evidence:[claims[0]]}).value,false,'TTL boundary is inclusive');
 assert.equal(snapshot(publicInput,{raw_output:{evidence:{invalid:true}}}).value,null,'Invalid unfinished extraction is not evidence');
 assert.equal(snapshot(publicInput,{raw_output:{evidence:[null,{},false,{message_id:'m2',subject:'C1',value:'true'}]}}).value,null,'Rejected malformed claims must not crash simulation');
 const unknown=board(publicInput,{...currentStep,accepted_evidence:[]},{policy:'cost_aware',steps:[]},0);
 assert.ok(unknown.includes('Χρειάζεται πληροφορία'));
 assert.ok(unknown.includes('Διαθέσιμος στο t=6'));
 assert.ok(!unknown.includes('actual_verified'));
 const malicious=structuredClone(publicInput);
 malicious.task.subject='<img src=x onerror=alert(1)>';
 malicious.messages[0].text='<script>alert(1)</script>';
 const escaped=board(malicious,currentStep,{policy:'cost_aware',steps:[]},0);
 assert.ok(!escaped.includes('<script>'));
 assert.ok(!escaped.includes('<img src=x'));
 assert.ok(escaped.includes('&lt;script&gt;'));
 const future={...step,selected_action:{action:'ask',recipient:'FUTURE_PERSON'},transition:{result:'future'}};
 const past={...step,selected_action:{action:'ask',recipient:'H3'},transition:{result:'answered'}};
 const history=board(publicInput,currentStep,{policy:'cost_aware',steps:[past,currentStep,future]},1);
 assert.ok(!history.includes('FUTURE_PERSON'),'Recorded future actions must not leak into an earlier snapshot');
 // Navigate two recorded snapshots: the team status must change with the selected turn.
 const multiSession=structuredClone(session);
 multiSession.runs[0].steps=[{...step,public_input:publicInput,accepted_evidence:[]},
                           {...currentStep,public_input:{...publicInput,task:{...publicInput.task,now:5}}}];
 const multi=await boot('#experiment/mock-guard',false,undefined,{session:multiSession,summary});
 await multi.doc.groups['[data-tab]'].find(x=>x.dataset.tab==='simulation').onclick();
 await new Promise(resolve=>setImmediate(resolve));
 await new Promise(resolve=>setImmediate(resolve));
 assert.ok(multi.doc.getElementById('detail-content').textContent.includes('t = 4'));
 multi.doc.getElementById('sim-next').onclick();
 assert.ok(multi.doc.getElementById('detail-content').textContent.includes('t = 5'));
 multi.doc.getElementById('sim-prev').onclick();
 assert.ok(multi.doc.getElementById('detail-content').textContent.includes('t = 4'));
 assert.ok(multi.doc.getElementById('detail-content').textContent.includes('Άγνωστη / μη ισχύουσα επιβεβαίωση'));
 multi.doc.getElementById('sim-next').onclick();
 assert.ok(multi.doc.getElementById('detail-content').textContent.includes('t = 5'));


 // The interactive lab runs no provider requests and never changes recorded experiments.
 const lab=await boot('#simulation',false,undefined,null,true);
 const initialRequests=[...lab.requests];
 assert.deepEqual(initialRequests,['/api/state','/api/dataset']);
 assert.ok(lab.doc.getElementById('interactive-lab').textContent.includes('ΕΚΠΑΙΔΕΥΤΙΚΟ SANDBOX'));
 assert.ok(lab.doc.groups['[data-ask]'].some(x=>x.dataset.ask==='H3'));
 lab.doc.getElementById('lab-follow').onclick();
 await new Promise(resolve=>setTimeout(resolve,10));
 assert.ok(lab.doc.getElementById('interactive-lab').textContent.includes('Λήφθηκε νέα επιβεβαίωση'));
 assert.deepEqual(lab.requests,initialRequests,'Sandbox actions must not call an API');
 lab.doc.getElementById('lab-dispatch').onclick();
 await new Promise(resolve=>setTimeout(resolve,10));
 assert.ok(lab.doc.getElementById('interactive-lab').textContent.includes('Ολοκληρώθηκε η παράδοση'));
 lab.doc.getElementById('lab-reset').onclick();
 lab.doc.getElementById('lab-compare').onclick();
 assert.ok(lab.doc.getElementById('interactive-lab').textContent.includes('Εκπαιδευτική σύγκριση'));

 lab.doc.getElementById('lab-policy').value='cost_blind';
 lab.doc.getElementById('lab-policy').onchange();
 assert.ok(lab.doc.getElementById('interactive-lab').textContent.includes('Δοκίμασε την πρόταση: Ερώτηση → H2'));
 lab.doc.getElementById('lab-cost-h2').value='1';
 lab.doc.getElementById('lab-cost-h3').value='8';
 lab.doc.getElementById('lab-cost-apply').onclick();
 assert.ok(lab.doc.getElementById('interactive-lab').textContent.includes('Δική σου παραλλαγή κόστους'));
 lab.doc.getElementById('lab-policy').value='cost_aware';
 lab.doc.getElementById('lab-policy').onchange();
 lab.doc.getElementById('lab-follow').onclick();
 lab.doc.getElementById('lab-reset').onclick();
 await new Promise(resolve=>setTimeout(resolve,10));
 assert.ok(!lab.doc.getElementById('interactive-lab').textContent.includes('Λήφθηκε νέα επιβεβαίωση'),'Reset cancels an in-flight visual timer');
 lab.doc.groups['[data-person]'].find(x=>x.dataset.person==='H3').onclick();
 await new Promise(resolve=>setTimeout(resolve,10));
 assert.ok(lab.doc.getElementById('interactive-lab').textContent.includes('Λήφθηκε νέα επιβεβαίωση'),'Clicking the source figure must request its programmed answer');
 assert.deepEqual(lab.requests,initialRequests);

 const model=lab.context.__simulationTest.InteractiveSim;
 const c=fixture().data.cases.find(c=>c.id==='D09'),unchanged=JSON.stringify(c),one=new model.Sandbox(c);
 assert.equal(one.snapshot().value,null);
 const extraPublic=structuredClone(c);extraPublic.public.actual_verified='PRIVATE_EXTRA';
 assert.ok(!JSON.stringify(new model.Sandbox(extraPublic).snapshot()).includes('PRIVATE_EXTRA'),'Only allowed public task fields enter the view');
 assert.ok(!JSON.stringify(one.snapshot()).includes('actual_verified'),'Private truth is not exposed in public sandbox snapshots');
 assert.ok(!JSON.stringify(one.snapshot()).includes('actual_access'));
 assert.equal(one.recommendation('cost_aware').recipient,'H3');
 assert.equal(one.recommendation('cost_blind').recipient,'H2');
 one.apply({action:'ask',recipient:'H3'});
 assert.equal(one.snapshot().cost,1);
 assert.equal(one.snapshot().value,true);
 one.apply({action:'dispatch',recipient:null});
 assert.equal(one.snapshot().last.result,'delivered');
 assert.throws(()=>one.apply({action:'dispatch',recipient:null}),/ολοκληρώθηκε/);
 assert.equal(JSON.stringify(c),unchanged,'Training must not mutate dataset');
 const variant=new model.Sandbox(c,{H2:1,H3:7});
 assert.equal(variant.recommendation('cost_aware').recipient,'H2');
 assert.equal(variant.recommendation('cost_blind').recipient,'H2');
 assert.throws(()=>new model.Sandbox(c,{H2:NaN,H3:1}),/κόστος/);
 const blockedModel=new model.Sandbox(fixture().data.cases.find(c=>c.id==='D01'));
 blockedModel.apply({action:'dispatch',recipient:null});
 assert.equal(blockedModel.snapshot().last.result,'dispatch_blocked');
 const unsafeScene=model.scene(blockedModel.snapshot());
 assert.ok(!unsafeScene.includes('class="lab-mobile-robot is-delivered'),'Blocked attempts must not animate a delivery');
 const knownless=new model.Sandbox(fixture().data.cases.find(c=>c.id==='D07'));
 knownless.apply({action:'ask',recipient:'H2'});
 assert.equal(knownless.snapshot().last.answer,'unknown');
 assert.equal(knownless.snapshot().publicInput.task.probability_knows.H2,0);
 assert.throws(()=>knownless.apply({action:'ask',recipient:'H2'}),/ήδη/);
 // Before/after replay reveals a saved answer only in the post-action phase.
 const replayRow={steps:[{public_input:publicInput,accepted_evidence:[],raw_output:{conflict:false},
  selected_action:{action:'ask',recipient:'H2'},transition:{action:'ask',recipient:'H2',time:4,result:'answered',answer:true,cost:5,actual_verified:'PRIVATE_MARKER'}}]};
 const frozen=JSON.stringify(replayRow),before=model.replaySnapshot(replayRow,0),after=model.replaySnapshot(replayRow,1);
 assert.equal(before.value,null);assert.equal(before.last,null);assert.equal(before.cost,0);
 assert.ok(!JSON.stringify(before).includes('PRIVATE_MARKER'));
 assert.ok(!JSON.stringify(before).includes('"answer":true'),'Before-action frames must not contain the future answer');
 assert.equal(after.value,true);assert.equal(after.cost,5);assert.equal(after.publicInput.task.now,5);
 assert.ok(!JSON.stringify(after.last).includes('PRIVATE_MARKER'));
 assert.ok(!JSON.stringify(after.history).includes('PRIVATE_MARKER'));
 assert.equal(JSON.stringify(replayRow),frozen);
 const rejectedRow={steps:[{public_input:publicInput,raw_output:{evidence:[{message_id:'m2',subject:'C1',value:true}],conflict:false},status:'error',error:'Invalid output'}]};
 assert.equal(model.replaySnapshot(rejectedRow,0).value,null,'A rejected model extraction is not an accepted status');
 const timerTest=await boot('#experiment/mock-guard',false,undefined,{session:multiSession,summary});
 await timerTest.doc.groups['[data-tab]'].find(x=>x.dataset.tab==='simulation').onclick();
 await new Promise(resolve=>setImmediate(resolve));
 await new Promise(resolve=>setImmediate(resolve));
 timerTest.doc.getElementById('sim-play').onclick();
 assert.ok(timerTest.doc.getElementById('sim-play'));
 timerTest.context.location.hash='#home';
 await timerTest.listeners.hashchange();


 // Guided study previews and draft creation never send a start request.
 const studyPosts=[];
 const studyHandler=async(url,options)=>{
  if(url==='/api/study/plan'){
   const body=JSON.parse(options.body);studyPosts.push({url,body});
   return {episodes:body.config.case_ids.length*body.config.policies.length,initial_call_cap:body.initial_call_cap,
    maximum_calls:64,config:body.config,cases:fixture().data.cases.filter(c=>body.config.case_ids.includes(c.id)),
    study_design:{cost_overrides:body.cost_overrides},warnings:['Development, not independent evaluation'],plan_sha256:'reviewed-study-plan'};
  }
  if(url==='/api/study/create'){studyPosts.push({url,body:JSON.parse(options.body)});return {id:'b'.repeat(32),status:'ready'};}
 };
 const wizard=await boot('#study',false,undefined,null,false,studyHandler);
 assert.ok(wizard.doc.getElementById('study-create').disabled);
 await wizard.doc.getElementById('study-form').onsubmit({preventDefault(){}});
 assert.equal(studyPosts.length,1);
 assert.equal(studyPosts[0].body.config.mode,'live');
 assert.deepEqual(studyPosts[0].body.config.case_ids,['D03','D05']);
 assert.ok(!wizard.doc.getElementById('study-create').disabled);
 wizard.doc.getElementById('study-repeats').value='2';
 wizard.doc.getElementById('study-form').oninput();
 assert.ok(wizard.doc.getElementById('study-create').disabled);
 await wizard.doc.getElementById('study-create').onclick();
 assert.equal(studyPosts.length,1,'Changing the form invalidates a reviewed plan');
 await wizard.doc.getElementById('study-form').onsubmit({preventDefault(){}});
 await wizard.doc.getElementById('study-create').onclick();
 assert.equal(studyPosts.at(-1).body.expected_plan_sha256,'reviewed-study-plan');
 assert.equal(wizard.context.location.hash,'#experiment/'+'b'.repeat(32));
 assert.ok(!wizard.requests.some(url=>url.endsWith('/start')),'Study creation must not start billable calls');
 const bridge=await boot('#simulation',false,undefined,null,false,studyHandler);
 bridge.doc.getElementById('lab-cost-h2').value='2';bridge.doc.getElementById('lab-cost-h3').value='9';
 bridge.doc.getElementById('lab-cost-apply').onclick();
 bridge.doc.getElementById('lab-research').onclick();
 assert.equal(bridge.context.location.hash,'#study');
 await bridge.listeners.hashchange();
 await bridge.doc.getElementById('study-form').onsubmit({preventDefault(){}});
 assert.deepEqual(studyPosts.at(-1).body.config.case_ids,['D09']);
 assert.deepEqual(studyPosts.at(-1).body.cost_overrides,{D09:{H2:2,H3:9}});
 assert.ok(!bridge.requests.some(url=>url.endsWith('/start')));
 const researchReport={unique_case_ids:1,family_labels:1,repetitions_per_condition:1,study_design:null,
  warnings:['<script>unsafe report text</script>'],conditions:[{...summary.groups[0],not_started:0,technical_failures:0,limit_failures:0}],
  decision_audit:{scored_turns:1,skipped_turns:0,unique_public_inputs:1,contrasts:[{policies:['cost_aware','cost_blind'],different_actions:1,observations:1}],
    observations:[{episode_id:'e00001',case:'D09',source_policy:'cost_blind',profile:{model:'mock'},step:1,admitted_status:null,
      actions:{cost_aware:{action:'ask',recipient:'H3'},always_reverify:{action:'ask',recipient:'H3'},cost_blind:{action:'ask',recipient:'H2'},llm_proposal:{action:'ask',recipient:'H3'}},
      immediate_query_cost:{cost_aware:1,always_reverify:1,cost_blind:5,llm_proposal:1}}],notes:[],skipped:[]},remaining_research_steps:['Independent review']};
 const researchView=await boot('#experiment/mock-guard',false,undefined,{session,summary},false,async url=>url.endsWith('/research')?researchReport:undefined);
 await researchView.doc.groups['[data-tab]'].find(x=>x.dataset.tab==='research').onclick();
 await new Promise(resolve=>setImmediate(resolve));await new Promise(resolve=>setImmediate(resolve));
 assert.ok(researchView.doc.getElementById('detail-content').textContent.includes('Τι αλλάζει αν όλοι δουν την ίδια πληροφορία;'));
 assert.ok(!researchView.doc.getElementById('detail-content').innerHTML.includes('<script>unsafe'));
 assert.ok(researchView.doc.getElementById('audit-table').textContent.includes('ask → H3'));

 console.log('Frontend regression checks: 8 routes, guarded experiment table/dialogue, read-only globals, startup failure UI, no startup inference, simulation navigation, evidence binding/freshness, no future history, escaped public text, manual sandbox, structured policy variants, two-phase replay, timer disposal, sandbox-to-study transfer, frozen review invalidation, no implicit start and read-only research reports. PASS');
}
if(require.main===module)main().catch(error=>{console.error(error);process.exitCode=1;});
module.exports={boot};
