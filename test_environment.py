import copy
import io
import json
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
import zipfile
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch
import analysis
import app
import catalog
import contracts
import engine
from manager import Manager
import providers
from storage import Store,WorkspaceLock
import temporal_core as core


def setup_case(sid='D01'):
    data=catalog.load_builtin()
    case=next(c for c in data['cases'] if c['id']==sid)
    condition={'episode_id':'e00001','case':sid,'policy':'cost_aware',
               'profile':{'provider':'openai','model':'gpt-5-mini-2025-08-07'},'repetition':1}
    config=engine.plan({'mode':'offline','case_ids':[sid]},data)['config']
    return case,condition,config


def scripted_call(case,condition):
    env=core.Environment(catalog.scenario(case))
    messages=contracts.initial_messages(env.scenario,case)
    def call(profile,public,max_tokens):
        raw=contracts.fixture(env.view,public)
        selected=engine.choose(condition['policy'],env.view,raw['decision'])
        contracts.advance(env,messages,selected)
        return {'output':raw,'usage':{'input_tokens':2,'output_tokens':1},'returned_model':'mock'}
    return call


class DatasetTests(unittest.TestCase):
    def test_catalog_counts_and_existing_annotations(self):
        data=catalog.load_builtin()
        self.assertEqual(len(data['cases']),20)
        self.assertEqual(sum(c['split']=='development' for c in data['cases']),12)
        self.assertEqual(sum(c['split']=='candidate' for c in data['cases']),8)

    def test_rejects_duplicate_id_future_message_bad_prior_and_missing_provenance(self):
        base=catalog.load_builtin()
        examples=[]
        data=copy.deepcopy(base);data['cases'][1]['id']=data['cases'][0]['id'];examples.append(data)
        data=copy.deepcopy(base);data['cases'][0]['messages'][0]['time']=99;examples.append(data)
        data=copy.deepcopy(base);data['cases'][0]['public']['probability_knows']['H2']=1.2;examples.append(data)
        data=copy.deepcopy(base);data['cases'][0]['annotations']['evidence'][0]['source']='H3';examples.append(data)
        for data in examples:
            with self.assertRaises(ValueError):catalog.validate(data)

    def test_no_private_annotation_input_leak(self):
        case,condition,config=setup_case()
        s=catalog.scenario(case)
        alt=replace(s,public=replace(s.public,evidence=(),conflict=True),actual_verified=True,actual_access=('H3',))
        messages=contracts.initial_messages(s,case)
        self.assertEqual(contracts.observation(s.public,messages),contracts.observation(alt.public,messages))
        public=contracts.observation(s.public,messages)
        for k in ('actual_verified','actual_access','annotations','evidence','conflict'):
            self.assertNotIn(k,public['task'])

    def test_evaluation_gate_requires_review_and_family_separation(self):
        data=catalog.load_builtin()
        with self.assertRaises(ValueError):engine.plan({'purpose':'evaluation','case_ids':['E01']},data)
        c=copy.deepcopy(data['cases'][0]);c['id']='T01';c['split']='evaluation';data['cases'].append(c)
        data['review']={'reviewers':['A','B'],'independently_reviewed':True}
        self.assertFalse(catalog.evaluation_readiness(data,['T01'])['ready'])
        c['family']='independently_authored_new_family'
        self.assertTrue(catalog.evaluation_readiness(data,['T01'])['ready'])

    def test_candidate_live_is_blocked_but_offline_allowed(self):
        data=catalog.load_builtin()
        engine.plan({'mode':'offline','case_ids':['E01']},data)
        with self.assertRaises(ValueError):engine.plan({'mode':'live','case_ids':['E01']},data)


