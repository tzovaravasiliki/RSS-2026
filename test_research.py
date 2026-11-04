"""Research workflow contracts: frozen sources, no implicit billing, honest audits."""
import copy
import csv
import io
import json
from pathlib import Path
import re
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
import zipfile
from unittest.mock import patch

import app
import catalog
import contracts
import engine
from manager import Manager
import research
from storage import Store


def request(mode='live', ids=None):
    return {'name':'Research test', 'initial_call_cap':6,
            'config':{'mode':mode,'purpose':'development','case_ids':ids or ['D09'],
                      'policies':['cost_aware','always_reverify','cost_blind','llm'],
                      'models':[{'provider':'openai','model':'gpt-5-mini-2025-08-07'}],
                      'repeats':1,'max_steps':8,'evidence_mode':'explicit_support'}}


def observed_session():
    data=catalog.load_builtin()
    plan=engine.plan(request()['config'],data)
    condition=next(p for p in plan['pairs'] if p['policy']=='cost_aware')
    case=next(c for c in data['cases'] if c['id']=='D09')
    scenario=catalog.scenario(case)
    public=contracts.observation(scenario.public,contracts.initial_messages(scenario,case))
    raw={'evidence':[{'message_id':'m001','subject':'C1','value':False}],
         'conflict':False,'decision':{'action':'ask','recipient':'H3'}}
    step={'public_input':public,'raw_output':raw,'accepted_evidence':[],
          'evidence_guard_applied':True,'selected_action':{'action':'ask','recipient':'H3'},
          'status':'completed','stage':'action_execution',
          'extraction_checks':{'evidence_exact':False,'current_status_correct':False,'conflict_correct':True},
          'accepted_extraction_checks':{'evidence_exact':True,'current_status_correct':True,'conflict_correct':True}}
    row=dict(condition,steps=[step],status='paused_budget',api_calls=1,questions=1,query_cost=1)
    return {'id':'a'*32,'name':'Audit test','created_at':'test','status':'paused_budget',
            'config':plan['config'],'dataset':data,'dataset_sha256':plan['dataset_sha256'],
            'fingerprint':plan['fingerprint'],'plan':plan['pairs'],'runs':[row]}


class ResearchPlanTests(unittest.TestCase):
    def setUp(self):
        self.data=catalog.load_builtin()

    def test_cost_variant_freezes_copy_without_changing_source_or_truth(self):
        original=copy.deepcopy(self.data)
        body=request();body['cost_overrides']={'D09':{'H2':1,'H3':9}}
        plan=research.prepare(body,self.data)
        self.assertEqual(self.data,original)
        changed=next(c for c in plan['dataset']['cases'] if c['id']=='D09')
        before=next(c for c in self.data['cases'] if c['id']=='D09')
        self.assertEqual(changed['private'],before['private'])
        self.assertEqual(changed['public']['query_cost'],{'H2':1,'H3':9})
        self.assertEqual(plan['source_sha256'],contracts.digest(original))
        self.assertNotEqual(plan['source_sha256'],plan['study_design']['dataset_sha256'])
        self.assertEqual(plan['episodes'],4)
        self.assertEqual(plan['maximum_calls'],32)

    def test_review_hash_is_deterministic_and_rejects_stale_designs(self):
        body=request();plan=research.prepare(body,self.data)
        reviewed=dict(body,expected_plan_sha256=plan['plan_sha256'])
        self.assertEqual(research.prepare(reviewed,self.data)['plan_sha256'],plan['plan_sha256'])
        changed=copy.deepcopy(reviewed);changed['config']['repeats']=2
        with self.assertRaisesRegex(ValueError,'review|Review|Preview'):research.prepare(changed,self.data)
        changed=copy.deepcopy(reviewed);changed['name']='Another question'
        with self.assertRaises(ValueError):research.prepare(changed,self.data)
        changed=copy.deepcopy(self.data);changed['cases'][0]['title']+=' changed'
        with self.assertRaises(ValueError):research.prepare(reviewed,changed)
        with self.assertRaisesRegex(ValueError,'source dataset changed'):
            research.prepare(dict(body,expected_source_sha256='stale'),self.data)

    def test_bad_budgets_costs_and_unselected_variants_are_rejected(self):
        for value in [0,-1,True,1.5,10001]:
            with self.subTest(value=value),self.assertRaises(ValueError):
                research.prepare(dict(request(),initial_call_cap=value),self.data)
        for costs in [{'H2':True,'H3':1},{'H2':float('nan'),'H3':1},{'H2':1},{'H2':1,'H3':-1}]:
            with self.subTest(costs=costs),self.assertRaises(ValueError):
                research.prepare(dict(request(),cost_overrides={'D09':costs}),self.data)
        with self.assertRaises(ValueError):
            research.prepare(dict(request(),cost_overrides={'D10':{'H2':1,'H3':2}}),self.data)

    def test_variants_do_not_inherit_evaluation_review(self):
        body=request();body['config']['purpose']='evaluation'
        body['cost_overrides']={'D09':{'H2':1,'H3':9}}
        with self.assertRaisesRegex(ValueError,'newly reviewed dataset'):research.prepare(body,self.data)
        with self.assertRaises(ValueError):research.prepare(request('live',['E01']),self.data)

    def test_draft_creation_does_not_start_worker_or_read_credentials(self):
        with tempfile.TemporaryDirectory() as tmp,patch('providers.read_key',side_effect=AssertionError('No key read')):
            store=Store(tmp);manager=Manager(store,call=lambda *a: self.fail('No model call'))
            before=store.dataset();prepared=research.prepare(request(),before,'b'*32)
            session=manager.create(prepared['config'],prepared['name'],prepared['dataset'],prepared['study_design'])
            self.assertIsNone(manager.thread)
            self.assertEqual(session['status'],'ready')
            self.assertEqual(session['runs'],[])
            self.assertEqual(store.dataset(),before)
            self.assertEqual(session['study_design']['source']['kind'],'frozen_experiment')
            self.assertEqual(store.get(session['id'])['study_design'],session['study_design'])

    def test_offline_plan_is_explicitly_not_a_model_comparison(self):
        plan=research.prepare(request('offline'),self.data)
        self.assertEqual(plan['initial_call_cap'],0)
        self.assertEqual(plan['maximum_calls'],0)
        self.assertEqual(plan['config']['models'][0]['provider'],'fixture')
        self.assertTrue(any('not LLM' in w for w in plan['warnings']))


