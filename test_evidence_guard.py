import copy
import io
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch
import catalog
import contracts
import engine
import evidence_guard as guard
import replay_audit
from storage import WorkspaceLock
from test_environment import setup_case

ROOT=Path(__file__).resolve().parent


def public_message(text,subject='C1'):
    case,_,_=setup_case('D09')
    scenario=catalog.scenario(case)
    public=contracts.observation(scenario.public,contracts.initial_messages(scenario,case))
    public['messages'][0]['text']=text
    public['task']['known_subjects']=['C1','C2','C1-east']
    public['task']['subject']=subject
    return public


def claim(value=True,subject='C1'):
    return {'message_id':'m001','subject':subject,'value':value}


class EvidenceSupportTests(unittest.TestCase):
    def test_explicit_positive_and_negative_assertions(self):
        examples=[
            ('Ο έλεγχος του C1 ολοκληρώθηκε.',True),
            ('Ο έλεγχος του C1 δεν έχει ολοκληρωθεί.',False),
            ('Ο έλεγχος ολοκληρώθηκε και δεν χρειάζεται άλλη ερώτηση.',True),
            ('The check is completed and no delivery is needed.',True),
            ('The check has not been completed.',False),
            ('Η καταγραφή δείχνει εκκρεμή έλεγχο.',False),
            ('Έκανα προσωπικά τον έλεγχο τώρα και ολοκληρώθηκε.',True),
            ('The inspection for C1 is completed.',True),
            ('The check for C1 is not complete.',False),
            ('The check for C1 is pending.',False),
            ('The check for C1 failed.',False),
            ('Ο έλεγχος είναι μη ολοκληρωμένος.',False)]
        for text,value in examples:
            with self.subTest(text=text):
                indexes,audit=guard.filter_claims([claim(value)],public_message(text))
                self.assertEqual(indexes,[0]);self.assertTrue(audit[0]['accepted'])

    def test_unknown_participation_alias_and_prospective_text_never_support_claims(self):
        texts=[
            'Το H2 και το H3 συμμετείχαν στον ίδιο έλεγχο του κιτ Α.',
            'Το ίδιο καρότσι C1 εμφανίζεται πλέον ως C1-east στην οθόνη.',
            'Δεν γνωρίζω αν ολοκληρώθηκε ο έλεγχος.',
            'Η επιβεβαίωση ελέγχου εκκρεμεί.',
            'Αν ολοκληρωθεί ο έλεγχος, θα ενημερώσω την ομάδα.',
            'Ο έλεγχος πρέπει να ολοκληρωθεί.',
            'Ο έλεγχος ολοκληρώθηκε;',
            'Is the check completed?',
            'The check must be completed.',
            'I do not know whether the check is complete.',
            'The confirmation of the check is pending.',
            'Ο έλεγχος δεν εκκρεμεί.',
            'The check is not pending.',
            'Παράδειγμα: «ο έλεγχος ολοκληρώθηκε».',
            'Δεν είπα ότι ο έλεγχος ολοκληρώθηκε.']
        for text in texts:
            for value in (True,False):
                with self.subTest(text=text,value=value):
                    self.assertEqual(guard.filter_claims([claim(value)],public_message(text))[0],[])

    def test_wrong_polarity_and_ambiguous_message_are_rejected(self):
        for text,value in [('Ο έλεγχος ολοκληρώθηκε.',False),
                           ('Ο έλεγχος δεν έχει ολοκληρωθεί.',True),
                           ('Ο έλεγχος ολοκληρώθηκε και δεν έχει ολοκληρωθεί.',True),
                           ('Ο έλεγχος ολοκληρώθηκε. Ο έλεγχος δεν έχει ολοκληρωθεί.',True)]:
            self.assertEqual(guard.filter_claims([claim(value)],public_message(text))[0],[])

    def test_cart_binding_aliases_and_ambiguous_multi_cart_messages(self):
        p=public_message('Ο έλεγχος του C1 ολοκληρώθηκε.')
        self.assertEqual(guard.filter_claims([claim(subject='C2')],p)[0],[])
        p['task']['aliases']={'C1-east':'C1'}
        self.assertEqual(guard.filter_claims([claim(subject='C1-east')],p)[0],[0])
        p['messages'][0]['text']='Ο έλεγχος του C1 και του C2 ολοκληρώθηκε.'
        self.assertEqual(guard.filter_claims([claim()],p)[0],[])

    def test_inputs_not_mutated_and_gold_metadata_has_no_effect(self):
        p=public_message('Ο έλεγχος του C1 ολοκληρώθηκε.');items=[claim()]
        before=copy.deepcopy((p,items));result=guard.filter_claims(items,p)
        self.assertEqual((p,items),before)
        p['private']={'actual_verified':False,'actual_access':[]}
        p['annotations']={'evidence':[],'conflict':True}
        self.assertEqual(result,guard.filter_claims(items,p))

    def test_filter_never_adds_claims_or_changes_source_time_or_ttl(self):
        p=public_message('Ο έλεγχος του C1 ολοκληρώθηκε.');raw={'evidence':[claim()],
            'conflict':False,'decision':{'action':'dispatch','recipient':None}}
        evidence,_,_=contracts.decode(raw,p)
        indexes,_=guard.filter_claims(raw['evidence'],p)
        admitted=[e for i,e in enumerate(evidence) if i in indexes]
        self.assertEqual(admitted,list(evidence))
        self.assertEqual(guard.filter_claims([],p),([],[]))

    def test_recorded_development_turns_preserve_raw_errors_and_fix_known_admission_errors(self):
        data=json.loads((ROOT/'regression/recorded_turns_v1.json').read_text(encoding='utf-8'))
        with patch('providers.infer',side_effect=AssertionError('Network forbidden')):
            result=replay_audit.audit(data)
        self.assertEqual(result['recorded_turns'],12)
        self.assertEqual(result['raw_error_turns'],4)
        self.assertEqual(result['admitted_error_turns'],0)
        self.assertEqual(result['rejected_claims'],4)
        self.assertEqual(result['changed_actions_on_saved_inputs'],1)
        bad=next(r for r in result['rows'] if r['case']=='D09' and r['policy']=='cost_blind')
        self.assertEqual(bad['raw_action']['action'],'escalate')
        self.assertEqual(bad['admitted_action'],{'action':'ask','recipient':'H2'})

    def test_raw_and_filtered_execution_paths_keep_original_outputs_visible(self):
        for mode in ('raw','explicit_support'):
            case,condition,config=setup_case('D09');condition['policy']='cost_blind'
            config.update(mode='live',evidence_mode=mode)
            bad={'evidence':[claim(False)],'conflict':False,'decision':{'action':'ask','recipient':'H3'}}
            def call(profile,public,max_tokens):
                if len(public['messages'])==1:return {'output':copy.deepcopy(bad)}
                return {'output':{'evidence':[{'message_id':public['messages'][-1]['message_id'],'subject':'C1','value':True}],
                    'conflict':False,'decision':{'action':'dispatch','recipient':None}}}
            row=engine.episode(case,condition,config,{'used':0,'cap':2},call=call)
            self.assertEqual(row['steps'][0]['raw_output'],bad)
            self.assertEqual(row['extraction_error_turns'],1)
            if mode=='raw':
                self.assertEqual(row['status'],'escalated');self.assertEqual(row['rejected_evidence'],0)
                self.assertEqual(row['accepted_extraction_error_turns'],1)
            else:
                self.assertEqual(row['status'],'delivered');self.assertEqual(row['query_cost'],5)
                self.assertEqual(row['accepted_extraction_error_turns'],0)
                self.assertEqual(row['rejected_evidence'],1)
                self.assertEqual(row['guard_changed_controller_turns'],1)

    def test_llm_action_is_not_replaced_by_programmed_controller(self):
        case,condition,config=setup_case('D09');condition['policy']='llm';config['mode']='live'
        raw={'evidence':[claim(False)],'conflict':False,'decision':{'action':'ask','recipient':'H3'}}
        row=engine.episode(case,condition,config,{'used':0,'cap':1},call=lambda *a:{'output':raw})
        self.assertEqual(row['steps'][0]['selected_action'],raw['decision'])
        self.assertFalse(row['steps'][0]['guard_changes_controller_action'])
        self.assertEqual(row['rejected_evidence'],1)

    def test_mode_is_frozen_and_invalid_modes_are_rejected(self):
        data=catalog.load_builtin()
        self.assertEqual(engine.plan({},data)['config']['evidence_mode'],'explicit_support')
        self.assertEqual(engine.plan({'evidence_mode':'raw'},data)['config']['evidence_mode'],'raw')
        with self.assertRaises(ValueError):engine.plan({'evidence_mode':'gold_oracle'},data)

    def test_gold_fixture_paths_are_preserved_for_all_builtin_cases_and_policies(self):
        config=setup_case()[2]
        for case in catalog.load_builtin()['cases']:
            for policy in engine.POLICIES:
                condition={'episode_id':'test','case':case['id'],'policy':policy,
                    'profile':{'provider':'fixture','model':'scripted_fixture'},'repetition':1}
                with self.subTest(case=case['id'],policy=policy):
                    raw=engine.episode(case,condition,dict(config,evidence_mode='raw'),{'used':0,'cap':0})
                    filtered=engine.episode(case,condition,dict(config,evidence_mode='explicit_support'),{'used':0,'cap':0})
                    self.assertEqual([(x['selected_action'],x['transition']) for x in raw['steps']],
                                     [(x['selected_action'],x['transition']) for x in filtered['steps']])
                    self.assertEqual(filtered['rejected_evidence'],0)
                    self.assertEqual(filtered['accepted_extraction_error_turns'],0)