class EngineTests(unittest.TestCase):
    def test_all_140_offline_conditions_are_bounded_without_network(self):
        config=setup_case()[2]
        for case in catalog.load_builtin()['cases']:
            for policy in engine.POLICIES:
                condition={'episode_id':'test','case':case['id'],'policy':policy,
                    'profile':{'provider':'fixture','model':'scripted_fixture'},'repetition':1}
                with self.subTest(case=case['id'],policy=policy):
                    row=engine.episode(case,condition,config,{'used':0,'cap':0},
                        call=lambda *a:(_ for _ in ()).throw(AssertionError('network')))
                    self.assertIn(row['status'],engine.FINAL)
                    self.assertLessEqual(len(row['steps']),config['max_steps'])
                    self.assertEqual(row['api_calls'],0)
                    self.assertEqual(row['extraction_error_turns'],0)

    def test_plan_order_reproducible_and_balanced(self):
        data=catalog.load_builtin()
        a=engine.plan({'mode':'offline','repeats':3},data)
        b=engine.plan({'mode':'offline','repeats':3},data)
        c=engine.plan({'mode':'offline','repeats':3,'seed':42},data)
        self.assertEqual(a['pairs'],b['pairs'])
        self.assertNotEqual(a['pairs'],c['pairs'])
        self.assertEqual(len(a['pairs']),108)
        self.assertEqual(len({(p['case'],p['policy'],p['repetition']) for p in a['pairs']}),108)

    def test_plan_rejects_empty_selection_inline_credentials_and_bad_numbers(self):
        for change in ({'case_ids':[]},{'repeats':0},{'max_steps':100},{'question_value':float('nan')},
                       {'mode':'live','models':[{'provider':'openai','model':'x','api_key':'not-a-real-key'}]}):
            with self.assertRaises(ValueError):engine.plan(change,catalog.load_builtin())

    def test_matching_source_selector_and_cost_blind_ablation(self):
        case,condition,config=setup_case('D09');view=catalog.scenario(case).public
        self.assertEqual(engine.choose('cost_aware',view)['recipient'],'H3')
        self.assertEqual(engine.choose('always_reverify',view)['recipient'],'H3')
        self.assertEqual(engine.choose('cost_blind',view)['recipient'],'H2')

    def test_reverification_difference_and_wrong_prior_recovery(self):
        case,condition,config=setup_case('D02')
        a=engine.episode(case,condition,config,{'used':0,'cap':0})
        condition['policy']='always_reverify'
        b=engine.episode(case,condition,config,{'used':0,'cap':0})
        self.assertEqual((a['questions'],b['questions']),(0,1))
        case,condition,config=setup_case('E03')
        row=engine.episode(case,condition,config,{'used':0,'cap':0})
        self.assertEqual(row['status'],'delivered')
        self.assertEqual(row['questions'],2)
        self.assertEqual(row['steps'][1]['public_input']['task']['probability_knows']['H2'],0)

    def test_budget_resumes_without_repeating_completed_calls(self):
        case,condition,config=setup_case('D12');config['mode']='live'
        call=scripted_call(case,condition)
        first=engine.episode(case,condition,config,{'used':0,'cap':1},call=call)
        self.assertEqual(first['status'],'paused_budget')
        second=engine.episode(case,condition,config,{'used':0,'cap':2},previous=first,call=call)
        self.assertEqual(second['status'],'delivered')
        self.assertEqual(second['api_calls'],3)
        self.assertEqual(second['questions'],1)
        self.assertEqual(len(first['steps']),1)

    def test_call_intent_saved_before_transport_and_no_retry(self):
        case,condition,config=setup_case();config['mode']='live';saves=[];calls=[]
        def call(*args):
            self.assertEqual(saves[-1]['steps'][-1]['status'],'in_flight')
            self.assertEqual(saves[-1]['api_calls'],1)
            calls.append(True)
            raise providers.ProviderError('HTTP 401: Key rejected. No automatic retry.')
        row=engine.episode(case,condition,config,{'used':0,'cap':6},call=call,
                           checkpoint=lambda r:saves.append(copy.deepcopy(r)))
        self.assertEqual(len(calls),1)
        self.assertEqual(row['status'],'error')

    def test_restart_never_retries_unknown_inflight(self):
        case,condition,config=setup_case();config['mode']='live'
        previous=dict(condition,status='running',steps=[{'status':'in_flight'}],api_calls=1)
        row=engine.episode(case,condition,config,{'used':0,'cap':6},previous=previous,
                          call=lambda *a:self.fail('retried in-flight'))
        self.assertEqual(row['status'],'interrupted_unknown')
        self.assertEqual(row['api_calls'],1)

    def test_crash_after_saved_terminal_transition_finalizes_without_call(self):
        case,condition,config=setup_case('D02')
        complete=engine.episode(case,condition,config,{'used':0,'cap':0})
        complete['status']='running';config['mode']='live'
        row=engine.episode(case,condition,config,{'used':0,'cap':6},previous=complete,
                          call=lambda *a:self.fail('terminal action retried'))
        self.assertEqual(row['status'],'delivered')

    def test_unsafe_proposal_recorded_and_semantic_error_separate(self):
        case,condition,config=setup_case();config['mode']='live'
        config['evidence_mode']='raw'  # Preserve the unfiltered baseline path.
        public=contracts.observation(catalog.scenario(case).public,contracts.initial_messages(catalog.scenario(case),case))
        raw=contracts.fixture(catalog.scenario(case).public,public)
        raw['evidence'][0]['subject']='C2'
        row=engine.episode(case,condition,config,{'used':0,'cap':1},call=lambda *a:{'output':raw})
        self.assertEqual(row['status'],'dispatch_blocked')
        self.assertEqual(row['unsafe_proposals'],1)
        self.assertEqual(row['extraction_error_turns'],1)
        self.assertEqual(row['validation_errors'],0)

    def test_pause_before_request_uses_no_calls(self):
        case,condition,config=setup_case();config['mode']='live';budget={'used':0,'cap':6}
        row=engine.episode(case,condition,config,budget,should_stop=lambda:True,
                          call=lambda *a:self.fail('called after pause'))
        self.assertEqual(row['status'],'paused_user')
        self.assertEqual(budget['used'],0)

    def test_message_ids_cannot_collide_in_custom_scenarios(self):
        case,condition,config=setup_case('D09');case['messages'][0]['message_id']='m003'
        row=engine.episode(case,condition,config,{'used':0,'cap':0})
        messages=row['steps'][-1]['public_input']['messages']
        self.assertEqual(len(messages),len({m['message_id'] for m in messages}))