class DecisionAuditTests(unittest.TestCase):
    def test_controllers_share_the_recorded_admitted_input_not_model_errors(self):
        session=observed_session();before=copy.deepcopy(session)
        audit=research.decision_audit(session);row=audit['observations'][0]
        self.assertEqual(audit['scored_turns'],1)
        self.assertEqual(audit['new_provider_calls'],0)
        self.assertEqual(row['admitted_status'],None)
        self.assertEqual(row['actions']['cost_aware'],{'action':'ask','recipient':'H3'})
        self.assertEqual(row['actions']['cost_blind'],{'action':'ask','recipient':'H2'})
        self.assertEqual(row['immediate_query_cost']['cost_aware'],1)
        self.assertEqual(row['immediate_query_cost']['cost_blind'],5)
        self.assertNotIn('expected_outcome_met',row)
        self.assertEqual(session,before)

    def test_private_truth_and_annotations_cannot_change_the_diagnostic(self):
        session=observed_session();expected=research.decision_audit(session)
        changed=copy.deepcopy(session)
        changed['dataset']={'private':'MUTATED_SECRET','annotations':False}
        with patch('providers.infer',side_effect=AssertionError('No provider')):
            self.assertEqual(research.decision_audit(changed),expected)

    def test_conservative_conflict_is_preserved_after_claims_are_removed(self):
        session=observed_session();case=next(c for c in session['dataset']['cases'] if c['id']=='D05')
        scenario=catalog.scenario(case);public=contracts.observation(scenario.public,contracts.initial_messages(scenario,case))
        raw=contracts.fixture(scenario.public,public)
        step=session['runs'][0]['steps'][0]
        step.update(public_input=public,raw_output=raw,accepted_evidence=[])
        audit=research.decision_audit(session)
        self.assertEqual(audit['scored_turns'],1)
        self.assertIsNone(audit['observations'][0]['admitted_status'])

    def test_missing_invalid_and_inflight_extractions_stay_visible_as_skipped(self):
        session=observed_session();row=session['runs'][0]
        row['steps'].append({'status':'in_flight','stage':'provider'})
        row['steps'].append({'status':'error','stage':'output_validation','public_input':{},'raw_output':{}})
        del row['steps'][0]['accepted_evidence']
        audit=research.decision_audit(session)
        self.assertEqual(audit['scored_turns'],0)
        self.assertEqual(audit['skipped_turns'],3)
        self.assertEqual(audit['skipped'][1]['saved_status'],'in_flight')

    def test_admitted_claims_must_be_an_actual_recorded_subset(self):
        session=observed_session();session['runs'][0]['steps'][0]['accepted_evidence']=[
            {'message_id':'m001','subject':'C1','value':True}]
        self.assertEqual(research.decision_audit(session)['skipped_turns'],1)

    def test_legacy_raw_mode_and_changed_evaluator_are_explicit(self):
        session=observed_session();session['config']['evidence_mode']='raw'
        step=session['runs'][0]['steps'][0];step.pop('accepted_evidence');step['evidence_guard_applied']=False
        session['fingerprint']={'sha256':'legacy'}
        audit=research.decision_audit(session)
        self.assertFalse(audit['same_evaluator_as_source'])
        self.assertFalse(audit['observations'][0]['admitted_status'])

    def test_csv_escapes_spreadsheet_formula_fields(self):
        session=observed_session();session['runs'][0]['profile']['model']='=DANGEROUS()'
        rows=list(csv.DictReader(io.StringIO(research.audit_csv(session).lstrip('\ufeff'))))
        self.assertEqual(len(rows),4)
        self.assertTrue(all(r['model']=="'=DANGEROUS()" for r in rows))

    def test_report_distinguishes_technical_limits_pending_and_scenario_counts(self):
        session=observed_session();a=copy.deepcopy(session['runs'][0]);b=copy.deepcopy(a)
        a.update(status='error',expected_outcome_met=False)
        condition=next(p for p in session['plan'] if p['policy']=='always_reverify')
        b.update(condition,status='deadline_missed',expected_outcome_met=False)
        session['runs']=[a,b]
        result=research.report(session)
        self.assertEqual(result['unique_case_ids'],1)
        self.assertEqual(sum(g['technical_failures'] for g in result['conditions']),1)
        self.assertEqual(sum(g['limit_failures'] for g in result['conditions']),1)
        self.assertEqual(sum(g['not_started'] for g in result['conditions']),2)
        self.assertTrue(result['dataset_integrity_matches'])
        session['dataset']['cases'][0]['title']+=' tampered'
        self.assertFalse(research.report(session)['dataset_integrity_matches'])

    def test_returned_versions_and_usage_are_reported_without_silent_pooling(self):
        session=observed_session();row=session['runs'][0]
        row['steps'][0]['returned_model']='version-one'
        row['steps'].append(dict(copy.deepcopy(row['steps'][0]),returned_model='version-two'))
        report=research.report(session)
        group=next(g for g in report['conditions'] if g['condition'].endswith('cost_aware'))
        self.assertEqual(group['returned_models'],['version-one','version-two'])
        self.assertTrue(any('Multiple returned model versions' in w for w in report['warnings']))
        markdown=research.markdown_report(session)
        self.assertIn('version-one, version-two',markdown)
        self.assertIn('actual batch budgets',markdown)

    def test_markdown_text_is_escaped_and_design_json_remains_literal(self):
        session=observed_session();session['name']='<script>unsafe</script>'
        session['study_design']={'question':'<script>design</script>```'}
        markdown=research.markdown_report(session)
        self.assertIn('Experiment: &lt;script&gt;unsafe&lt;/script&gt;',markdown)
        self.assertIn('    "question":',markdown)

    def test_exports_contain_study_audit_and_caveats_without_credentials(self):
        session=observed_session()
        with patch('providers.read_key',return_value='CREDENTIAL_MUST_NOT_APPEAR'):
            blob,_,_=app.export(session,'zip')
        with zipfile.ZipFile(io.BytesIO(blob)) as z:
            self.assertTrue({'study_design.json','decision_audit.json','decision_audit.csv','research_report.md'}<=set(z.namelist()))
            markdown=z.read('research_report.md').decode()
            self.assertIn('not independent cases',markdown)
            self.assertIn('no counterfactual outcome',markdown)
            self.assertNotIn('CREDENTIAL_MUST_NOT_APPEAR',b''.join(z.read(n) for n in z.namelist()).decode())


class ResearchHTTPTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.calls=[]
        def inference(profile,public,max_tokens):
            self.calls.append(copy.deepcopy(public))
            humans=[m for m in public['messages'] if m['speaker']!='ROBOT']
            latest=humans[-1]
            evidence=[]
            if 'Επανέλεγξα' in latest['text']:
                evidence=[{'message_id':latest['message_id'],'subject':public['task']['subject'],
                           'value':'δεν έχει' not in latest['text']}]
            return {'output':{'evidence':evidence,'conflict':False,'decision':{
                'action':'dispatch' if evidence and evidence[0]['value'] else 'escalate','recipient':None}},'usage':{}}
        self.server=app.make_server(self.tmp.name,0,call=inference)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.url='http://127.0.0.1:'+str(self.server.server_address[1])
        page=urllib.request.urlopen(self.url).read().decode()
        self.token=re.search(r'name="workbench-token" content="([^"]+)"',page)[1]

    def tearDown(self):
        worker=self.server.workbench_manager.thread
        if worker:worker.join(3)
        self.server.shutdown();self.server.server_close();self.thread.join();self.tmp.cleanup()

    def post(self,path,value):
        req=urllib.request.Request(self.url+path,data=json.dumps(value).encode(),
            headers={'Content-Type':'application/json','X-Workbench-Token':self.token})
        return json.load(urllib.request.urlopen(req))

    def test_review_create_report_are_free_and_source_remains_unmodified(self):
        body=request();body['cost_overrides']={'D09':{'H2':2,'H3':8}}
        before=contracts.digest(self.server.workbench_store.dataset())
        plan=self.post('/api/study/plan',body)
        self.assertNotIn('dataset',plan)
        with self.assertRaises(urllib.error.HTTPError):self.post('/api/study/create',body)
        session=self.post('/api/study/create',dict(body,expected_plan_sha256=plan['plan_sha256']))
        self.assertEqual(session['status'],'ready');self.assertEqual(self.calls,[])
        self.assertEqual(before,contracts.digest(self.server.workbench_store.dataset()))
        result=json.load(urllib.request.urlopen(self.url+'/api/experiments/'+session['id']+'/research'))
        self.assertEqual(sum(g['not_started'] for g in result['conditions']),4)
        self.assertEqual(self.calls,[])
        script=urllib.request.urlopen(self.url+'/web/research-ui.js').read().decode()
        self.assertIn('mountWizard',script)

    def test_stale_source_and_array_request_do_not_create_experiments(self):
        body=request();plan=self.post('/api/study/plan',body)
        data=self.server.workbench_store.dataset();data['cases'][0]['title']+=' changed'
        self.server.workbench_store.save_dataset(data)
        with self.assertRaises(urllib.error.HTTPError):self.post('/api/study/create',dict(body,expected_plan_sha256=plan['plan_sha256']))
        with self.assertRaises(urllib.error.HTTPError):self.post('/api/study/plan',[])
        self.assertEqual(self.server.workbench_store.listing(),[])

    def test_frozen_source_is_used_even_after_draft_changes(self):
        original=self.server.workbench_manager.create(request()['config'])
        data=self.server.workbench_store.dataset();next(c for c in data['cases'] if c['id']=='D09')['public']['query_cost']['H2']=99
        self.server.workbench_store.save_dataset(data)
        body=dict(request(),source_experiment_id=original['id'],expected_source_sha256=original['dataset_sha256'])
        plan=self.post('/api/study/plan',body)
        self.assertEqual(plan['cases'][0]['query_cost']['H2'],5)

    def test_live_runs_require_separate_start_and_only_public_data_reaches_mock(self):
        body=request();body['question']='METADATA_ONLY_NOT_A_PROMPT';plan=self.post('/api/study/plan',body)
        session=self.post('/api/study/create',dict(body,expected_plan_sha256=plan['plan_sha256']))
        with patch('providers.read_key',return_value=''):
            with self.assertRaises(urllib.error.HTTPError):self.post('/api/experiments/'+session['id']+'/start',{'max_calls':6})
        self.assertEqual(self.calls,[])
        with patch('providers.read_key',return_value='local-test-key'):
            self.post('/api/experiments/'+session['id']+'/start',{'max_calls':6})
            self.server.workbench_manager.thread.join(3)
        self.assertTrue(self.calls)
        for public in self.calls:
            encoded=json.dumps(public)
            self.assertNotIn('actual_verified',encoded);self.assertNotIn('actual_access',encoded)
            self.assertNotIn('annotations',encoded);self.assertNotIn('local-test-key',encoded)
            self.assertNotIn('METADATA_ONLY_NOT_A_PROMPT',encoded)
        saved=self.server.workbench_store.get(session['id'])
        self.assertLessEqual(saved['batches'][0]['calls_used'],6)


if __name__=='__main__':unittest.main()