class WindowsLockRegressionTests(unittest.TestCase):
    def test_windows_lock_never_reads_a_byte_before_locking(self):
        with tempfile.TemporaryDirectory() as tmp:
            lock=WorkspaceLock(tmp);handle=io.BytesIO()
            handle.fileno=lambda:42
            handle.read=lambda *a:(_ for _ in ()).throw(PermissionError('another handle owns byte'))
            calls=[]
            fake=types.SimpleNamespace(LK_NBLCK=1,locking=lambda fd,mode,n:calls.append((fd,mode,n,handle.tell())))
            with patch('storage.Path.open',return_value=handle),patch('os.name','nt'),patch.dict(sys.modules,{'msvcrt':fake}):
                lock.acquire();lock.release()
            self.assertEqual(calls,[(42,1,1,0)])
            self.assertTrue(handle.closed)

    def test_windows_second_instance_failure_closes_handle_and_is_readable(self):
        with tempfile.TemporaryDirectory() as tmp:
            lock=WorkspaceLock(tmp);handle=io.BytesIO();handle.fileno=lambda:42
            def fail(*a):raise OSError('locked')
            fake=types.SimpleNamespace(LK_NBLCK=1,locking=fail)
            with patch('storage.Path.open',return_value=handle),patch('os.name','nt'),patch.dict(sys.modules,{'msvcrt':fake}):
                with self.assertRaisesRegex(ValueError,'already open'):lock.acquire()
            self.assertTrue(handle.closed)


if __name__=='__main__':
    unittest.main()
