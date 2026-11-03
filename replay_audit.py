"""Replay saved extraction inputs locally; never calls a provider.

Each turn is assessed on its ORIGINAL saved history. Changed actions do not
generate counterfactual future replies. This is a development regression audit,
not a new end-to-end LLM experiment or an independent benchmark.
"""
import argparse
import html
import json
from dataclasses import replace
from pathlib import Path
import contracts
import engine
import evidence_guard
import temporal_core as core

ROOT = Path(__file__).resolve().parent


def audit(data):
    rows = []
    for turn in data['turns']:
        public, raw = turn['public_input'], turn['raw_output']
        expected = dict(turn['expected_view_for_offline_scoring'])
        expected['evidence'] = tuple(core.Evidence(**e) for e in expected['evidence'])
        expected['sources'] = tuple(expected['sources'])
        expected['attempted'] = tuple(expected['attempted'])
        view = core.PublicState(**expected)
        evidence, conflict, decision = contracts.decode(raw, public)
        indexes, details = evidence_guard.filter_claims(raw['evidence'], public)
        admitted = tuple(e for i,e in enumerate(evidence) if i in indexes)
        raw_checks = contracts.check(view, evidence, conflict)
        admitted_checks = contracts.check(view, admitted, conflict)
        raw_action = engine.choose(turn['policy'], replace(view,evidence=evidence,conflict=conflict),decision)
        admitted_action = engine.choose(turn['policy'], replace(view,evidence=admitted,conflict=conflict),decision)
        rows.append({'case':turn['case'], 'policy':turn['policy'], 'turn':turn['turn'],
                     'raw_checks':raw_checks, 'admitted_checks':admitted_checks,
                     'raw_action':raw_action, 'admitted_action':admitted_action,
                     'action_changed':raw_action!=admitted_action,
                     'rejected_claims':sum(not d['accepted'] for d in details),
                     'evidence_audit':details})
    return {'scope':data['scope'], 'source_session_id':data['source_session_id'],
            'guard_version':evidence_guard.VERSION, 'new_api_calls':0,
            'recorded_turns':len(rows),
            'raw_error_turns':sum(not all(r['raw_checks'].values()) for r in rows),
            'admitted_error_turns':sum(not all(r['admitted_checks'].values()) for r in rows),
            'changed_actions_on_saved_inputs':sum(r['action_changed'] for r in rows),
            'rejected_claims':sum(r['rejected_claims'] for r in rows),
            'limitation':'No new model outputs or counterfactual complete episodes were generated. The guard uses a limited, hand-written language grammar. Independent and live validation remain necessary.',
            'rows':rows}


def render(report):
    esc=lambda s:html.escape(str(s))
    rows=''.join('<tr>'+''.join('<td>'+esc(v)+'</td>' for v in (
        r['case'],r['policy'],r['turn'],all(r['raw_checks'].values()),
        all(r['admitted_checks'].values()),r['rejected_claims'],
        json.dumps(r['raw_action'],ensure_ascii=False),json.dumps(r['admitted_action'],ensure_ascii=False)))+'</tr>' for r in report['rows'])
    return ('<!doctype html><html lang="el"><meta charset="utf-8"><title>RSS2027 offline regression audit</title>'
        '<style>body{font:16px system-ui;max-width:1200px;margin:36px auto;padding:0 20px;color:#17333e}table{border-collapse:collapse;width:100%}td,th{border:1px solid #d9e0e3;padding:10px;text-align:left}th{background:#17333e;color:white}.scroll{overflow:auto}pre{white-space:pre-wrap;background:#f3f6f7;padding:18px}</style>'
        '<h1>Δωρεάν έλεγχος καταγεγραμμένων εξαγωγών</h1>'
        '<p>Δεν πραγματοποιούνται νέες κλήσεις API. Κάθε γύρος ελέγχεται στην αρχική αποθηκευμένη ιστορία του. Οι διαφορετικές ενέργειες δεν εκτελούνται ως νέα επεισόδια.</p>'
        '<p>Γύροι: '+esc(report['recorded_turns'])+' · Αρχικά λάθη: '+esc(report['raw_error_turns'])+
        ' · Λάθη μετά το φίλτρο: '+esc(report['admitted_error_turns'])+' · Απορριφθείσες αναφορές: '+esc(report['rejected_claims'])+'</p>'
        '<p>Πρόκειται για περιπτώσεις ανάπτυξης που χρησιμοποιήθηκαν για τη σχεδίαση της διόρθωσης. Δεν αποδεικνύεται γενίκευση ή βελτίωση σε νέες αποκρίσεις LLM.</p>'
        '<div class="scroll"><table><tr><th>Σενάριο</th><th>Πολιτική</th><th>Γύρος</th><th>Αρχικά σωστό</th><th>Μετά το φίλτρο σωστό</th><th>Απορρίψεις</th><th>Αρχική ενέργεια</th><th>Ενέργεια με φίλτρο</th></tr>'+rows+'</table></div>'
        '<details><summary>Πλήρης καταγραφή</summary><pre>'+esc(json.dumps(report,ensure_ascii=False,indent=2))+'</pre></details></html>')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'offline_audit')
    args=parser.parse_args()
    report=audit(json.loads((ROOT/'regression/recorded_turns_v1.json').read_text(encoding='utf-8')))
    args.output.mkdir(parents=True,exist_ok=True)
    (args.output/'replay_audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (args.output/'report.html').write_text(render(report),encoding='utf-8')
    print('OFFLINE RECORDED-INPUT AUDIT | New API calls: 0')
    print('Saved turns:',report['recorded_turns'])
    print('Raw extraction error turns:',report['raw_error_turns'])
    print('After explicit-support filter:',report['admitted_error_turns'])
    print('Changed actions on saved inputs:',report['changed_actions_on_saved_inputs'])
    print('Not a new live evaluation; no complete counterfactual outcomes inferred.')
    print('Report:',(args.output/'report.html').resolve())
    print('Share:',(args.output/'replay_audit.json').resolve())
    return 0 if report['admitted_error_turns']==0 else 1


if __name__=='__main__':
    raise SystemExit(main())
