/* Browser-global and startup regression checks. Node only; no npm packages/network. */
'use strict';
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');

class Element {
 constructor(doc,id=''){this.doc=doc;this.id=id;this._html='';this._text='';this.value='';this.checked=false;this.dataset={};this.style={};this.children=[];this.classList={toggle(){}};}
 set innerHTML(html){this._html=String(html);this._text='';this.doc.parse(this._html);}
 get innerHTML(){return this._html;}
 set outerHTML(html){this.innerHTML=html;}
 get textContent(){return this._text+this._html.replace(/<[^>]*>/g,'')+this.children.map(c=>typeof c==='string'?c:c.textContent).join('');}
 set textContent(value){this._text=String(value);this._html='';this.children=[];}
 append(...children){this.children.push(...children);}
 replaceChildren(...children){this._text='';this._html='';this.children=children;}
 close(){} showModal(){} click(){} remove(){}
 querySelector(selector){if(selector==='select')return {value:'openai'};if(selector==='input')return {value:'gpt-5-mini-2025-08-07'};return null;}
}
class Document {
 constructor(){this.elements=new Map();this.groups={};for(const id of ['main','global-key','breadcrumb','dialog','dialog-close','dialog-body','toast'])this.elements.set(id,new Element(this,id));}
 getElementById(id){return this.elements.get(id)||null;}
 createElement(){return new Element(this);}
 querySelector(selector){if(selector==='meta[name="workbench-token"]')return {content:'mock-local-token'};return selector.startsWith('#')?this.getElementById(selector.slice(1)):null;}
 querySelectorAll(selector){return this.groups[selector]||[];}
 parse(html){
  for(const match of html.matchAll(/<([a-z][a-z0-9]*)\b([^>]*)>/g)){
   const attrs=match[2],id=attrs.match(/\bid="([^"]+)"/);
   if(id){const el=new Element(this,id[1]);el.value=attrs.match(/\bvalue="([^"]*)"/)?.[1]||'';if(id[1]==='exp-mode')el.value='offline';if(id[1]==='exp-purpose')el.value='development';if(id[1]==='document-select')el.value='README_GR.md';this.elements.set(id[1],el);}
  }
  for(const name of ['case','policy']){
   const inputs=[...html.matchAll(new RegExp('<input\\b[^>]*name="'+name+'"[^>]*>','g'))].map(m=>{const el=new Element(this);el.value=m[0].match(/value="([^"]+)"/)[1];el.checked=/\bchecked\b/.test(m[0]);return el;});
   if(inputs.length){this.groups['input[name='+name+']']=inputs;this.groups['input[name='+name+']:checked']=inputs.filter(e=>e.checked);}
  }
  if(html.includes('class="model-row"'))this.groups['.model-row']=[new Element(this)];
  if(html.includes('data-tab="'))this.groups['[data-tab]']=[...html.matchAll(/data-tab="([^"]+)"/g)].map(m=>{const el=new Element(this);el.dataset.tab=m[1];return el;});
  this.groups['[data-case]']=[...html.matchAll(/data-case="([^"]+)"/g)].map(m=>{const el=new Element(this);el.dataset.case=m[1];return el;});
 }
}

function fixture(){
 const data=JSON.parse(fs.readFileSync(path.join(__dirname,'data/scenarios.json'),'utf8'));
 const state={case_count:data.cases.length,experiments:[],dataset_name:data.name,workspace:'mock-workspace',
   keys:Object.fromEntries(['openai','anthropic','gemini'].map(provider=>[provider,{available:false,variable:provider.toUpperCase()+'_API_KEY'}])),
   policies:{cost_aware:'test',always_reverify:'test',cost_blind:'test',llm:'test'},documents:['README_GR.md']};
 return {data,state};
}
async function boot(hash,fail=false,sourceFile=path.join(__dirname,'web/app.js'),experiment=null,exposeSimulation=false){
 const doc=new Document(),requests=[],listeners={};const {data,state}=fixture();
 const context={document:doc,location:{hash},console,AbortController,structuredClone,Blob,URL,
   setTimeout,clearTimeout,addEventListener(name,fn){listeners[name]=fn;},
   fetch:async url=>{requests.push(url);if(fail)throw Error('mock local server offline');return {ok:true,status:200,json:async()=>url==='/api/state'?state:url==='/api/dataset'?data:experiment&&url.startsWith('/api/experiments/')?experiment:{text:'# Test protocol',name:'README_GR.md'}};}};
 context.window=context;
 // Actual browser Window has non-configurable top, unlike a plain Node global.
 Object.defineProperty(context,'top',{get(){return context;},configurable:false});
 context.status='';
 let source=fs.readFileSync(sourceFile,'utf8');
 if(exposeSimulation)source=source.replace(/\}\)\(\);\s*$/, 'window.__simulationTest={simulationSnapshot,simulationBoard};})();');
 vm.runInNewContext(source,context,{filename:'app.js',timeout:2000});
 await new Promise(resolve=>setImmediate(resolve));
 await new Promise(resolve=>setImmediate(resolve));
 return {doc,requests,context,listeners};
}
async function main(){
 for(const [hash,expected] of [['#home','Από τον διάλογο στην απόφαση'],['#new','Σχεδίασε το επόμενο πείραμα'],
   ['#experiments','Πειράματα & αποτελέσματα'],['#scenarios','Σενάρια & ετικέτες'],
   ['#protocol','Πρωτόκολλο & βιβλιογραφία'],['#settings','Ρυθμίσεις περιβάλλοντος']]){
  const app=await boot(hash);
  assert.ok(app.doc.getElementById('main').textContent.includes(expected),'Route did not render: '+hash);
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
 const scene=detail.doc.getElementById('episode-body');
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
 assert.ok(multi.doc.getElementById('episode-body').textContent.includes('t = 5'));
 multi.doc.getElementById('sim-prev').onclick();
 assert.ok(multi.doc.getElementById('episode-body').textContent.includes('t = 4'));
 assert.ok(multi.doc.getElementById('episode-body').textContent.includes('Χρειάζεται πληροφορία'));
 multi.doc.getElementById('sim-next').onclick();
 assert.ok(multi.doc.getElementById('episode-body').textContent.includes('t = 5'));

 console.log('Frontend regression checks: 6 routes, guarded experiment table/dialogue, read-only globals, startup failure UI, no startup inference, simulation navigation, evidence binding/freshness, no future history, escaped public text. PASS');
}
if(require.main===module)main().catch(error=>{console.error(error);process.exitCode=1;});
module.exports={boot};
