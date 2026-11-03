(function () {
'use strict';
const $=s=>document.querySelector(s), $$=s=>Array.from(document.querySelectorAll(s));
const token=$('meta[name="workbench-token"]').content;
const E=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let state=null, dataset=null, selectedScenario=null, selectedEpisode=null, detailTab='overview', poll=null, detailCache=null;
let interactiveDispose=null,pendingLabCase=null;
function disposeInteractive(){if(interactiveDispose){interactiveDispose();interactiveDispose=null;}}
const routes={simulation:'Διαδραστικό εργαστήριο',home:'Επισκόπηση',new:'Νέο πείραμα',experiments:'Πειράματα & αποτελέσματα',scenarios:'Σενάρια & ετικέτες',protocol:'Πρωτόκολλο & βιβλιογραφία',settings:'Ρυθμίσεις'};
const statusNames={ready:'Έτοιμο',running:'Σε εκτέλεση',completed:'Οι προσπάθειες ολοκληρώθηκαν',paused_budget:'Όριο κλήσεων',paused_user:'Σε παύση',paused_restart:'Συνέχεια μετά επανεκκίνηση',paused_provider_error:'Σφάλμα παρόχου',paused_internal_error:'Χρειάζεται έλεγχο',delivered:'Παράδοση',escalated:'Κλιμάκωση',dispatch_blocked:'Μπλοκαρισμένη πρόταση',error:'Σφάλμα',interrupted_unknown:'Άγνωστη έκβαση κλήσης',step_limit:'Όριο αποφάσεων',deadline_missed:'Εκτός προθεσμίας'};
const policyLabels={cost_aware:'Επιλεκτική επανεπιβεβαίωση',always_reverify:'Υποχρεωτική επανεπιβεβαίωση',cost_blind:'Χωρίς κόστος πηγής',llm:'Απόφαση LLM',no_ttl:'Ablation: χωρίς χρονική ισχύ',no_binding:'Ablation: χωρίς ταυτότητα',no_conflict:'Ablation: χωρίς αντιφάσεις'};
function pill(text,kind='muted'){return `<span class="pill ${kind}">${E(text)}</span>`;}
function status(s){return pill(statusNames[s]||s,s==='completed'?'muted':s==='delivered'?'good':['error','dispatch_blocked','paused_provider_error','paused_internal_error','interrupted_unknown'].includes(s)?'bad':s==='running'?'live':'warn');}
function modePill(mode){return mode==='live'?pill('LIVE API','live'):pill('OFFLINE · 0 API CALLS','good');}
function toast(message,error=false){const el=$('#toast');el.textContent=message;el.className=error?'error':'';el.style.display='block';clearTimeout(toast.timer);toast.timer=setTimeout(()=>el.style.display='none',6500);}
async function api(url,body){
 const controller=new AbortController();
 const timer=setTimeout(()=>controller.abort(),15000);
 try {
  const options=body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json','X-Workbench-Token':token},body:JSON.stringify(body)};
  const response=await fetch(url,{...options,signal:controller.signal});
  let data;
  try {data=await response.json();} catch {throw Error('Ο τοπικός server επέστρεψε μη έγκυρη απόκριση. Κλείσε και άνοιξε την εφαρμογή από START_WINDOWS.bat.');}
  if(!response.ok)throw Error(data.error||`HTTP ${response.status}`);
  return data;
 } catch(error) {
  if(error.name==='AbortError')throw Error('Ο τοπικός server δεν απάντησε εντός 15 δευτερολέπτων. Έλεγξε ότι το παράθυρο Python παραμένει ανοιχτό.');
  throw error;
 } finally {clearTimeout(timer);}
}
function safe(fn){return async(...args)=>{try{await fn(...args);}catch(e){toast(e.message,true);}};}
function pageHeader(title,description,action=''){return `<div class="page-top"><div><div class="eyebrow">RSS2027 / TEAM COORDINATION RESEARCH</div><h1>${title}</h1><p class="subtitle">${description}</p></div>${action}</div>`;}
function download(name,text,type='application/json'){const url=URL.createObjectURL(new Blob([text],{type}));const a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
async function loadState(){state=await api('/api/state');$('#global-key').outerHTML=`<span id="global-key" class="pill ${state.keys.openai.available?'good':'muted'}">${state.keys.openai.available?'● OpenAI key διαθέσιμο':'○ OpenAI key δεν έχει οριστεί'}</span>`;}
function navigate(hash){location.hash=hash;}
function latestTable(items){if(!items.length)return `<div class="empty"><b>Ο χώρος των πειραμάτων σου είναι έτοιμος.</b>Ξεκίνα με μία offline εκτέλεση, χωρίς API ή χρέωση.</div>`;return `<div class="table-scroll"><table><thead><tr><th>ΠΕΙΡΑΜΑ</th><th>ΚΑΤΑΣΤΑΣΗ</th><th>ΠΡΟΟΔΟΣ</th><th>ΚΛΗΣΕΙΣ</th></tr></thead><tbody>${items.map(x=>`<tr class="clickable" data-open="${x.id}"><td>${E(x.name)}<small class="cell-sub">${E(x.config.mode)} · ${E(x.created_at.slice(0,10))}</small></td><td>${status(x.status)}</td><td>${x.finished}/${x.assigned}</td><td>${x.calls}</td></tr>`).join('')}</tbody></table></div>`;}
function openBindings(){$$('[data-open]').forEach(el=>el.onclick=()=>navigate('experiment/'+el.dataset.open));}
async function home(){const finished=state.experiments.reduce((s,x)=>s+x.finished,0),calls=state.experiments.reduce((s,x)=>s+x.calls,0);$('#main').innerHTML=pageHeader('Από τον διάλογο στην απόφαση.','Παρακολούθησε πώς ένας ρομποτικός συντονιστής επιλέγει πότε και ποιον άνθρωπο να ρωτήσει, πριν αποφασίσει για τη μεταφορά εξοπλισμού.',`<a class="btn primary" href="#simulation">▶ Δοκίμασε τον συντονισμό</a>`)+`
<div class="stats"><div class="stat"><div class="label">Σενάρια στο περιβάλλον</div><strong>${state.case_count}</strong><small>Ανάπτυξη & υποψήφια σχέδια</small></div><div class="stat"><div class="label">Πειράματα</div><strong>${state.experiments.length}</strong><small>Με παγωμένες ρυθμίσεις</small></div><div class="stat"><div class="label">Ολοκληρωμένες προσπάθειες</div><strong>${finished}</strong><small>Οι τεχνικές αποτυχίες καταγράφονται</small></div><div class="stat"><div class="label">Κλήσεις API</div><strong>${calls}</strong><small>Συντηρητική καταμέτρηση προσπαθειών</small></div></div>
<div class="grid"><div><section class="card"><div class="card-top"><h2>Τι ερευνά η προσομοίωση</h2>${pill('CLOSED-LOOP','good')}</div><p class="subtitle">Διάλογος H1–H3, κατάσταση ελέγχου ενός καροτσιού και επιλογή πηγής με διαφορετική διαθεσιμότητα και κόστος διακοπής.</p><div class="flow"><div class="flow-node"><b>◌</b>Διάλογος ομάδας</div><span class="flow-arrow">›</span><div class="flow-node"><b>◇</b>Κατάσταση & αβεβαιότητα</div><span class="flow-arrow">›</span><div class="flow-node"><b>↗</b>Ερώτηση σε μέλος</div><span class="flow-arrow">›</span><div class="flow-node"><b>✓</b>Ενημέρωση & απόφαση</div></div><div class="note">Συνθετικό περιβάλλον: άνθρωποι με προγραμματισμένες απαντήσεις, αφηρημένο κόστος και προθεσμίες.</div></section><section class="card"><div class="card-top"><h2>Πρόσφατα πειράματα</h2><a href="#experiments">Προβολή όλων ↗</a></div>${latestTable(state.experiments.slice(0,4))}</section></div>
<div><section class="card"><div class="card-top"><h3>Μπες στον ρόλο του συντονιστή</h3>${pill('ΧΩΡΙΣ ΧΡΕΩΣΗ','good')}</div><ol class="step-list"><li>Επίλεξε ένα σενάριο.<small>Διαθεσιμότητα, πληροφορία και προθεσμία.</small></li><li>Ρώτησε ένα μέλος της ομάδας.<small>Δες την απάντηση και το κόστος διακοπής.</small></li><li>Σύγκρινε διαφορετικές επιλογές.<small>Εκπαιδευτική δοκιμή, χωρίς κλήσεις AI.</small></li></ol><button id="demo" class="btn secondary" style="width:100%;margin-top:20px">▶ Άνοιγμα διαδραστικού εργαστηρίου</button></section><section class="card"><div class="card-top"><h3>Πάροχοι μοντέλων</h3><a href="#settings">Ρυθμίσεις</a></div>${providerRows()}<div class="field-help">Δεν αποστέλλονται κλειδιά στη σελίδα. Κάθε πάροχος απαιτεί δικό του API key.</div></section></div></div>`;openBindings();$('#demo').onclick=()=>navigate('simulation');}
function providerRows(){return Object.entries(state.keys).map(([key,v])=>`<div class="provider"><span class="provider-icon">${key==='openai'?'O':key==='anthropic'?'C':'G'}</span><div class="provider-text">${key==='openai'?'OpenAI':key==='anthropic'?'Claude / Anthropic':'Google Gemini'}<small>${E(v.variable)}</small></div>${pill(v.available?'Key διαθέσιμο':'Δεν έχει οριστεί',v.available?'good':'muted')}</div>`).join('');}
async function experimentList(){$('#main').innerHTML=pageHeader('Πειράματα & αποτελέσματα','Οι ολοκληρωμένες προσπάθειες παραμένουν αποθηκευμένες. Μπορείς να συνεχίσεις πειράματα σε παύση.',`<a class="btn primary" href="#new">＋ Νέο πείραμα</a>`)+(state.experiments.length?state.experiments.map(x=>`<section class="card experiment-card"><div style="flex:1;min-width:200px"><h3>${E(x.name)}</h3><div class="actions">${modePill(x.config.mode)}${status(x.status)}<span class="field-help">${x.finished}/${x.assigned} προσπάθειες · ${x.calls} κλήσεις</span></div><div class="progress"><span style="width:${x.finished/x.assigned*100}%"></span></div></div><a class="btn" href="#experiment/${x.id}">Άνοιγμα πειράματος ↗</a></section>`).join(''):`<section class="card">${latestTable([])}</section>`);}
function modelRow(provider='openai',model='gpt-5-mini-2025-08-07'){return `<div class="model-row"><select aria-label="Πάροχος"><option value="openai" ${provider==='openai'?'selected':''}>OpenAI</option><option value="anthropic" ${provider==='anthropic'?'selected':''}>Anthropic</option><option value="gemini" ${provider==='gemini'?'selected':''}>Gemini</option></select><input aria-label="Model ID" value="${E(model)}" placeholder="Exact API model ID" required><button type="button" class="icon-button remove-model" aria-label="Αφαίρεση μοντέλου">×</button></div>`;}
async function newExperiment(){dataset=await api('/api/dataset');const cases=dataset.cases;$('#main').innerHTML=pageHeader('Σχεδίασε το επόμενο πείραμα.','Επίλεξε συνθήκες, όρισε τον προϋπολογισμό και διατήρησε σταθερό το πρωτόκολλο.')+`<div class="grid"><form id="experiment-form"><section class="card"><div class="card-top"><h2>01 / Βασικές ρυθμίσεις</h2>${pill('OFFLINE BY DEFAULT','good')}</div><div class="form-grid"><div><label for="exp-name">Όνομα πειράματος</label><input id="exp-name" value="RSS2027 v1.1 — Development experiment" maxlength="120"></div><div><label for="exp-mode">Τρόπος εκτέλεσης</label><select id="exp-mode"><option value="offline">Offline fixture — χωρίς API</option><option value="live">Live API — με χρέωση παρόχου</option></select></div><div><label for="exp-evidence">Έλεγχος επιβεβαιώσεων</label><select id="exp-evidence"><option value="explicit_support">Συντηρητικό φίλτρο ρητών δηλώσεων</option><option value="raw">Αρχική εξαγωγή — χωρίς φίλτρο</option></select><div class="field-help">Το φίλτρο αναγνωρίζει συγκεκριμένες ελληνικές/αγγλικές διατυπώσεις. Οι αρχικές έξοδοι και τα λάθη παραμένουν καταγεγραμμένα.</div></div><div><label for="exp-purpose">Χρήση δεδομένων</label><select id="exp-purpose"><option value="development">Ανάπτυξη / debugging</option><option value="evaluation">Ανεξάρτητη αξιολόγηση</option></select></div><div><label for="exp-repeat">Επαναλήψεις ανά συνθήκη</label><input id="exp-repeat" type="number" min="1" max="30" value="1"></div></div></section>
<section class="card"><div class="card-top"><h2>02 / Σενάρια</h2><div class="actions"><button id="select-dev" class="btn" type="button">Development</button><button id="select-none" class="btn" type="button">Καθαρισμός</button></div></div><div class="checks">${cases.map(c=>`<label class="check"><input type="checkbox" name="case" value="${E(c.id)}" ${c.split==='development'?'checked':''}><span>${E(c.id)} · ${E(c.title)}<small>${E(c.family)} / ${E(c.split)}</small></span></label>`).join('')}</div></section>
<section class="card"><div class="card-top"><h2>03 / Πολιτικές συντονισμού</h2></div><div class="checks">${['cost_aware','always_reverify','cost_blind','llm'].map(p=>`<label class="check"><input type="checkbox" name="policy" value="${p}" ${p!=='cost_blind'?'checked':''}><span>${policyLabels[p]}<small>${E(state.policies[p])}</small></span></label>`).join('')}</div><details><summary>Διαγνωστικές ablations</summary><div class="checks">${['no_ttl','no_binding','no_conflict'].map(p=>`<label class="check"><input type="checkbox" name="policy" value="${p}"><span>${policyLabels[p]}</span></label>`).join('')}</div></details></section>
<section class="card"><div class="card-top"><h2>04 / Μοντέλα</h2><button id="add-model" class="btn" type="button">＋ Μοντέλο</button></div><div id="model-rows">${modelRow()}</div><div class="note info" id="model-note">Στο offline χρησιμοποιείται ένα scripted fixture. Δεν καλούνται τα επιλεγμένα μοντέλα και δεν παράγονται αποτελέσματα LLM.</div><div class="field-help">Για Claude/Gemini βάλε exact model ID διαθέσιμο στον δικό σου λογαριασμό. Οι adapters έχουν ελεγχθεί με mock responses, όχι με ζωντανές κλήσεις εδώ.</div></section>
<section class="card"><h2>05 / Προϋπολογισμός & αναπαραγωγή</h2><div class="form-grid"><div><label for="exp-cap">Πρόσθετο όριο κλήσεων σε αυτή την εκκίνηση</label><input id="exp-cap" type="number" min="1" max="10000" value="6"><div class="field-help">Όριο προσπαθειών API, όχι ποσό σε ευρώ.</div></div><div><label for="exp-steps">Μέγιστες αποφάσεις ανά επεισόδιο</label><input id="exp-steps" type="number" min="1" max="40" value="8"></div><div><label for="exp-seed">Seed σειράς συνθηκών</label><input id="exp-seed" type="number" min="0" value="2027"></div><div><label for="exp-value">Βάρος πιθανότητας γνώσης</label><input id="exp-value" type="number" min="0" max="1000" value="30" step="0.5"><div class="field-help">Ευρετική: βάρος × p − κόστος − αναμονή.</div></div></div></section></form>
<aside><section class="card plan-card"><div class="card-top"><h2>Σχέδιο εκτέλεσης</h2><span id="plan-mode">${modePill('offline')}</span></div><div id="plan-numbers"></div><p class="field-help">Η σειρά περιπτώσεων και συνθηκών τυχαιοποιείται με το seed. Κώδικας, prompt, δεδομένα και πλάνο αποθηκεύονται στο πείραμα.</p><div class="note warn" style="margin:20px 0">Το simulator χρησιμοποιεί κρυφή αλήθεια για αξιολόγηση και φιλτράρισμα dispatch. Η αξιολόγηση αφορά και τις προτάσεις πριν από το φίλτρο.</div><div id="plan-error" class="field-help"></div><button type="submit" form="experiment-form" class="btn primary" id="launch" style="width:100%;margin-top:18px">▶ Έναρξη offline πειράματος</button></section></aside></div>`;
const form=$('#experiment-form');function config(){return {mode:$('#exp-mode').value,evidence_mode:$('#exp-evidence').value,purpose:$('#exp-purpose').value,case_ids:$$('input[name=case]:checked').map(x=>x.value),policies:$$('input[name=policy]:checked').map(x=>x.value),repeats:Number($('#exp-repeat').value),max_steps:Number($('#exp-steps').value),seed:Number($('#exp-seed').value),question_value:Number($('#exp-value').value),models:$$('.model-row').map(x=>({provider:x.querySelector('select').value,model:x.querySelector('input').value.trim()}))};}
function update(){const c=config(),n=c.case_ids.length*c.policies.length*c.repeats*(c.mode==='offline'?1:c.models.length);$('#plan-mode').innerHTML=modePill(c.mode);$('#plan-numbers').innerHTML=`<div class="plan-numbers"><div><b>${n}</b><small>επεισόδια συνολικά</small></div><div><b>${c.mode==='offline'?0:Number($('#exp-cap').value)}</b><small>όριο κλήσεων τώρα</small></div></div><div class="plan-numbers"><div><b>${c.case_ids.length}</b><small>περιπτώσεις</small></div><div><b>${c.policies.length}</b><small>πολιτικές</small></div></div><p class="field-help" style="margin-top:15px">Θεωρητικό μέγιστο πλήρους πλάνου: ${c.mode==='live'?n*c.max_steps:0} κλήσεις. Δεν εκτελούνται αυτόματα πέρα από το πρόσθετο όριο.</p>`;$('#launch').textContent=c.mode==='live'?`▶ Έναρξη live · έως ${$('#exp-cap').value} κλήσεις`:'▶ Έναρξη offline πειράματος';$('#model-note').classList.toggle('hidden',c.mode==='live');$('#launch').disabled=!n;}
form.oninput=update;form.onchange=update;$('#add-model').onclick=()=>{if($$('.model-row').length>=6)return toast('Έως 6 μοντέλα ανά πείραμα.');$('#model-rows').insertAdjacentHTML('beforeend',modelRow('openai',''));update();};$('#model-rows').onclick=e=>{if(e.target.closest('.remove-model')){e.target.closest('.model-row').remove();update();}};$('#select-dev').onclick=()=>{$$('input[name=case]').forEach(x=>x.checked=cases.find(c=>c.id===x.value).split==='development');update();};$('#select-none').onclick=()=>{$$('input[name=case]').forEach(x=>x.checked=false);update();};
form.onsubmit=safe(async e=>{e.preventDefault();const c=config();if(!c.case_ids.length)throw Error('Επίλεξε τουλάχιστον ένα σενάριο.');$('#launch').disabled=true;try{await api('/api/plan',{config:c});const s=await api('/api/experiments',{name:$('#exp-name').value,config:c});try{await api(`/api/experiments/${s.id}/start`,{max_calls:Number($('#exp-cap').value)});}catch(e){toast(e.message,true);}navigate('experiment/'+s.id);}finally{if($('#launch'))$('#launch').disabled=false;}});update();}
async function experimentDetail(id,refresh=false){clearTimeout(poll);disposeInteractive();const current=await api('/api/experiments/'+id);detailCache=current;const s=current.session,a=current.summary;const running=s.status==='running';const finished=s.runs.filter(r=>['delivered','escalated','dispatch_blocked','deadline_missed','step_limit','error','interrupted_unknown'].includes(r.status)).length;
$('#main').innerHTML=pageHeader(E(s.name),`${s.config.purpose==='evaluation'?'Αξιολόγηση με δηλωμένο ανεξάρτητο έλεγχο':'Πείραμα ανάπτυξης'} · ${s.dataset_sha256.slice(0,12)} · ${E(s.created_at)}`,`<div class="actions"><a class="btn" href="/api/experiments/${id}/export?format=zip">↓ Εξαγωγή πακέτου</a>${running?'<button id="pause" class="btn danger">Ⅱ Παύση μετά την τρέχουσα κλήση</button>':s.status!=='completed'?'<button id="resume" class="btn primary">▶ Έναρξη / Συνέχεια</button>':''}</div>`)+`<div class="actions">${modePill(s.config.mode)}${status(s.status)}${pill(`${finished}/${s.plan.length} προσπάθειες`)}${pill(`${s.runs.reduce((v,r)=>v+r.api_calls,0)} κλήσεις`)}</div><div class="progress"><span style="width:${finished/s.plan.length*100}%"></span></div><div class="tabs"><button data-tab="simulation" class="${detailTab==='simulation'?'active':''}">Προσομοίωση ομάδας</button><button data-tab="overview" class="${detailTab==='overview'?'active':''}">Συγκριτικά αποτελέσματα</button><button data-tab="dialogue" class="${detailTab==='dialogue'?'active':''}">Διάλογος & αποφάσεις</button><button data-tab="config" class="${detailTab==='config'?'active':''}">Πρωτόκολλο εκτέλεσης</button></div><div id="detail-content"></div>`;
if($('#pause'))$('#pause').onclick=safe(async()=>{await api(`/api/experiments/${id}/pause`,{});toast('Ζητήθηκε παύση. Η τρέχουσα κλήση μπορεί να ολοκληρωθεί και να χρεωθεί.');});
if($('#resume'))$('#resume').onclick=()=>{const d=$('#dialog');$('#dialog-body').innerHTML=`<h2>Συνέχεια πειράματος</h2><p class="subtitle">Οι ολοκληρωμένες ή αποτυχημένες προσπάθειες διατηρούνται. Οι κλήσεις που έμειναν σε αναμονή μετά από διακοπή δεν επαναλαμβάνονται.</p><label for="resume-cap" style="margin-top:22px">Πρόσθετο όριο κλήσεων για αυτή την εκκίνηση</label><input id="resume-cap" type="number" value="6" min="1" max="10000"><button id="resume-go" class="btn primary" style="margin-top:20px">▶ Εκτέλεση με αυτό το όριο</button>`;d.showModal();$('#resume-go').onclick=safe(async()=>{await api(`/api/experiments/${id}/start`,{max_calls:Number($('#resume-cap').value)});d.close();await experimentDetail(id);});};
$$('[data-tab]').forEach(b=>b.onclick=()=>{detailTab=b.dataset.tab;experimentDetail(id).catch(e=>toast(e.message,true));});
if(detailTab==='simulation')detailDialogue(s,true);else if(detailTab==='overview')detailOverview(s,a);else if(detailTab==='dialogue')detailDialogue(s);else $('#detail-content').innerHTML=`<section class="card"><h2>Παγωμένο πλάνο</h2><div class="note info">Οι ρυθμίσεις αυτού του πειράματος δεν αλλάζουν μετά τη δημιουργία. Για νέα συνθήκη δημιούργησε νέο πείραμα.</div><pre class="json-view">${E(JSON.stringify({config:s.config,fingerprint:s.fingerprint,review:s.dataset.review,readiness:s.readiness,batches:s.batches},null,2))}</pre><details><summary>Ακριβές prompt</summary><pre class="json-view">${E(s.prompt)}</pre></details><div class="actions"><a class="btn" href="/api/experiments/${id}/export?format=session">↓ session.json</a><a class="btn" href="/api/experiments/${id}/export?format=report">↓ HTML report</a></div></section>`;
if(running&&detailTab!=='simulation'){clearTimeout(poll);poll=setTimeout(()=>{if(location.hash==='#experiment/'+id)experimentDetail(id,true).catch(e=>toast(e.message,true));},2000);} }
function detailOverview(s,a){const max=Math.max(1,...a.groups.map(g=>g.query_cost));$('#detail-content').innerHTML=`${s.config.mode==='offline'?'<div class="note info" style="margin-bottom:22px">OFFLINE FIXTURE: αυτές οι γραμμές ελέγχουν λογισμικό. Η πολιτική llm χρησιμοποιεί scripted απάντηση και δεν αξιολογεί γλωσσικό μοντέλο.</div>':''}${!a.complete?'<div class="note warn" style="margin-bottom:22px">Το πλάνο δεν έχει ολοκληρωθεί. Έλεγξε την κάλυψη κάθε συνθήκης πριν συγκρίνεις επιδόσεις.</div>':''}<section class="card"><div class="card-top"><h2>Αποτελέσματα ανά συνθήκη</h2><div class="actions"><a href="/api/experiments/${s.id}/export?format=csv">CSV ↓</a><a href="/api/experiments/${s.id}/export?format=latex">LaTeX ↓</a></div></div><div class="table-scroll"><table><thead><tr><th>ΜΟΝΤΕΛΟ / ΠΟΛΙΤΙΚΗ</th><th>ΚΑΛΥΨΗ</th><th>REFERENCE MET</th><th>ΕΡΩΤΗΣΕΙΣ</th><th>ΚΟΣΤΟΣ</th><th>UNSAFE / UNSUPPORTED</th><th>ΛΑΘΗ ΕΞΑΓΩΓΗΣ<br>ΑΡΧΙΚΑ / ΜΕΤΑ ΦΙΛΤΡΟ</th><th>ΑΠΟΡΡΙΨΕΙΣ ΦΙΛΤΡΟΥ</th><th>ΤΕΧΝΙΚΑ ΣΦΑΛΜΑΤΑ</th><th>API</th></tr></thead><tbody>${a.groups.map(g=>`<tr><td>${E(g.condition)}</td><td>${g.finished}/${g.assigned}</td><td>${g.outcome_met}</td><td>${g.questions}</td><td>${g.query_cost}</td><td>${g.unsafe_episodes} / ${g.unsupported_episodes}</td><td>${g.extraction_error_turns} / ${g.accepted_extraction_error_turns??g.extraction_error_turns}</td><td>${g.rejected_evidence||0}</td><td>${g.errors}</td><td>${g.api_calls}</td></tr>`).join('')}</tbody></table></div><p class="field-help">Unsafe/unsupported μετρά επεισόδια με τουλάχιστον μία σχετική πρόταση, πριν από το κοινό oracle φίλτρο. Reference met βασίζεται σε συνθετική κρυφή αλήθεια και εφικτότητα.</p></section><div class="grid"><section class="card"><h2>Κόστος διακοπής της ομάδας</h2>${a.groups.map(g=>`<div class="bar-row"><span>${E(g.condition.split(' / ').slice(-1)[0])}<small class="cell-sub">${E(g.condition.split(' / ').slice(0,-1).join(' / '))}</small></span><div class="bar-bg"><div class="bar-fill" style="width:${g.query_cost/max*100}%"></div></div><b>${g.query_cost}</b></div>`).join('')}<p class="field-help">Αθροιστικές συνθετικές μονάδες. Οι αποτυχημένες/μερικές προσπάθειες συμπεριλαμβάνονται στην καταγραφή κόστους.</p></section><section class="card"><h2>Τι ελέγχουμε πριν από συμπεράσματα</h2><ul class="step-list" style="list-style:none"><li>Πλήρης κάλυψη του παγωμένου πλάνου.<small>Οι τεχνικές αποτυχίες παραμένουν ορατές.</small></li><li>Ορθότητα προτάσεων και κλιμακώσεων.<small>Η απουσία εκτελεσμένων λαθών δεν αποδεικνύει ασφάλεια.</small></li><li>Ανεξάρτητες περιπτώσεις και reviewers.<small>Οι γύροι διαλόγου δεν είναι ανεξάρτητα δείγματα.</small></li></ul></section></div><section class="card"><h2>Exploratory paired cost analysis</h2><p class="field-help">Διαφορά cost_aware − always_reverify, ανά σενάριο μετά από μέσο όρο επαναλήψεων. Περιγραφικό bootstrap σε επίπεδο σεναρίου· όχι απόδειξη μη κατωτερότητας ή κλινικής ασφάλειας.</p><pre class="json-view">${E(JSON.stringify(a.paired_cost,null,2))}</pre></section>`;}


/* Interactive lab: isolated browser-only training, never a scored LLM experiment. */
const InteractiveSim=(()=>{
 const clone=x=>JSON.parse(JSON.stringify(x));
 const esc=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 const canon=(subject,aliases)=>aliases[subject]||subject;
 const names={ask:'Ερώτηση',wait:'Αναμονή',dispatch:'Αποστολή',escalate:'Παραπομπή σε υπεύθυνο'};
 const results={answered:'Λήφθηκε νέα επιβεβαίωση',unknown:'Το μέλος δεν γνωρίζει',waited:'Πέρασε ένα βήμα',delivered:'Ολοκληρώθηκε η παράδοση',escalated:'Η εργασία παραπέμφθηκε σε υπεύθυνο',dispatch_blocked:'Ο simulator μπλόκαρε την αποστολή'};
 const terminal=new Set(['delivered','escalated','dispatch_blocked','deadline_missed','step_limit']);
 function valueOf(task,evidence,conflict){
  if(conflict)return null;
  const valid=evidence.filter(e=>canon(e.subject,task.aliases)===canon(task.subject,task.aliases)&&task.now-e.timestamp>=0&&task.now-e.timestamp<=e.ttl);
  return valid.length?valid.reduce((a,b)=>b.timestamp>a.timestamp?b:a).value:null;
 }
 class Sandbox {
  #truth; #access; #evidence; #conflict; #task; #messages; #history=[]; #done=false; #cost=0; #questions=0;
  constructor(scenario,costs=null){
   this.#truth=scenario.private.actual_verified;this.#access=[...scenario.private.actual_access];
   this.#evidence=clone(scenario.annotations.evidence);this.#conflict=scenario.annotations.conflict;
   this.#task=Object.fromEntries(['subject','now','deadline','aliases','probability_knows','available_at','query_cost'].map(k=>[k,clone(scenario.public[k])]));
   Object.assign(this.#task,{sources:['H2','H3'],attempted:[],received_answer:false});
   if(costs){for(const h of ['H2','H3']){if(!Number.isFinite(costs[h])||costs[h]<0||costs[h]>1000)throw Error('Το κόστος πρέπει να είναι αριθμός από 0 έως 1000.');}this.#task.query_cost=clone(costs);}
   this.#messages=clone(scenario.messages).map(m=>({...m,valid_for:scenario.initial_ttl??100}));
  }
  snapshot(){
   const publicInput={task:clone(this.#task),messages:clone(this.#messages)};
   const accepted=this.#evidence.map(e=>{
    const m=this.#messages.find(m=>m.speaker===e.source&&m.time===e.timestamp);
    return m?{message_id:m.message_id,subject:e.subject,value:e.value}:null;
   }).filter(Boolean);
   return {publicInput,step:{accepted_evidence:accepted,raw_output:{conflict:this.#conflict}},
    value:valueOf(this.#task,this.#evidence,this.#conflict),done:this.#done,
    questions:this.#questions,cost:this.#cost,history:clone(this.#history),last:clone(this.#history.at(-1)||null)};
  }
  recommendation(policy){
   if(!['cost_aware','always_reverify','cost_blind'].includes(policy))throw Error('Άγνωστη εκπαιδευτική πολιτική.');
   if(this.#done)return null;
   const t=this.#task,value=valueOf(t,this.#evidence,this.#conflict);
   if(policy!=='always_reverify'||t.received_answer){if(value!==null)return {action:value?'dispatch':'escalate',recipient:null};}
   const possible=t.sources.filter(h=>!t.attempted.includes(h)&&t.probability_knows[h]>0&&Math.max(t.now,t.available_at[h])+1<=t.deadline);
   if(!possible.length)return {action:'escalate',recipient:null};
   const score=h=>30*t.probability_knows[h]-Math.max(0,t.available_at[h]-t.now)-(policy==='cost_blind'?0:t.query_cost[h]);
   const h=possible.reduce((a,b)=>score(b)>score(a)?b:a);
   return {action:t.available_at[h]>t.now?'wait':'ask',recipient:h};
  }
  apply(action){
   if(this.#done)throw Error('Η δοκιμή ολοκληρώθηκε. Πάτησε επαναφορά για νέα προσπάθεια.');
   if(!action||!['ask','wait','dispatch','escalate'].includes(action.action))throw Error('Άγνωστη ενέργεια.');
   const t=this.#task,kind=action.action,h=action.recipient;
   if(['ask','wait'].includes(kind)){
    if(!t.sources.includes(h)||t.attempted.includes(h))throw Error('Η πηγή δεν είναι έγκυρη ή έχει ήδη ερωτηθεί.');
    if(kind==='ask'&&t.available_at[h]>t.now)throw Error('Το μέλος δεν είναι ακόμη διαθέσιμο. Δοκίμασε αναμονή.');
    if(t.now+1>t.deadline)throw Error('Η ενέργεια θα ξεπερνούσε την προθεσμία.');
   }else if(h!==null)throw Error('Η ενέργεια δεν δέχεται αποδέκτη.');
   const event={time:t.now,action:kind,recipient:h};
   if(kind==='ask'){
    const answer=this.#access.includes(h)?this.#truth:'unknown';
    event.result=typeof answer==='boolean'?'answered':'unknown';event.answer=answer;event.cost=t.query_cost[h];event.subject=t.subject;
    this.#questions++;this.#cost+=event.cost;
    let n=this.#messages.length+1;const used=new Set(this.#messages.map(m=>m.message_id));
    while(used.has('m'+String(n).padStart(3,'0'))||used.has('m'+String(n+1).padStart(3,'0')))n+=2;
    this.#messages.push({message_id:'m'+String(n).padStart(3,'0'),speaker:'ROBOT',time:t.now,valid_for:0,text:'Ποια είναι η τρέχουσα κατάσταση ελέγχου για το '+t.subject+';'});
    t.now++;t.attempted.push(h);
    if(typeof answer==='boolean'){
     this.#evidence=this.#evidence.filter(e=>canon(e.subject,t.aliases)!==canon(t.subject,t.aliases));
     this.#evidence.push({subject:t.subject,value:answer,source:h,timestamp:t.now,ttl:100});
     this.#conflict=false;t.received_answer=true;
    }else t.probability_knows[h]=0;
    const text=typeof answer==='boolean'?'Επανέλεγξα το '+t.subject+' τώρα. Ο έλεγχος '+(answer?'ολοκληρώθηκε.':'δεν έχει ολοκληρωθεί.')+' Αυτή η ενημέρωση αντικαθιστά τις προηγούμενες αναφορές για το ίδιο καρότσι.':'Δεν γνωρίζω την κατάσταση ελέγχου για το '+t.subject+'.';
    this.#messages.push({message_id:'m'+String(n+1).padStart(3,'0'),speaker:h,time:t.now,valid_for:100,text});
   }else if(kind==='wait'){t.now++;event.result='waited';}
   else if(kind==='dispatch'){
    const supported=valueOf(t,this.#evidence,this.#conflict)===true;
    event.result=this.#truth&&supported?'delivered':'dispatch_blocked';
    event.unsupported=!supported;event.truth_violation=!this.#truth;this.#done=true;
   }else{event.result='escalated';this.#done=true;}
   this.#history.push(event);
   if(!this.#done&&this.#history.length>=8){this.#done=true;event.limit_reached=true;}
   return clone(event);
  }
 }
 function stateLabel(snapshot){
  const v=snapshot.value;
  return snapshot.step.raw_output?.conflict?'Αντικρουόμενες αναφορές':v===true?'Ισχύουσα θετική αναφορά':v===false?'Ισχύουσα αρνητική αναφορά':'Άγνωστη / μη ισχύουσα επιβεβαίωση';
 }
 function replaySnapshot(row,cursor){
  const i=Math.floor(cursor/2),after=cursor%2===1,st=row.steps[i];if(!st)return null;
  const validExtraction=Array.isArray(st.accepted_evidence)||!!st.extraction_checks;
  const p=clone(st.public_input),step={raw_output:{evidence:validExtraction&&Array.isArray(st.raw_output?.evidence)?clone(st.raw_output.evidence):[],conflict:validExtraction&&st.raw_output?.conflict===true},evidence_guard_applied:st.evidence_guard_applied===true},action=st.selected_action,event=after?st.transition:null;
  if(Array.isArray(st.accepted_evidence))step.accepted_evidence=clone(st.accepted_evidence);
  if(event&&action&&['ask','wait'].includes(action.action)){
   p.task.now++;
   if(action.action==='ask'){
    const h=action.recipient;p.task.attempted=[...(p.task.attempted||[]),h];
    const mid='playback-reply-'+i;
    p.messages.push({message_id:'playback-question-'+i,speaker:'ROBOT',time:p.task.now-1,valid_for:0,text:'Ποια είναι η τρέχουσα κατάσταση ελέγχου για το '+p.task.subject+';'});
    const answer=event.answer;
    p.messages.push({message_id:mid,speaker:h,time:p.task.now,valid_for:100,text:typeof answer==='boolean'?'Επανέλεγξα το '+p.task.subject+' τώρα. Ο έλεγχος '+(answer?'ολοκληρώθηκε.':'δεν έχει ολοκληρωθεί.')+' Αυτή η ενημέρωση αντικαθιστά τις προηγούμενες αναφορές για το ίδιο καρότσι.':'Δεν γνωρίζω την κατάσταση ελέγχου για το '+p.task.subject+'.'});
    if(typeof answer==='boolean'){
     const accepted=Array.isArray(step.accepted_evidence)?step.accepted_evidence:(Array.isArray(step.raw_output?.evidence)?step.raw_output.evidence:[]);
     step.accepted_evidence=accepted.filter(e=>canon(e.subject,p.task.aliases)!==canon(p.task.subject,p.task.aliases));
     step.accepted_evidence.push({message_id:mid,subject:p.task.subject,value:answer});
     step.raw_output={...step.raw_output,conflict:false};p.task.received_answer=true;
    }else p.task.probability_knows[h]=0;
   }
  }
  const parsed=simulationSnapshot(p,step),done=!!event&&terminal.has(event.result);
  const past=row.steps.slice(0,i+(after?1:0)).filter(x=>x.transition).map(x=>x.transition);
  return {publicInput:p,step,value:parsed.value,done,last:event?Object.fromEntries(['time','action','recipient','result','answer','cost'].filter(k=>k in event).map(k=>[k,clone(event[k])])):null,
   questions:past.filter(x=>x.action==='ask').length,cost:past.reduce((sum,x)=>sum+(x.cost||0),0),history:past.map(e=>Object.fromEntries(['time','action','recipient','result','answer','cost'].filter(k=>k in e).map(k=>[k,clone(e[k])]))),
   action,after,turn:i,technical:st.error||null};
 }

 function scene(snapshot,options={}){
  const t=snapshot.publicInput.task,action=options.action||null,last=snapshot.last;
  const complete=last?.result==='delivered',blocked=last?.result==='dispatch_blocked';
  const target=['H2','H3'].includes(action?.recipient)?action.recipient:null;
  const spots={H1:[452,153],H2:[235,245],H3:[715,255]};
  const beam=target?spots[target]:null;
  const humans=Object.entries(spots).map(([h,[x,y]])=>{
   const source=h!=='H1',available=source&&t.available_at[h]<=t.now,attempted=(t.attempted||[]).includes(h);
   const clickable=options.interactive&&source&&!snapshot.done&&!options.busy&&!attempted&&available&&t.now+1<=t.deadline;
   const color=source?(attempted?'#8a9bb4':available?'#69d5c0':'#eab970'):'#9caed0';
   return '<g transform="translate('+x+' '+y+')" class="lab-human '+(target===h?'is-addressed ':'')+(clickable?'is-clickable':'')+'"'+(source?' data-person="'+h+'" role="button" tabindex="'+(clickable?'0':'-1')+'" aria-disabled="'+(!clickable)+'" aria-label="'+esc('Ρώτησε '+h)+'"':'')+'>'+
    '<ellipse cx="0" cy="44" rx="35" ry="14" fill="#102b49" opacity=".13"/><circle cx="0" cy="-22" r="12" fill="#dfb99b"/><path d="M-17,-6 Q0,-14 17,-6 L22,25 L12,29 L9,7 L10,32 L-10,32 L-9,7 L-12,29 L-22,25 Z" fill="'+(target===h?'#448bff':'#4b8d94')+'"/><path d="M-10,31 L-2,31 L-3,49 L-13,49 Z M2,31 L10,31 L13,49 L3,49 Z" fill="#263d5c"/><path d="M-4,-5 L0,1 L4,-5" fill="none" stroke="#c9e5e7" stroke-width="2"/><rect x="6" y="7" width="6" height="8" rx="1" fill="#dce9eb"/>'+
    '<rect x="-52" y="-68" width="104" height="28" rx="9" fill="#fff" stroke="'+(target===h?'#70a3ff':'#d5e0ed')+'"/><circle cx="-35" cy="-54" r="4" fill="'+color+'"/><text x="-23" y="-50" font-size="12" font-weight="700" fill="#1c3758">'+h+'</text><text x="48" y="-50" text-anchor="end" font-size="10" fill="#637995">'+(source?esc(t.query_cost[h])+' μον.':'Πλαίσιο')+'</text></g>';
  }).join('');
  let bubble='';
  if(last?.action==='ask'&&spots[last.recipient]){
   const [x,y]=spots[last.recipient],text=last.answer===true?'Ο έλεγχος ολοκληρώθηκε':last.answer===false?'Ο έλεγχος δεν ολοκληρώθηκε':'Δεν γνωρίζω';
   bubble='<g class="lab-answer" transform="translate('+(x-105)+' '+(y-116)+')"><rect width="210" height="32" rx="10" fill="#fff" stroke="#a8c8ee"/><path d="M96,32 L105,42 L114,32" fill="#fff" stroke="#a8c8ee"/><text x="105" y="21" text-anchor="middle" font-size="10" fill="#23486e">'+esc(text)+'</text></g>';
  }
  const cx=complete?690:555,cy=complete?370:340,rx=complete?625:425,ry=complete?374:305;
  return '<div class="lab-room '+(options.busy?'is-running':'')+'"><div class="lab-room-top"><span class="lab-mode-tag">'+(options.interactive?'ΔΙΚΗ ΣΟΥ ΔΟΚΙΜΗ · ΧΩΡΙΣ API':'ΑΝΑΠΑΡΑΓΩΓΗ ΚΑΤΑΓΡΑΦΗΣ')+'</span><span>Σχηματικός χώρος · όχι πραγματικές θέσεις</span></div>'+
   '<svg class="lab-scene" viewBox="0 0 936 510" role="'+(options.interactive?'group':'img')+'" aria-label="Σχηματική προσομοίωση ομάδας με ρομπότ, καρότσι και μέλη H1 H2 H3" xmlns="http://www.w3.org/2000/svg"><defs><linearGradient id="lab-floor" x2="1" y2="1"><stop stop-color="#edf3fb"/><stop offset="1" stop-color="#dce8f6"/></linearGradient><linearGradient id="lab-wall" x2="0" y2="1"><stop stop-color="#f9fcff"/><stop offset="1" stop-color="#dae5f2"/></linearGradient><pattern id="lab-grid" width="44" height="26" patternUnits="userSpaceOnUse" patternTransform="matrix(1 .35 -1 .35 440 160)"><rect width="44" height="26" fill="none" stroke="#c3d3e6" stroke-width="1"/></pattern></defs>'+
   '<rect width="936" height="510" rx="18" fill="#eef3fa"/><ellipse cx="470" cy="430" rx="360" ry="45" fill="#1e426a" opacity=".06"/>'+
   '<path d="M74,212 L450,86 L866,218 L470,470 Z" fill="url(#lab-floor)" stroke="#bfcee1"/><path d="M74,212 L450,86 L866,218 L470,470 Z" fill="url(#lab-grid)" opacity=".55"/>'+
   '<path d="M74,212 L74,126 L450,21 L450,86 Z" fill="url(#lab-wall)" stroke="#c6d4e5"/><path d="M450,21 L866,151 L866,218 L450,86 Z" fill="#e2ebf6" stroke="#c6d4e5"/>'+
   '<path d="M98,196 L98,142 L161,124 L161,177 Z" fill="#c4d7ec" stroke="#8faac9"/><path d="M107,151 L151,138 L151,153 L107,166 Z" fill="#7fa3ca"/><text x="112" y="184" font-size="9" fill="#456789">ΕΙΣΟΔΟΣ</text>'+
   '<path d="M578,81 L689,116 L689,157 L578,123 Z" fill="#afc4de" stroke="#819fbe"/><path d="M586,90 L680,120 L680,135 L586,105 Z" fill="#e7f3ff"/><path d="M592,94 L625,105 M635,108 L670,120" stroke="#66a8d5" stroke-width="4"/>'+
   '<g transform="translate(780 213)"><path d="M-48,-20 L0,-35 L43,-20 L0,-4 Z" fill="#f6faff" stroke="#8fa9c8"/><path d="M-48,-20 L0,-4 L0,37 L-48,19 Z" fill="#bed0e4" stroke="#8fa9c8"/><path d="M0,-4 L43,-20 L43,17 L0,37 Z" fill="#a0b9d4" stroke="#8fa9c8"/><rect x="-18" y="-49" width="32" height="24" rx="3" fill="#234b71"/><path d="M-12,-36 L-5,-36 L0,-42 L5,-31 L11,-36" fill="none" stroke="#7ad3d2" stroke-width="2"/></g>'+
   '<path d="M604,391 L698,350 L783,391 L689,439 Z" fill="'+(complete?'#c6eadf':'#d0deed')+'" stroke="'+(complete?'#71b49a':'#9eb5ce')+'" stroke-dasharray="5 5"/><text x="690" y="455" text-anchor="middle" font-size="10" font-weight="600" fill="#607d9e">ΖΩΝΗ ΠΑΡΑΔΟΣΗΣ</text>'+
   (beam?'<path class="lab-signal" d="M425,278 Q'+beam[0]+',160 '+beam[0]+','+(beam[1]-35)+'" fill="none" stroke="#4d91ef" stroke-width="3" stroke-dasharray="7 7" opacity=".8"/>':'')+
   humans+
   '<g transform="translate('+cx+' '+cy+')" class="lab-cart '+(complete?'is-delivered':'')+'"><g class="lab-cart-motion"><ellipse cx="0" cy="40" rx="39" ry="14" fill="#163752" opacity=".14"/><path d="M-30,-28 L7,-41 L39,-27 L1,-13 Z" fill="#f7fbff" stroke="#7898b9" stroke-width="2"/><path d="M-30,-28 L1,-13 L1,27 L-30,12 Z" fill="#bfcede" stroke="#7898b9" stroke-width="2"/><path d="M1,-13 L39,-27 L39,12 L1,27 Z" fill="#9fb4cd" stroke="#7898b9" stroke-width="2"/><path d="M-29,-6 L1,8 L37,-6" fill="none" stroke="#e7eff9" stroke-width="3"/><path d="M35,-27 L45,-31 L45,-42" fill="none" stroke="#587b9f" stroke-width="3"/><path d="M-13,-38 L8,-45 L22,-39 L0,-31 Z" fill="#79aebc" stroke="#4b7c8a"/><circle cx="-24" cy="23" r="5" fill="#415d7b"/><circle cx="4" cy="35" r="5" fill="#415d7b"/><circle cx="35" cy="21" r="5" fill="#415d7b"/><text x="0" y="61" text-anchor="middle" font-size="11" font-weight="700" fill="#355674">'+esc(t.subject)+'</text></g></g>'+
   '<g transform="translate('+rx+' '+ry+')" class="lab-mobile-robot '+(complete?'is-delivered':'')+'"><g class="lab-robot-motion"><ellipse cx="0" cy="42" rx="36" ry="14" fill="#142f4f" opacity=".16"/><path d="M-25,12 Q0,26 25,12 L25,28 Q0,49 -25,28 Z" fill="#4b6c96"/><ellipse cx="0" cy="12" rx="25" ry="12" fill="#d7e4f5" stroke="#54739a" stroke-width="2"/><rect x="-23" y="-31" width="46" height="38" rx="13" fill="#fcfdff" stroke="#54739a" stroke-width="2"/><rect x="-17" y="-23" width="34" height="19" rx="8" fill="#234e7a"/><circle cx="-7" cy="-14" r="3" fill="#8be1e4"/><circle cx="7" cy="-14" r="3" fill="#8be1e4"/><path d="M0,-32 L0,-42" stroke="#54739a" stroke-width="2"/><circle cx="0" cy="-44" r="4" fill="'+(blocked?'#e69f8d':'#6ed2c1')+'"/><text x="0" y="65" text-anchor="middle" font-size="10" font-weight="700" fill="#355674">Ρομπότ συντονιστής</text></g></g>'+
   bubble+'<text x="66" y="485" font-size="9" fill="#6b83a0">Χώρος προετοιμασίας εξοπλισμού · συμβολική κίνηση</text></svg>'+
   '<div class="lab-state-strip"><span class="lab-state-dot '+(snapshot.value===true?'positive':snapshot.value===false?'negative':'')+'"></span><strong>'+esc(stateLabel(snapshot))+'</strong><span>t = '+esc(t.now)+' / '+esc(t.deadline)+'</span></div></div>';
 }
 function transcript(snapshot){
  return '<div class="lab-transcript" role="log" aria-label="Διάλογος ομάδας">'+snapshot.publicInput.messages.map(m=>'<article class="lab-message '+(m.speaker==='ROBOT'?'from-robot':'')+'"><span class="lab-message-avatar">'+esc(m.speaker==='ROBOT'?'R':m.speaker)+'</span><div><small>'+esc(m.speaker)+' · t='+esc(m.time)+'</small><p>'+esc(m.text)+'</p></div></article>').join('')+'</div>';
 }
 function sourceCards(snapshot,interactive,busy){
  const t=snapshot.publicInput.task;
  return '<div class="lab-source-cards">'+['H2','H3'].map(h=>{
   const attempted=t.attempted.includes(h),available=t.available_at[h]<=t.now,late=t.now+1>t.deadline;
   const disabled=!interactive||busy||snapshot.done||attempted||!available||late;
   const waitDisabled=!interactive||busy||snapshot.done||attempted||available||late;
   return '<article class="lab-source '+(snapshot.last?.recipient===h?'was-addressed':'')+'"><div class="lab-source-heading"><span class="lab-person-badge">'+h+'</span><div><h3>Μέλος '+h+'</h3><small>'+(attempted?'Έχει ερωτηθεί':available?'Διαθέσιμο τώρα':'Διαθέσιμο στο t='+esc(t.available_at[h]))+'</small></div><strong>'+esc(t.query_cost[h])+'<small>μον. / ερώτηση</small></strong></div><label>Εκτίμηση ότι γνωρίζει <b>'+Math.round(t.probability_knows[h]*100)+'%</b></label><div class="lab-estimate"><i style="width:'+Math.max(0,Math.min(100,t.probability_knows[h]*100))+'%"></i></div>'+(interactive?'<div class="lab-source-actions"><button class="btn primary" data-ask="'+h+'" '+(disabled?'disabled':'')+'>Ρώτησε '+h+'</button><button class="btn" data-wait="'+h+'" '+(waitDisabled?'disabled':'')+'>Αναμονή για '+h+'</button></div>':'')+'</article>';
  }).join('')+'</div>';
 }
 function metrics(snapshot){
  const t=snapshot.publicInput.task;
  return '<div class="lab-metrics"><div><small>ΕΡΩΤΗΣΕΙΣ</small><b>'+snapshot.questions+'</b></div><div><small>ΚΟΣΤΟΣ ΔΙΑΚΟΠΩΝ</small><b>'+snapshot.cost+' <em>μον.</em></b></div><div><small>ΒΗΜΑΤΑ ΠΟΥ ΑΠΟΜΕΝΟΥΝ</small><b>'+Math.max(0,t.deadline-t.now)+'</b></div><div><small>ΝΕΕΣ ΚΛΗΣΕΙΣ ΑΠΟ ΤΗΝ ΠΡΟΒΟΛΗ</small><b>0</b></div></div>';
 }
 function outcome(snapshot){
  const last=snapshot.last;if(!last)return '<p class="lab-action-hint">Επίλεξε μια πηγή πληροφορίας ή δοκίμασε την πρόταση μιας πολιτικής.</p>';
  const text=results[last.result]||last.result;
  return '<div class="lab-outcome '+(last.result==='dispatch_blocked'?'blocked':last.result==='delivered'?'delivered':'')+'" role="status"><strong>'+esc(text)+'</strong><p>'+esc(last.result==='dispatch_blocked'?'Η πρόταση δεν πέρασε τον έλεγχο κρυφής αλήθειας / τεκμηρίωσης του συνθετικού simulator.':last.result==='delivered'?'Η μεταφορά ολοκληρώθηκε στη συνθετική εργασία. Η κίνηση στο σκηνικό είναι συμβολική.':last.result==='unknown'?'Η εκτίμηση γνώσης αυτής της πηγής ενημερώθηκε. Μπορείς να δοκιμάσεις άλλο μέλος.':last.result==='escalated'?'Η αυτόματη εργασία σταμάτησε και παραπέμφθηκε σε υπεύθυνο.':last.result==='waited'?'Έλεγξε ποια πηγή είναι πλέον διαθέσιμη και πόσος χρόνος απομένει.':'Η νέα απάντηση ενημέρωσε την κατάσταση του συγκεκριμένου καροτσιού.')+'</p></div>';
 }
 function timeline(snapshot){
  return '<ol class="lab-timeline">'+snapshot.history.map((e,i)=>'<li><span>'+(i+1)+'</span><div><b>'+esc((names[e.action]||e.action)+(e.recipient?' → '+e.recipient:''))+'</b><small>t='+esc(e.time)+' · '+esc(results[e.result]||e.result)+(e.cost!==undefined?' · κόστος '+esc(e.cost):'')+'</small></div></li>').join('')+'</ol>';
 }

 function mountLab(root,dataset,options={}){
  let cases=dataset.cases.filter(c=>c.split==='development'),chosen=options.scenario||cases.find(c=>c.id==='D09')||cases[0];
  if(options.scenario&&!cases.some(c=>c.id===chosen.id))cases=[chosen,...cases];
  else if(options.scenario)cases=cases.map(c=>c.id===chosen.id?chosen:c);
  if(!chosen){root.innerHTML='<div class="empty">Δεν υπάρχουν σενάρια για εκπαιδευτική δοκιμή.</div>';return ()=>{};}
  let costs=clone(chosen.public.query_cost),sandbox=new Sandbox(chosen,costs),policy='cost_aware',comparison=null,busy=false,preview=null,timer=null,disposed=false,error='';
  const $=selector=>root.querySelector(selector),all=selector=>Array.from(root.querySelectorAll(selector));
  function reset(){clearTimeout(timer);busy=false;preview=null;comparison=null;error='';sandbox=new Sandbox(chosen,costs);render();}
  function act(action){
   if(disposed||busy)return;
   error='';busy=true;preview=action;render();
   const reduced=typeof window.matchMedia==='function'&&window.matchMedia('(prefers-reduced-motion: reduce)').matches;
   timer=setTimeout(()=>{if(disposed)return;try{sandbox.apply(action);}catch(e){error=e.message;}busy=false;preview=null;render();},reduced?0:650);
  }
  function compare(){
   comparison=['cost_aware','always_reverify','cost_blind'].map(name=>{
    const other=new Sandbox(chosen,costs);for(let n=0;n<8&&!other.snapshot().done;n++)other.apply(other.recommendation(name));
    const x=other.snapshot();return {policy:name,cost:x.cost,questions:x.questions,result:x.last?.limit_reached?'step_limit':x.last?.result,path:x.history.map(e=>(names[e.action]||e.action)+(e.recipient?' → '+e.recipient:''))};
   });render();
  }
  function render(){
   if(disposed)return;
   const snapshot=sandbox.snapshot(),t=snapshot.publicInput.task,next=sandbox.recommendation(policy);
   const custom=['H2','H3'].some(h=>costs[h]!==chosen.public.query_cost[h]);
   root.innerHTML='<section class="lab-shell"><div class="lab-banner"><span class="lab-mode-tag">ΕΚΠΑΙΔΕΥΤΙΚΟ SANDBOX · 0 API</span><p>Εσύ επιλέγεις τις ενέργειες. Οι απαντήσεις είναι προγραμματισμένες, με δομημένη αρχική κατάσταση· δεν γίνεται εξαγωγή από LLM και αυτή η δοκιμή δεν βαθμολογείται ως ερευνητικό πείραμα.</p></div>'+
    '<div class="lab-toolbar"><div><label for="lab-case">Σενάριο</label><select id="lab-case">'+cases.map(c=>'<option value="'+esc(c.id)+'">'+esc(c.id+' · '+c.title)+'</option>').join('')+'</select></div><div><label for="lab-policy">Πολιτική για σύγκριση</label><select id="lab-policy"><option value="cost_aware">Επιλεκτική, με κόστος</option><option value="always_reverify">Πάντα νέα επιβεβαίωση</option><option value="cost_blind">Χωρίς κόστος πηγής</option></select></div><button id="lab-reset" class="btn">↺ Επαναφορά</button></div>'+
    '<div class="lab-scenario-heading"><div><span class="eyebrow">'+esc(chosen.id)+' / '+esc(chosen.family)+'</span><h2>Ποιον πρέπει να ρωτήσει το ρομπότ;</h2><p>Πάτησε ένα διαθέσιμο μέλος στον χώρο ή χρησιμοποίησε τις ενέργειες παρακάτω.</p></div><span class="pill '+(custom?'warn':'muted')+'">'+(custom?'Δική σου παραλλαγή κόστους':'Αρχικές συνθήκες σεναρίου')+'</span></div>'+
    metrics(snapshot)+'<div class="lab-layout"><div>'+scene(snapshot,{interactive:true,busy,action:preview||snapshot.last})+sourceCards(snapshot,true,busy)+
    '<details class="lab-variants"><summary>Τι αλλάζει αν η διακοπή ενός μέλους κοστίζει περισσότερο;</summary><p>Αλλάζει μόνο το δημόσιο κόστος. Η κρυφή κατάσταση και η προγραμματισμένη γνώση των πηγών διατηρούνται. Η εφαρμογή των αλλαγών ξεκινά νέα εκπαιδευτική προσπάθεια.</p><div class="lab-cost-form"><div><label for="lab-cost-h2">Κόστος ερώτησης H2</label><input id="lab-cost-h2" type="number" min="0" max="1000" step="1" value="'+costs.H2+'"></div><div><label for="lab-cost-h3">Κόστος ερώτησης H3</label><input id="lab-cost-h3" type="number" min="0" max="1000" step="1" value="'+costs.H3+'"></div><button id="lab-cost-apply" class="btn">Εφαρμογή και επαναφορά</button></div></details></div>'+
    '<aside class="lab-control-panel"><span class="eyebrow">ΕΣΥ ΣΤΟΝ ΣΥΝΤΟΝΙΣΜΟ</span><h3>Η επόμενη κίνηση</h3><p class="lab-action-hint">'+(busy?'Αναπαράσταση ερώτησης / ενέργειας…':snapshot.done?'Η προσπάθεια ολοκληρώθηκε. Μπορείς να την επαναφέρεις ή να συγκρίνεις πολιτικές.':'Χρειάζεται νέα επιβεβαίωση ή μπορεί να προχωρήσει η εργασία;')+'</p>'+
    (error?'<div class="note warn" role="alert">'+esc(error)+'</div>':'')+
    '<button id="lab-follow" class="btn primary" '+(busy||snapshot.done?'disabled':'')+'>'+(next?'Δοκίμασε την πρόταση: '+esc(names[next.action])+(next.recipient?' → '+esc(next.recipient):''):'Η προσπάθεια ολοκληρώθηκε')+'</button><small class="lab-policy-note">Ευρετική πάνω στα δομημένα δεδομένα, όχι απόφαση μοντέλου.</small>'+
    '<div class="lab-manual-actions"><button id="lab-dispatch" class="btn" '+(busy||snapshot.done?'disabled':'')+'>Δοκίμασε αποστολή</button><button id="lab-escalate" class="btn" '+(busy||snapshot.done?'disabled':'')+'>Παραπομπή σε υπεύθυνο</button></div>'+outcome(snapshot)+
    '<div class="lab-comparison-callout"><h3>Ίδιο σενάριο, άλλη πολιτική</h3><p>Τρέξε τις τρεις ευρετικές στο ίδιο αρχικό στιγμιότυπο για να δεις τη διαφορά στις ερωτήσεις και στο κόστος.</p><button id="lab-compare" class="btn secondary" '+(busy?'disabled':'')+'>Σύγκρινε τις 3 πολιτικές</button></div></aside></div>'+
    (comparison?'<section class="lab-comparison"><h3>Εκπαιδευτική σύγκριση · δομημένα δεδομένα</h3><div class="table-scroll"><table><thead><tr><th>ΠΟΛΙΤΙΚΗ</th><th>ΕΡΩΤΗΣΕΙΣ</th><th>ΚΟΣΤΟΣ</th><th>ΕΚΒΑΣΗ</th><th>ΑΚΟΛΟΥΘΙΑ</th></tr></thead><tbody>'+comparison.map(x=>'<tr><td>'+esc(x.policy)+'</td><td>'+x.questions+'</td><td>'+x.cost+'</td><td>'+esc(results[x.result]||x.result)+'</td><td>'+esc(x.path.join(' · '))+'</td></tr>').join('')+'</tbody></table></div><p>Αυτός ο πίνακας εξηγεί τη συμπεριφορά των ευρετικών. Δεν αποτελεί live αξιολόγηση LLM ή ανεξάρτητο benchmark.</p></section>':'')+
    '<div class="lab-bottom-grid"><section><h3>Διάλογος ομάδας</h3>'+transcript(snapshot)+'</section><section><h3>Η δική σου ακολουθία</h3>'+timeline(snapshot)+(snapshot.history.length?'':'<p class="field-help">Δεν έχει γίνει ακόμη ενέργεια.</p>')+'</section></div><p class="lab-footnote">Η εκπαιδευτική δοκιμή κρατιέται μόνο στη μνήμη της σελίδας. Η επαναφορά ή η αλλαγή σελίδας τη διαγράφει. Οι συμβολικές κινήσεις δεν αποτελούν μοντέλο πλοήγησης ή χειρουργικής πράξης.</p></section>';
   $('#lab-case').value=chosen.id;$('#lab-policy').value=policy;
   $('#lab-case').onchange=()=>{chosen=cases.find(c=>c.id===$('#lab-case').value);costs=clone(chosen.public.query_cost);reset();};
   $('#lab-policy').onchange=()=>{policy=$('#lab-policy').value;render();};
   $('#lab-reset').onclick=reset;
   all('[data-ask]').forEach(el=>el.onclick=()=>act({action:'ask',recipient:el.dataset.ask}));
   all('[data-wait]').forEach(el=>el.onclick=()=>act({action:'wait',recipient:el.dataset.wait}));
   all('[data-person]').forEach(el=>{
    const choose=()=>{if(el.getAttribute('aria-disabled')==='false')act({action:'ask',recipient:el.dataset.person});};
    el.onclick=choose;el.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();choose();}};
   });
   $('#lab-follow').onclick=()=>{const action=sandbox.recommendation(policy);if(action)act(action);};
   $('#lab-dispatch').onclick=()=>act({action:'dispatch',recipient:null});
   $('#lab-escalate').onclick=()=>act({action:'escalate',recipient:null});
   $('#lab-compare').onclick=compare;
   $('#lab-cost-apply').onclick=()=>{
    const h2=$('#lab-cost-h2').value.trim(),h3=$('#lab-cost-h3').value.trim(),nextCosts={H2:Number(h2),H3:Number(h3)};
    if(!h2||!h3){error='Συμπλήρωσε και τα δύο κόστη.';render();return;}
    try{new Sandbox(chosen,nextCosts);costs=nextCosts;reset();}catch(e){error=e.message;render();}
   };
  }
  render();return ()=>{disposed=true;clearTimeout(timer);};
 }
 function mountReplay(root,session,launchLab,refresh){
  const rows=session.runs.filter(r=>r.steps?.length);
  if(!rows.length){root.innerHTML='<section class="card empty">Δεν υπάρχει ακόμη καταγεγραμμένος γύρος. Άνοιξε το διαδραστικό εργαστήριο για δοκιμή χωρίς API: <a href="#simulation">Άνοιγμα εργαστηρίου</a>.</section>';return ()=>{};}
  let row=rows[0],cursor=0,playing=false,speed=1,timer=null,disposed=false;
  const $=selector=>root.querySelector(selector);
  function stop(){playing=false;clearTimeout(timer);}
  function render(){
   if(disposed)return;clearTimeout(timer);
   const total=row.steps.length*2,max=total-1,snapshot=replaySnapshot(row,cursor);
   if(cursor>=max)playing=false;
   const phase=snapshot.after?'Μετά τη μετάβαση':'Πριν από την ενέργεια';
   const initial=session.dataset.cases.find(c=>c.id===row.case);
   root.innerHTML='<section class="lab-shell"><div class="lab-banner replay"><span class="lab-mode-tag">ΚΑΤΑΓΕΓΡΑΜΜΕΝΟ ΠΕΙΡΑΜΑ · ΜΟΝΟ ΠΡΟΒΟΛΗ</span><p>Τα κουμπιά αναπαράγουν τις αποθηκευμένες ενέργειες. Δεν αλλάζουν το πείραμα και δεν κάνουν νέες κλήσεις API. Η φάση «μετά» ανασυνθέτει την καταγεγραμμένη μετάβαση του simulator.</p></div>'+
    '<div class="lab-toolbar"><div class="lab-episode-field"><label for="episode-select">Επεισόδιο</label><select id="episode-select">'+rows.map(r=>'<option value="'+esc(r.episode_id)+'">'+esc(r.case+' / '+r.policy+' / '+r.profile.model+' / #'+r.repetition)+'</option>').join('')+'</select></div><button id="sim-refresh" class="btn">↻ Ανανέωση καταγραφής</button><button id="sim-lab-launch" class="btn secondary">Δοκίμασε εσύ το σενάριο ↗</button></div>'+
    '<div id="episode-body"><div class="lab-scenario-heading"><div><span class="eyebrow">'+esc(row.case)+' / '+esc(row.policy)+'</span><h2>Ποιον πρέπει να ρωτήσει το ρομπότ;</h2><p>'+esc(initial?.title||row.case)+'</p></div><span class="pill muted">'+esc(phase)+'</span></div>'+
    '<div class="lab-playback-controls"><button id="sim-first" class="btn" aria-label="Επιστροφή στην αρχή">↺ Αρχή</button><button id="sim-prev" class="btn" '+(cursor===0?'disabled':'')+'>← Προηγούμενο</button><button id="sim-play" class="btn primary">'+(playing?'Ⅱ Παύση':'▶ Αναπαραγωγή')+'</button><button id="sim-next" class="btn" '+(cursor===max?'disabled':'')+'>Επόμενο →</button><label for="sim-speed">Ταχύτητα</label><select id="sim-speed"><option value="0.5">0.5×</option><option value="1">1×</option><option value="2">2×</option></select></div>'+
    '<label class="lab-frame-label" for="sim-range">Γύρος '+(snapshot.turn+1)+' / '+row.steps.length+' · '+esc(phase)+' · t = '+esc(snapshot.publicInput.task.now)+'</label><input id="sim-range" type="range" min="0" max="'+max+'" value="'+cursor+'" aria-label="Φάση αναπαραγωγής">'+
    metrics(snapshot)+'<div class="lab-layout"><div>'+scene(snapshot,{action:snapshot.action,interactive:false})+sourceCards(snapshot,false,false)+'</div><aside class="lab-control-panel"><span class="eyebrow">'+(snapshot.after?'ΚΑΤΑΓΕΓΡΑΜΜΕΝΗ ΜΕΤΑΒΑΣΗ':'ΚΑΤΑΓΕΓΡΑΜΜΕΝΗ ΑΠΟΦΑΣΗ')+'</span><h3>'+esc(snapshot.action?(names[snapshot.action.action]||snapshot.action.action)+(snapshot.action.recipient?' → '+snapshot.action.recipient:''):'Δεν υπάρχει επικυρωμένη ενέργεια')+'</h3>'+
    (snapshot.after?outcome(snapshot):'<p>Πάτησε «Επόμενο» για να δεις την καταγεγραμμένη απάντηση ή την έκβαση αυτής της ενέργειας.</p>')+
    (snapshot.technical?'<div class="note warn">'+esc(snapshot.technical)+'</div>':'')+'<p class="lab-policy-note">Η κατάσταση προκύπτει από τις αποδεκτές αναφορές και τα δημόσια χρονικά στοιχεία. Δεν προβάλλεται η κρυφή αλήθεια πριν από την ενέργεια.</p></aside></div>'+
    '<div class="lab-bottom-grid"><section><h3>Διάλογος διαθέσιμος σε αυτή τη φάση</h3>'+transcript(snapshot)+'</section><section><h3>Ενέργειες έως αυτή τη φάση</h3>'+timeline(snapshot)+'</section></div></div></section>';
   $('#episode-select').value=row.episode_id;$('#sim-speed').value=String(speed);
   $('#episode-select').onchange=()=>{stop();row=rows.find(r=>r.episode_id===$('#episode-select').value);cursor=0;render();};
   $('#sim-play').onclick=()=>{if(playing)stop();else{if(cursor===max)cursor=0;playing=true;}render();};
   $('#sim-first').onclick=()=>{stop();cursor=0;render();};
   $('#sim-prev').onclick=()=>{stop();cursor=Math.max(0,cursor-1);render();};
   $('#sim-next').onclick=()=>{stop();cursor=Math.min(max,cursor+1);render();};
   $('#sim-range').oninput=e=>{stop();cursor=Math.max(0,Math.min(max,Number(e.target.value)));render();};
   $('#sim-speed').onchange=()=>{speed=Number($('#sim-speed').value);render();};
   $('#sim-lab-launch').onclick=()=>launchLab(clone(initial));
   $('#sim-refresh').onclick=refresh;
   if(playing)timer=setTimeout(()=>{cursor=Math.min(max,cursor+1);render();},1600/speed);
  }
  render();return ()=>{disposed=true;stop();};
 }
 return {Sandbox,valueOf,replaySnapshot,scene,mountLab,mountReplay};
})();

function simulationSnapshot(publicInput,step){
 const task=publicInput.task||{},messages=publicInput.messages||[],aliases=task.aliases||{};
 const canonical=id=>aliases[id]||id;
 const claims=Array.isArray(step?.accepted_evidence)?step.accepted_evidence:(step?.evidence_guard_applied?[]:(Array.isArray(step?.raw_output?.evidence)?step.raw_output.evidence:[]));
 const records=claims.filter(e=>e&&typeof e.message_id==='string'&&typeof e.subject==='string'&&typeof e.value==='boolean').map(e=>({claim:e,message:messages.find(m=>m.message_id===e.message_id)}));
 const bound=records.filter(x=>x.message&&canonical(x.claim.subject)===canonical(task.subject));
 const current=bound.filter(x=>Number.isFinite(x.message.time)&&Number.isFinite(x.message.valid_for)&&0<=task.now-x.message.time&&task.now-x.message.time<=x.message.valid_for);
 const latest=current.reduce((best,x)=>!best||x.message.time>best.message.time?x:best,null);
 const conflict=step?.raw_output?.conflict===true;
 const value=conflict?null:(latest?latest.claim.value:null);
 return {task,messages,claims,current,conflict,value,expired:bound.filter(x=>Number.isFinite(x.message.time)&&Number.isFinite(x.message.valid_for)&&task.now-x.message.time>x.message.valid_for).length};
}
function simulationBoard(publicInput,step,row,index){
 const v=simulationSnapshot(publicInput,step),t=v.task,action=step?.selected_action;
 const remaining=Number.isFinite(t.deadline)&&Number.isFinite(t.now)?t.deadline-t.now:null;
 const label=v.conflict?'Αντικρουόμενες αναφορές':v.value===true?'Υπάρχει ισχύουσα θετική αναφορά':v.value===false?'Υπάρχει ισχύουσα αρνητική αναφορά':v.expired?'Η προηγούμενη αναφορά έχει λήξει':'Χρειάζεται πληροφορία';
 const tone=v.conflict||v.value===false?'warn':v.value===true?'good':'muted';
 const actionLabels={ask:'Ερώτηση',wait:'Αναμονή',dispatch:'Πρόταση αποστολής',escalate:'Παραπομπή σε υπεύθυνο'};
 const actionText=action?(actionLabels[action.action]||action.action)+(action.recipient?' → '+action.recipient:''):'Δεν υπάρχει ακόμη απόφαση';
 const people=['H1','H2','H3'].map(h=>{
  const source=(t.sources||[]).includes(h),attempted=(t.attempted||[]).includes(h),available=source&&Number.isFinite(t.available_at?.[h])?t.available_at[h]<=t.now:null;
  const probability=t.probability_knows?.[h];
  const pct=Number.isFinite(probability)?Math.round(probability*100):null;
  const latest=[...v.messages].reverse().find(m=>m.speaker===h);
  return `<article class="sim-person ${action?.recipient===h?'is-target':''}"><div class="sim-person-top"><span class="sim-avatar" aria-hidden="true">${E(h)}</span><div><h3>${E(h)}</h3><small>${source?'Πιθανή πηγή επιβεβαίωσης':'Ομαδικό πλαίσιο / αίτημα'}</small></div>${source?pill(attempted?'Έχει ερωτηθεί':available===true?'Διαθέσιμος':available===false?'Διαθέσιμος στο t='+t.available_at[h]:'Άγνωστη διαθεσιμότητα',attempted?'muted':available?'good':'warn'):''}</div>${source?`<dl class="sim-person-metrics"><div><dt>Εκτίμηση ότι γνωρίζει</dt><dd>${pct===null?'—':pct+'%'}</dd></div><div><dt>Κόστος διακοπής</dt><dd>${E(t.query_cost?.[h]??'—')} <small>μον.</small></dd></div></dl><div class="sim-probability" aria-hidden="true"><span style="width:${pct===null?0:Math.max(0,Math.min(100,pct))}%"></span></div>`:''}${latest?`<p class="sim-last-message">«${E(latest.text)}»</p>`:'<p class="sim-last-message">Χωρίς μήνυμα στο διαθέσιμο ιστορικό.</p>'}${action?.recipient===h?'<div class="sim-target-label">← Επιλεγμένος αποδέκτης της επόμενης ενέργειας</div>':''}</article>`;
 }).join('');
 const history=row.steps.slice(0,index).filter(x=>x.transition).map(x=>`<li><span class="sim-event-time">t=${E(x.public_input.task.now)}</span><b>${E((actionLabels[x.selected_action.action]||x.selected_action.action)+(x.selected_action.recipient?' → '+x.selected_action.recipient:''))}</b><small>${E(statusNames[x.transition.result]||x.transition.result)}</small></li>`).join('');
 return `<section class="sim-board" aria-label="Προσομοίωση συντονισμού ομάδας"><div class="sim-board-heading"><div><span class="eyebrow">TEAM COORDINATION SIMULATOR</span><h2>Ποιον πρέπει να ρωτήσει το ρομπότ;</h2><p>Στιγμιότυπο πριν από την επιλεγμένη ενέργεια. Σχηματική διάταξη, χωρίς δεδομένα φυσικής θέσης.</p></div>${pill('ΣΥΝΘΕΤΙΚΗ ΠΡΟΣΟΜΟΙΩΣΗ','muted')}</div><div class="sim-clock"><span><small>ΧΡΟΝΟΣ</small><b>t = ${E(t.now??'—')}</b></span><span><small>ΠΡΟΘΕΣΜΙΑ</small><b>t = ${E(t.deadline??'—')}</b></span><span><small>ΒΗΜΑΤΑ ΕΩΣ ΤΗΝ ΠΡΟΘΕΣΜΙΑ</small><b class="${remaining!==null&&remaining<=1?'deadline-close':''}">${E(remaining??'—')}</b></span><span><small>ΠΟΛΙΤΙΚΗ</small><b>${E(policyLabels[row.policy]||row.policy)}</b></span></div><div class="sim-workspace"><div class="sim-stage"><div class="sim-floor-label">Χώρος προετοιμασίας εξοπλισμού</div><div class="sim-robot"><div class="robot-antenna"></div><div class="robot-head"><i></i><i></i></div><div class="robot-base"></div><b>Ρομπότ συντονιστής</b><small>Διαθέσιμος διάλογος → απόφαση</small></div><div class="sim-connection" aria-hidden="true"><span>Πληροφορία ελέγχου</span></div><div class="sim-cart"><div class="cart-outline"><span class="cart-kit">KIT</span></div><div class="cart-wheels" aria-hidden="true">●&emsp;●</div><b>Καρότσι ${E(t.subject??'—')}</b><small>Αντικείμενο της τρέχουσας εργασίας</small></div><div class="sim-state">${pill(label,tone)}<small>Κατάσταση βάσει των αποδεκτών αναφορών του μοντέλου· δεν είναι η κρυφή αλήθεια του simulator.</small></div></div><aside class="sim-decision"><span class="eyebrow">ΕΠΟΜΕΝΗ ΕΝΕΡΓΕΙΑ</span><h3>${E(actionText)}</h3><p>${action?.action==='ask'?'Ο συντονιστής ζητά νέα πληροφορία από το επιλεγμένο μέλος.':action?.action==='wait'?'Ο συντονιστής περιμένει τη διαθεσιμότητα της επιλεγμένης πηγής.':action?.action==='dispatch'?'Η προτεινόμενη αποστολή ελέγχεται στη συνέχεια από τον simulator.':action?.action==='escalate'?'Ο συντονιστής σταματά την αυτόματη εκτέλεση και παραπέμπει την εργασία σε υπεύθυνο.':'Η απόφαση θα εμφανιστεί όταν καταγραφεί η απόκριση.'}</p><dl><div><dt>Ισχύουσες αποδεκτές αναφορές</dt><dd>${v.current.length}</dd></div><div><dt>Αναφορές που απέρριψε το φίλτρο</dt><dd>${E(step?.rejected_evidence_count??0)}</dd></div></dl><p class="sim-research-note">Μελετάμε την επιλογή πληροφορίας και αποδέκτη, όχι την κίνηση του ρομπότ.</p></aside></div><div class="sim-people">${people}</div><details class="sim-history"><summary>Προηγούμενες ενέργειες στο επεισόδιο · ${index}</summary><ol>${history||'<li>Αρχικό στιγμιότυπο — δεν έχει προηγηθεί ενέργεια.</li>'}</ol></details></section>`;
}

function detailDialogue(s,simulation=false){if(simulation){interactiveDispose=InteractiveSim.mountReplay($('#detail-content'),s,scenario=>{pendingLabCase=scenario;navigate('simulation');},safe(()=>experimentDetail(s.id)));return;}if(!s.runs.length){$('#detail-content').innerHTML='<section class="card"><div class="empty">Δεν έχει ξεκινήσει ακόμη επεισόδιο.</div></section>';return;}const row=s.runs.find(r=>r.episode_id===selectedEpisode)||s.runs[0];selectedEpisode=row.episode_id;$('#detail-content').innerHTML=`<section class="card"><div class="card-top"><h2>${simulation?'Προσομοίωση ομάδας — βήμα προς βήμα':'Επιθεώρηση επεισοδίου'}</h2><a href="/api/experiments/${s.id}/export?format=events">Events CSV ↓</a></div><label for="episode-select">Περίπτωση / πολιτική / μοντέλο / επανάληψη</label><select id="episode-select">${s.runs.map(r=>`<option value="${r.episode_id}" ${r.episode_id===row.episode_id?'selected':''}>${E(r.case+' / '+r.policy+' / '+r.profile.model+' / #'+r.repetition+' / '+r.status)}</option>`).join('')}</select><div id="episode-body"></div></section>`;$('#episode-select').onchange=()=>{selectedEpisode=$('#episode-select').value;detailDialogue(s);};const render=i=>{const st=row.steps[i];const initial=s.dataset.cases.find(c=>c.id===row.case);const publicInput=st?.public_input||{task:initial.public,messages:initial.messages};const task=publicInput.task,action=st?.selected_action;$('#episode-body').innerHTML=`<div class="actions" style="margin:18px 0">${status(row.status)}${pill(`Σύνολο επεισοδίου · ερωτήσεις: ${row.questions||0}`)}${pill(`Κόστος: ${row.query_cost||0}`)}${pill(`Κλήσεις: ${row.api_calls}`)}</div><label for="step-range">Γύρος ${i+1} / ${Math.max(1,row.steps.length)} · t = ${task.now} · αντικείμενο ${E(task.subject)}</label><div class="sim-step-actions"><button id="sim-prev" class="btn" ${i===0?'disabled':''}>← Προηγούμενο</button><span>Καταγεγραμμένος γύρος ${i+1} / ${Math.max(1,row.steps.length)}</span><button id="sim-next" class="btn" ${i>=row.steps.length-1?'disabled':''}>Επόμενο →</button></div><input id="step-range" type="range" min="0" max="${Math.max(0,row.steps.length-1)}" value="${i}">${simulationBoard(publicInput,st,row,i)}<div class="grid"><div><h3>Διάλογος διαθέσιμος στον συντονιστή</h3><div class="chat">${publicInput.messages.map(m=>`<div class="message ${m.speaker==='ROBOT'?'robot':''}"><small>${E(m.speaker)} · ${E(m.message_id)} · t=${m.time}</small>${E(m.text)}</div>`).join('')}</div></div><div>${simulation?'<details class="sim-analysis"><summary>Τεκμηρίωση εξαγωγής και διαγνωστικοί έλεγχοι</summary>':''}<h3>Αρχική εξαγωγή μοντέλου</h3><div class="evidence">${(Array.isArray(st?.raw_output?.evidence)?st.raw_output.evidence:[]).map(e=>pill(`${e?.subject}: ${e?.value} · ${e?.message_id}`,e?.value?'good':'warn')).join('')||pill('Χωρίς ρητές αναφορές')}${st?.raw_output?.conflict?pill('ΑΝΤΙΦΑΣΗ','bad'):''}</div>${st?.evidence_audit?`<h3 style="margin-top:18px">Επιβεβαιώσεις για τον controller</h3><p class="field-help">${st.evidence_guard_applied?'Συντηρητικό φίλτρο ενεργό':'Αρχική εξαγωγή — το φίλτρο δεν εφαρμόζεται'}</p><div class="evidence">${(st.accepted_evidence||[]).map(e=>pill(`${e.subject}: ${e.value} · ${e.message_id}`,e.value?'good':'warn')).join('')||pill('Άγνωστο / χωρίς αποδεκτή επιβεβαίωση')}</div><details><summary>Έλεγχος τεκμηρίωσης ανά αναφορά</summary><pre class="json-view">${E(JSON.stringify(st.evidence_audit,null,2))}</pre></details>`:''}<div class="action-box"><small>ΕΠΙΛΕΓΜΕΝΗ ΕΝΕΡΓΕΙΑ</small>${E(action?`${action.action}${action.recipient?' → '+action.recipient:''}`:'Αναμονή απόκρισης / δεν υπάρχει απόφαση')}<small style="margin-top:10px">${E(st?.transition?.result||st?.error||'')}</small></div><h3 style="margin-top:22px">Έλεγχοι ανά γύρο</h3>${Object.entries(st?.extraction_checks||{}).map(([k,v])=>`<p style="font-size:11px;margin-bottom:7px">${pill(v?'OK':'ΣΦΑΛΜΑ',v?'good':'bad')} ${E(k)}</p>`).join('')||'<p class="field-help">Δεν έχει ολοκληρωθεί εξαγωγή.</p>'}${st?.accepted_extraction_checks?`<h3>Έλεγχοι μετά το φίλτρο</h3>${Object.entries(st.accepted_extraction_checks).map(([k,v])=>`<p>${pill(v?'OK':'ΣΦΑΛΜΑ',v?'good':'bad')} ${E(k)}</p>`).join('')}`:''}<details><summary>Πλήρης καταγραφή απόφασης</summary><pre class="json-view">${E(JSON.stringify(st||{},null,2))}</pre></details>${simulation?'</details>':''}</div></div><div class="note">Τα ποσοστά και η διαθεσιμότητα είναι δημόσια δεδομένα εισόδου. Η πραγματική γνώση των μελών και η αλήθεια του simulator δεν δίνονται στο μοντέλο.</div>`;$('#step-range').oninput=e=>render(Number(e.target.value));$('#sim-prev').onclick=()=>render(Math.max(0,i-1));$('#sim-next').onclick=()=>render(Math.min(Math.max(0,row.steps.length-1),i+1));};render(Math.max(0,row.steps.length-1));}
async function scenarios(){dataset=await api('/api/dataset');selectedScenario=dataset.cases.some(c=>c.id===selectedScenario)?selectedScenario:dataset.cases[0].id;$('#main').innerHTML=pageHeader('Σενάρια & ετικέτες','Σχεδίασε νέες περιπτώσεις και έλεγξε τα annotations. Τα ήδη δημιουργημένα πειράματα κρατούν το δικό τους στιγμιότυπο.',`<div class="actions"><button class="btn" id="dataset-export">↓ Dataset JSON</button><button class="btn" id="dataset-import">↑ Εισαγωγή</button><button class="btn primary" id="scenario-new">＋ Νέο σενάριο</button></div>`)+`<div class="note warn" style="margin-bottom:23px">Τα 8 candidate σχέδια δεν είναι ανεξάρτητο benchmark. Για evaluation απαιτούνται νέες οικογένειες, δύο δηλωμένοι reviewers και ανθρώπινος έλεγχος για διαρροή μεταξύ συνόλων.</div><div class="scenario-layout"><div class="scenario-list">${dataset.cases.map(c=>`<div class="scenario-item ${c.id===selectedScenario?'selected':''}" data-case="${E(c.id)}"><div class="split-label"><b>${E(c.id)}</b>${pill(c.split,c.split==='development'?'good':'warn')}</div><b>${E(c.title)}</b><small>${E(c.family)}</small></div>`).join('')}</div><section class="card"><div class="card-top"><h2 id="editor-title"></h2><button id="scenario-save" class="btn secondary">Αποθήκευση αλλαγών</button></div><p class="field-help">Ο editor περιλαμβάνει δημόσια observations και ξεχωριστά annotations/private για το simulator. Τα private δεν στέλνονται στα μοντέλα. Η επικύρωση σχήματος δεν ελέγχει τη σημασιολογική ορθότητα των ετικετών.</p><label for="case-editor">Ορισμός σεναρίου JSON</label><textarea id="case-editor" class="code" spellcheck="false"></textarea><details><summary>Review metadata του dataset</summary><label for="review-editor">Ονόματα reviewers και δήλωση ανεξάρτητου ελέγχου</label><textarea id="review-editor" class="code" style="min-height:150px" spellcheck="false">${E(JSON.stringify(dataset.review||{reviewers:[],independently_reviewed:false},null,2))}</textarea><button id="review-save" class="btn" style="margin-top:10px">Αποθήκευση review metadata</button></details></section></div><input id="file-input" type="file" accept=".json,application/json" class="hidden">`;
function select(id){selectedScenario=id;const c=dataset.cases.find(c=>c.id===id);$('#editor-title').textContent=c.id+' / '+c.title;$('#case-editor').value=JSON.stringify(c,null,2);$$('[data-case]').forEach(x=>x.classList.toggle('selected',x.dataset.case===id));}$$('[data-case]').forEach(x=>x.onclick=()=>select(x.dataset.case));select(selectedScenario);
$('#scenario-save').onclick=safe(async()=>{const c=JSON.parse($('#case-editor').value);const next=structuredClone(dataset);next.cases[next.cases.findIndex(x=>x.id===selectedScenario)]=c;await api('/api/dataset',{dataset:next});toast('Το σενάριο αποθηκεύτηκε. Τα προηγούμενα πειράματα διατηρούνται.');await scenarios();});$('#scenario-new').onclick=()=>{const c=structuredClone(dataset.cases.find(x=>x.id===selectedScenario));let n=1;while(dataset.cases.some(x=>x.id==='X'+String(n).padStart(3,'0')))n++;c.id='X'+String(n).padStart(3,'0');c.title='Νέο σενάριο — χρειάζεται έλεγχο';c.split='candidate';dataset.cases.push(c);selectedScenario=c.id;$('#editor-title').textContent=c.id+' / Νέο προσχέδιο';$('#case-editor').value=JSON.stringify(c,null,2);toast('Το νέο προσχέδιο βασίζεται στην επιλεγμένη περίπτωση. Άλλαξε κείμενο, οικογένεια και ετικέτες πριν την αποθήκευση.');};$('#review-save').onclick=safe(async()=>{const next=structuredClone(dataset);next.review=JSON.parse($('#review-editor').value);await api('/api/dataset',{dataset:next});dataset=next;toast('Τα review metadata αποθηκεύτηκαν ως δική σου δήλωση.');});$('#dataset-export').onclick=()=>download('rss2027_dataset.json',JSON.stringify(dataset,null,2));$('#dataset-import').onclick=()=>$('#file-input').click();$('#file-input').onchange=safe(async e=>{const file=e.target.files[0];if(!file)return;const next=JSON.parse(await file.text());await api('/api/dataset',{dataset:next});selectedScenario=null;toast('Το dataset εισήχθη. Τα παλαιότερα πειράματα κρατούν τα δικά τους δεδομένα.');await scenarios();});}
async function protocol(){const docs=state.documents;$('#main').innerHTML=pageHeader('Πρωτόκολλο & βιβλιογραφία','Το ερώτημα, οι υποθέσεις και τα όρια της μελέτης παραμένουν δίπλα στα πειράματα.')+`<section class="card"><label for="document-select">Έγγραφο</label><select id="document-select">${docs.map(n=>`<option>${E(n)}</option>`).join('')}</select><article id="document-text" class="doc" style="margin-top:26px"></article></section>`;async function show(){const d=await api('/api/docs/'+$('#document-select').value);$('#document-text').innerHTML=d.text.split('\n').map(line=>{const h=line.match(/^(#{1,3}) (.*)/);return h?`<h${h[1].length}>${E(h[2])}</h${h[1].length}>`:`<p>${E(line)}</p>`;}).join('');}$('#document-select').onchange=safe(show);await show();}
async function settings(){$('#main').innerHTML=pageHeader('Ρυθμίσεις περιβάλλοντος','Τα κλειδιά διαβάζονται τοπικά από μεταβλητές περιβάλλοντος. Δεν χρειάζεται να τα αποθηκεύσεις στο project.')+`<div class="grid"><section class="card"><div class="card-top"><h2>API keys</h2><button id="refresh-keys" class="btn">↻ Ανανέωση ελέγχου</button></div>${providerRows()}<div class="note info" style="margin-top:20px">Στα Windows ελέγχεται και η αποθηκευμένη μεταβλητή χρήστη, ακόμη κι αν το VS Code άνοιξε πριν οριστεί το κλειδί. Η ένδειξη ελέγχει παρουσία κλειδιού, όχι πρόσβαση, χρέωση ή εγκυρότητα.</div><h3 style="margin-top:24px">Καταχώριση κλειδιού μία φορά</h3><p class="field-help">Τρέξε το <b>SETUP_KEY.ps1</b> από PowerShell. Η πληκτρολόγηση κρύβεται. Επιλέγεις OpenAI, Anthropic ή Gemini και επικολλάς το αντίστοιχο κλειδί μόνο στο τοπικό terminal.</p><pre class="json-view">powershell -ExecutionPolicy Bypass -File .\SETUP_KEY.ps1</pre><p class="field-help">Οι τρεις adapters χρησιμοποιούν επίσημα endpoints και αυστηρή τοπική επικύρωση. Η πρόσβαση/συμβατότητα του συγκεκριμένου μοντέλου ελέγχεται με μία μικρή live δοκιμή από τον δικό σου λογαριασμό.</p></section><div><section class="card"><h2>Τοπική αποθήκευση</h2><p class="field-help">Φάκελος workspace</p><pre class="json-view">${E(state.workspace)}</pre><p class="field-help">Αντέγραψε ολόκληρο τον φάκελο για backup. Κράτησε την έκδοση κώδικα μαζί με τα παγωμένα πειράματα. Δεν αποστέλλονται δεδομένα σε υπηρεσία φιλοξενίας.</p></section><section class="card"><h2>Προηγούμενα αποτελέσματα</h2><p class="field-help">Εισαγωγή session.json από v0.3–v0.7 ως read-only αρχείο τεκμηρίωσης. Δεν γίνεται μετατροπή, νέα βαθμολόγηση ή συνέχιση με διαφορετικό κώδικα.</p><button id="archive-import" class="btn">↑ Εισαγωγή παλιού session.json</button><input id="archive-file" type="file" accept=".json,application/json" class="hidden"><div id="archive-result" class="field-help"></div></section></div></div>`;$('#refresh-keys').onclick=safe(async()=>{await loadState();await settings();toast('Ο έλεγχος μεταβλητών ανανεώθηκε, χωρίς κλήση API.');});$('#archive-import').onclick=()=>$('#archive-file').click();$('#archive-file').onchange=safe(async e=>{const file=e.target.files[0];if(!file)return;const result=await api('/api/import-session',{session:JSON.parse(await file.text())});$('#archive-result').textContent=`Αποθηκεύτηκε αρχείο τεκμηρίωσης με ${result.run_count} προσπάθειες. ID: ${result.archive_id}`;});}

async function interactiveLab(){
 const data=await api('/api/dataset'),scenario=pendingLabCase;pendingLabCase=null;
 $('#main').innerHTML=pageHeader('Διαδραστικό εργαστήριο','Πάρε εσύ τις αποφάσεις του συντονιστή και δες πώς η πληροφορία, το κόστος και η προθεσμία αλλάζουν την εξέλιξη.')+'<div id="interactive-lab"></div>';
 interactiveDispose=InteractiveSim.mountLab($('#interactive-lab'),data,{scenario});
}

async function route(){clearTimeout(poll);disposeInteractive();const route=location.hash.slice(1)||'home';const key=route.split('/')[0];$$('nav a').forEach(a=>a.classList.toggle('active',a.dataset.route===(key==='experiment'?'experiments':key)));$('#breadcrumb').textContent='Ερευνητικός χώρος / '+(routes[key]||'Επιθεώρηση πειράματος');await loadState();if(key==='experiment'){await experimentDetail(route.split('/')[1]);return;}const fn={home,simulation:interactiveLab,new:newExperiment,experiments:experimentList,scenarios,protocol,settings}[key]||home;await fn();}
let booting=true;
function startupFailure(error){
 const main=document.getElementById('main');
 if(!main)return;
 const card=document.createElement('section');card.className='card';
 const title=document.createElement('h1');title.textContent='Δεν ήταν δυνατή η φόρτωση';
 const detail=document.createElement('p');detail.textContent=error?.message||String(error||'Άγνωστο σφάλμα εκκίνησης');
 const help=document.createElement('p');help.textContent='Κράτησε ανοιχτό το παράθυρο Python, άνοιξε τη διεύθυνση που γράφει Open: και πάτησε Ctrl+F5.';
 const retry=document.createElement('button');retry.className='btn primary';retry.textContent='Επαναφόρτωση';retry.onclick=()=>window.location.reload();
 card.append(title,detail,help,retry);main.replaceChildren(card);
 const key=document.getElementById('global-key');if(key){key.textContent='Αποτυχία φόρτωσης';key.className='pill bad';}
}
const startupTimer=setTimeout(()=>{if(booting)startupFailure(Error('Η εκκίνηση καθυστέρησε περισσότερο από το αναμενόμενο.'));},20000);
$('#dialog-close').onclick=()=>$('#dialog').close();
window.addEventListener('hashchange',safe(route));
window.addEventListener('error',event=>{if(booting)startupFailure(event.error||Error(event.message||'Σφάλμα JavaScript'));});
window.addEventListener('unhandledrejection',event=>{if(booting)startupFailure(event.reason);else toast(event.reason?.message||'Σφάλμα εφαρμογής',true);});
route().then(()=>{booting=false;clearTimeout(startupTimer);}).catch(error=>{clearTimeout(startupTimer);startupFailure(error);});
})();