class ProviderTests(unittest.TestCase):
    def setUp(self):
        case,condition,config=setup_case()
        self.public=contracts.observation(catalog.scenario(case).public,contracts.initial_messages(catalog.scenario(case),case))
        self.raw=contracts.fixture(catalog.scenario(case).public,self.public)

    def test_fixed_endpoints_and_public_schema(self):
        for name in providers.KEYS:
            url,body=providers.build({'provider':name,'model':'test-model'},self.public)
            self.assertTrue(url.startswith('https://'))
            text=json.dumps(body)
            self.assertNotIn('actual_access',text)
            self.assertNotIn('actual_verified',text)
            self.assertNotIn('api_key',text)

    def test_parses_all_three_provider_shapes(self):
        text=json.dumps(self.raw)
        cases=[('openai',{'status':'completed','output':[{'content':[{'type':'output_text','text':text}]}],'usage':{'input_tokens':5,'output_tokens':3}}),
               ('anthropic',{'stop_reason':'end_turn','content':[{'type':'text','text':text}],'usage':{'input_tokens':5,'output_tokens':3}}),
               ('gemini',{'candidates':[{'finishReason':'STOP','content':{'parts':[{'text':text}]}}],'usageMetadata':{'promptTokenCount':5,'candidatesTokenCount':3}})]
        for name,r in cases:
            raw,usage,model=providers.parse(name,r)
            self.assertEqual(raw,self.raw)
            self.assertEqual(usage['input_tokens'],5)
            self.assertEqual(usage['output_tokens'],3)

    def test_refusal_incomplete_and_invalid_json_never_execute(self):
        for name,response in [('openai',{'status':'incomplete'}),('anthropic',{'stop_reason':'max_tokens'}),
                              ('gemini',{'candidates':[]}),('openai',{'status':'completed','output':[{'content':[{'type':'output_text','text':'not json'}]}]})]:
            with self.assertRaises(providers.ProviderError):providers.parse(name,response)

    def test_mock_transport_secret_header_only_and_no_retry(self):
        calls=[]
        def transport(req,timeout):
            calls.append(req)
            self.assertEqual(timeout,60)
            self.assertNotIn('unit-test-secret',req.data.decode())
            r={'status':'completed','output':[{'content':[{'type':'output_text','text':json.dumps(self.raw)}]}]}
            return io.BytesIO(json.dumps(r).encode())
        with patch('providers.read_key',return_value='unit-test-secret'):
            result=providers.infer({'provider':'openai','model':'gpt-5-mini-2025-08-07'},self.public,transport=transport)
        self.assertEqual(result['output'],self.raw)
        self.assertEqual(len(calls),1)
        self.assertNotIn('unit-test-secret',json.dumps(result))

    def test_http_error_does_not_expose_server_body_or_key(self):
        def transport(req,timeout):
            raise urllib.error.HTTPError(req.full_url,401,'untrusted secret message',{},io.BytesIO(b'unit-test-secret'))
        with patch('providers.read_key',return_value='unit-test-secret'):
            with self.assertRaises(providers.ProviderError) as error:
                providers.infer({'provider':'openai','model':'test'},self.public,transport=transport)
        self.assertIn('HTTP 401',str(error.exception))
        self.assertNotIn('secret',str(error.exception))


class PersistenceAnalysisTests(unittest.TestCase):
    def test_workspace_lock_blocks_second_process_handle_and_releases(self):
        with tempfile.TemporaryDirectory() as tmp:
            first,second=WorkspaceLock(tmp),WorkspaceLock(tmp)
            first.acquire()
            with self.assertRaises(ValueError):second.acquire()
            first.release()
            second.acquire();second.release()

    def test_live_manager_global_budget_and_additional_resume_cap(self):
        case,condition,config=setup_case('D12')
        with tempfile.TemporaryDirectory() as tmp,patch('providers.read_key',return_value='unit-test-secret'):
            manager=Manager(Store(tmp),call=scripted_call(case,condition))
            s=manager.create({'mode':'live','case_ids':['D12'],'policies':['cost_aware']},'mock live')
            manager.start(s['id'],1);manager.thread.join(5)
            first=manager.store.get(s['id'])
            self.assertEqual(first['status'],'paused_budget')
            self.assertEqual(first['runs'][0]['api_calls'],1)
            manager.start(s['id'],2);manager.thread.join(5)
            second=manager.store.get(s['id'])
            self.assertEqual(second['status'],'completed')
            self.assertEqual([b['calls_used'] for b in second['batches']],[1,2])
            self.assertEqual(second['runs'][0]['api_calls'],3)
            self.assertNotIn('unit-test-secret',json.dumps(second))

    def test_missing_keys_and_frozen_fingerprint_changes_block_start(self):
        with tempfile.TemporaryDirectory() as tmp:
            manager=Manager(Store(tmp))
            s=manager.create({'mode':'live','case_ids':['D01']},'missing key test')
            with patch('providers.read_key',return_value=''):
                with self.assertRaises(ValueError):manager.start(s['id'])
            self.assertEqual(manager.store.get(s['id'])['batches'],[])
            s['fingerprint']['sha256']='modified'
            manager.store.save(s)
            with self.assertRaises(ValueError):manager.start(s['id'])

    def test_manager_frozen_data_pause_resume_and_exports(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(tmp);manager=Manager(store)
            s=manager.create({'mode':'offline','case_ids':['D01','D02']},'Test <script>')
            original=s['dataset_sha256']
            data=store.dataset();data['cases'][0]['title']='Changed draft'
            store.save_dataset(data)
            manager.start(s['id'],6);manager.thread.join(5)
            saved=store.get(s['id'])
            self.assertEqual(saved['status'],'completed')
            self.assertEqual(saved['dataset_sha256'],original)
            self.assertNotEqual(saved['dataset']['cases'][0]['title'],'Changed draft')
            self.assertEqual(len(saved['runs']),6)
            with self.assertRaises(ValueError):manager.start(s['id'],6)
            summary=analysis.summarize(saved)
            self.assertTrue(summary['complete'])
            self.assertEqual(len(summary['groups']),3)
            paired=summary['paired_cost'][0]
            self.assertEqual(paired['scenario_clusters'],2)
            self.assertEqual(paired['paired_repetitions'],2)
            report=analysis.html_report(saved)
            self.assertNotIn('<script>',report)
            self.assertIn('&lt;script&gt;',report)
            self.assertIn('\\begin{tabular}',analysis.latex_export(saved))
            content,mime,name=app.export(saved,'zip')
            with zipfile.ZipFile(io.BytesIO(content)) as z:
                self.assertIsNone(z.testzip())
                self.assertIn('frozen_dataset.json',z.namelist())

    def test_repeated_llm_runs_remain_scenario_clusters(self):
        with tempfile.TemporaryDirectory() as tmp:
            manager=Manager(Store(tmp))
            s=manager.create({'mode':'offline','case_ids':['D01','D02'],'repeats':3},'cluster test')
            manager.start(s['id']);manager.thread.join(5)
            paired=analysis.summarize(manager.store.get(s['id']))['paired_cost'][0]
            self.assertEqual(paired['scenario_clusters'],2)
            self.assertEqual(paired['paired_repetitions'],6)

    def test_csv_formula_protection_and_archive_readonly(self):
        case,condition,config=setup_case('D02')
        condition['profile']['model']='=bad'
        row=engine.episode(case,condition,config,{'used':0,'cap':0})
        csv=analysis.csv_export({'runs':[row]})
        self.assertIn("'=bad",csv)
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(tmp)
            result=store.import_archive({'metadata':{'version':'0.7'},'runs':[{'status':'error'}]})
            self.assertEqual(result['run_count'],1)
            self.assertEqual(store.listing(),[])

    def test_path_traversal_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):Store(tmp).get('../../anything')


class HTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory()
        cls.server=app.make_server(cls.temp.name,0)
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()
        cls.url='http://127.0.0.1:'+str(cls.server.server_address[1])
        import re
        page=urllib.request.urlopen(cls.url).read().decode()
        cls.token=re.search(r'name="workbench-token" content="([a-f0-9]+)"',page)[1]
    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.server_close();cls.temp.cleanup()

    def get(self,path):
        return json.load(urllib.request.urlopen(self.url+path))
    def post(self,path,body,token=None,origin=None):
        headers={'Content-Type':'application/json','X-Workbench-Token':token or self.token}
        if origin:headers['Origin']=origin
        return json.load(urllib.request.urlopen(urllib.request.Request(self.url+path,data=json.dumps(body).encode(),headers=headers)))

    def test_state_never_returns_key_values(self):
        with patch('providers.read_key',return_value='unit-test-secret'):
            data=self.get('/api/state')
        self.assertNotIn('unit-test-secret',json.dumps(data))
        self.assertTrue(data['keys']['openai']['available'])

    def test_mutations_require_token_and_same_origin(self):
        for kwargs in ({'token':'bad'},{'origin':'https://example.com'}):
            with self.assertRaises(urllib.error.HTTPError) as e:self.post('/api/plan',{'config':{}},**kwargs)
            self.assertEqual(e.exception.code,403)

    def test_local_host_header_enforced(self):
        req=urllib.request.Request(self.url+'/api/state',headers={'Host':'attacker.example'})
        with self.assertRaises(urllib.error.HTTPError) as e:urllib.request.urlopen(req)
        self.assertEqual(e.exception.code,403)

    def test_http_full_offline_experiment_and_export(self):
        s=self.post('/api/experiments',{'name':'HTTP test','config':{'mode':'offline','case_ids':['D01']}})
        self.post('/api/experiments/'+s['id']+'/start',{'max_calls':6})
        self.server.workbench_manager.thread.join(5)
        result=self.get('/api/experiments/'+s['id'])
        self.assertEqual(result['session']['status'],'completed')
        self.assertTrue(result['summary']['complete'])
        response=urllib.request.urlopen(self.url+'/api/experiments/'+s['id']+'/export?format=csv')
        self.assertIn('attachment',response.headers['Content-Disposition'])
        self.assertIn('episode_id',response.read().decode())


if __name__=='__main__':
    unittest.main()
