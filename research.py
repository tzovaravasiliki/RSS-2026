"""Research study envelopes and read-only, one-step policy diagnostics.

No provider is called here. A study is a frozen development/evaluation plan,
not a preregistration or independent scientific review.
"""
from __future__ import annotations

import copy
import csv
import html
import io
import json
import math
from collections import Counter

import analysis
import catalog
import contracts
import engine
import temporal_core as core


VERSION = 'study-workflow-v1'
QUESTION = ('Πότε και από ποιο μέλος μιας ομάδας πρέπει ένας ρομποτικός '
            'συντονιστής να ζητά επιβεβαίωση, ώστε να περιορίζει τις διακοπές '
            'και το κόστος τους, λαμβάνοντας υπόψη την αβεβαιότητα, την '
            'ταυτότητα του αντικειμένου, την ισχύ των πληροφοριών και τις προθεσμίες;')
HYPOTHESES = [
    {'id': 'H1', 'contrast': ['cost_aware', 'always_reverify'],
     'prediction': 'Λιγότερες περιττές ερωτήσεις με επιλεκτική επανεπιβεβαίωση.',
     'qualification': 'Η ορθότητα αναφέρεται χωριστά. Δεν τεκμηριώνεται μη κατωτερότητα χωρίς όριο και κατάλληλο σχεδιασμό.'},
    {'id': 'H2', 'contrast': ['cost_aware', 'cost_blind'],
     'prediction': 'Μικρότερο κόστος διακοπών όταν η επιλογή πηγής συνεκτιμά το κόστος.',
     'qualification': 'Το diagnostic στην ίδια καταγεγραμμένη πληροφορία ελέγχει μία ενέργεια, όχι υποθετικές πλήρεις εκβάσεις.'},
    {'id': 'H3', 'contrast': ['cost_aware', 'llm'],
     'prediction': 'Διερεύνηση διαφορών προτάσεων, κόστους και λαθών μεταξύ υβριδικού controller και απευθείας LLM.',
     'qualification': 'Δεν προϋποτίθεται υπεροχή. Τα ανεξάρτητα live calls μπορεί να έχουν διαφορετικές εξαγωγές.'},
]
PRESETS = [
    {'id': 'information_checks', 'label': 'Πιλοτικός έλεγχος ισχύος και αντιφάσεων',
     'case_ids': ['D03', 'D05'], 'policies': ['cost_aware', 'always_reverify', 'cost_blind', 'llm']},
    {'id': 'source_selection', 'label': 'Επιλογή ανθρώπινης πηγής και κόστος',
     'case_ids': ['D09', 'D10'], 'policies': ['cost_aware', 'always_reverify', 'cost_blind', 'llm']},
    {'id': 'development_suite', 'label': 'Πλήρης σουίτα ανάπτυξης',
     'case_ids': [f'D{i:02d}' for i in range(1, 13)],
     'policies': ['cost_aware', 'always_reverify', 'cost_blind', 'llm']},
]


def metadata():
    return {'version': VERSION, 'question': QUESTION, 'hypotheses': copy.deepcopy(HYPOTHESES),
            'presets': copy.deepcopy(PRESETS)}


def prepare(request, source_data, source_experiment_id=None):
    """Build a deterministic plan without editing the draft or starting work."""
    if not isinstance(request, dict):
        raise ValueError('Study request must be an object')
    source = catalog.validate(copy.deepcopy(source_data))
    source_hash = contracts.digest(source)
    if request.get('expected_source_sha256') not in (None, source_hash):
        raise ValueError('The source dataset changed. Reload the study page and review it again.')
    config = request.get('config')
    if not isinstance(config, dict):
        raise ValueError('Study config must be an object')
    cap = request.get('initial_call_cap', 6)
    if type(cap) is not int or not 1 <= cap <= 10000:
        raise ValueError('Initial call cap must be an integer from 1 to 10000')
    question = request.get('question', QUESTION)
    if not isinstance(question, str) or not 1 <= len(question.strip()) <= 1800:
        raise ValueError('Research question must contain 1–1800 characters')
    name = request.get('name', 'RSS2027 research development study')
    if not isinstance(name, str):
        raise ValueError('Study name must be text')
    name = name.strip()[:120] or 'RSS2027 research development study'
    overrides = request.get('cost_overrides', {})
    if not isinstance(overrides, dict):
        raise ValueError('Cost overrides must be an object')
    selected = config.get('case_ids', [])
    if not isinstance(selected, list):
        raise ValueError('Select cases before defining a cost variant')
    cases = {c['id']: c for c in source['cases']}
    changed = {}
    for cid, costs in overrides.items():
        if cid not in selected or cid not in cases or not isinstance(costs, dict) or set(costs) != {'H2', 'H3'}:
            raise ValueError('Cost variants require one selected case and costs for H2 and H3')
        if any(type(v) not in (int, float) or not math.isfinite(v) or not 0 <= v <= 1000 for v in costs.values()):
            raise ValueError('Costs must be finite numbers from 0 to 1000')
        if costs != cases[cid]['public']['query_cost']:
            changed[cid] = copy.deepcopy(costs)
            cases[cid]['public']['query_cost'] = copy.deepcopy(costs)
    if changed and config.get('purpose') == 'evaluation':
        raise ValueError('A modified evaluation case requires a newly reviewed dataset. Cost variants here are development only.')
    draft = engine.plan(config, source)
    chosen = [c for c in source['cases'] if c['id'] in draft['config']['case_ids']]
    design = {'version': VERSION, 'question': question.strip(), 'hypotheses': copy.deepcopy(HYPOTHESES),
              'status': 'frozen_plan_not_preregistration', 'purpose': draft['config']['purpose'],
              'primary_descriptive_metrics': ['query_cost', 'questions'],
              'required_companion_metrics': ['expected_outcome_met', 'unsafe_proposals', 'unsupported_proposals',
                                             'technical_errors', 'coverage', 'raw_and_admitted_extraction_errors'],
              'sampling_note': 'Scenario/family independence needs study-design justification; turns and repetitions are not independent cases.',
              'controller_scope': 'Greedy one-step heuristic over public knowledge estimates; not a learned policy or an optimal value-of-information planner.',
              'task_scope': 'One Boolean verification prerequisite for one current cart; scripted human replies, no ASR, physical robot or clinical protocol validation.',
              'source': {'kind': 'frozen_experiment' if source_experiment_id else 'workspace_draft',
                         'experiment_id': source_experiment_id, 'dataset_sha256': source_hash},
              'cost_overrides': changed, 'initial_call_cap': cap if draft['config']['mode'] == 'live' else 0,
              'preset_id': request.get('preset_id') if request.get('preset_id') in {p['id'] for p in PRESETS} else 'custom',
              'dataset_sha256': draft['dataset_sha256'], 'code_sha256': draft['fingerprint']['sha256']}
    review_hash = contracts.digest({'name': name, 'design': design, 'config': draft['config'], 'plan': draft['pairs']})
    if request.get('expected_plan_sha256') not in (None, review_hash):
        raise ValueError('The reviewed study plan changed. Preview it again before creating an experiment.')
    design['plan_sha256'] = review_hash
    warnings = ['This plan is not a preregistration, power analysis or external review.',
                'Interruption costs are synthetic units. Call caps are attempts, not currency.']
    if draft['config']['mode'] == 'offline':
        warnings.append('Offline fixtures are software checks, not LLM results.')
    elif len(draft['config']['models']) < 2:
        warnings.append('Only one model profile is selected; this does not compare different chatbots.')
    if any(c['split'] != 'evaluation' for c in chosen):
        warnings.append('Selected development/candidate cases do not constitute independent evaluation.')
    if draft['config']['repeats'] == 1:
        warnings.append('One repetition does not measure variation across model calls.')
    return {'name': name, 'config': draft['config'], 'dataset': draft['dataset'], 'study_design': design,
            'plan_sha256': review_hash, 'source_sha256': source_hash, 'fingerprint': draft['fingerprint'],
            'episodes': draft['episodes'], 'maximum_calls': draft['maximum_calls'],
            'initial_call_cap': design['initial_call_cap'], 'cases': [
                {'id': c['id'], 'title': c['title'], 'family': c['family'], 'split': c['split'],
                 'query_cost': c['public']['query_cost']} for c in chosen],
            'readiness': draft['readiness'], 'warnings': warnings}


def decision_audit(session):
    """Apply current controllers to the same recorded admitted extraction.

    It deliberately never reads scenario annotations, true state, source access,
    or hypothetical future replies. Each result is one proposed next action.
    """
    observations, skipped = [], []
    for run in session.get('runs', []):
        for index, step in enumerate(run.get('steps', []), 1):
            origin = {'episode_id': run['episode_id'], 'case': run['case'], 'step': index,
                      'source_policy': run['policy'], 'profile': copy.deepcopy(run['profile'])}
            try:
                public, raw = step['public_input'], step['raw_output']
                _, _, proposal = contracts.decode(raw, public)
                admitted = step.get('accepted_evidence')
                if admitted is None:
                    if step.get('evidence_guard_applied') or session['config'].get('evidence_mode') == 'explicit_support':
                        raise ValueError('missing_recorded_admitted_evidence')
                    admitted = raw['evidence']
                if not isinstance(admitted, list) or any(e not in raw['evidence'] for e in admitted):
                    raise ValueError('invalid_recorded_admitted_subset')
                evidence, _, _ = contracts.decode(dict(raw, evidence=admitted, conflict=False), public)
                conflict = raw['conflict']
                t = public['task']
                view = core.PublicState(run['case'], t['subject'], t['now'], t['deadline'], evidence,
                    copy.deepcopy(t['aliases']), conflict, tuple(t['sources']), copy.deepcopy(t['probability_knows']),
                    copy.deepcopy(t['available_at']), copy.deepcopy(t['query_cost']), tuple(t['attempted']), t['received_answer'])
                actions = {p: engine.choose(p, view, question_value=session['config'].get('question_value', 30))
                           for p in ('cost_aware', 'always_reverify', 'cost_blind')}
                actions['llm_proposal'] = proposal
                observations.append(dict(origin, public_sha256=contracts.digest(public),
                    admitted_sha256=contracts.digest({'evidence': admitted, 'conflict': conflict}),
                    subject=t['subject'], time=t['now'], deadline=t['deadline'],
                    admitted_status=core.current_evidence(view), actions=actions,
                    immediate_query_cost={p: t['query_cost'][a['recipient']] if a['action'] == 'ask' else 0
                                          for p, a in actions.items()},
                    recorded_action=copy.deepcopy(step.get('selected_action')),
                    raw_extraction_checks=copy.deepcopy(step.get('extraction_checks')),
                    admitted_extraction_checks=copy.deepcopy(step.get('accepted_extraction_checks'))))
            except (ValueError, KeyError, TypeError, AttributeError):
                skipped.append(dict(origin, reason='missing_or_invalid_recorded_extraction',
                                    saved_status=step.get('status'), saved_stage=step.get('stage')))
    contrasts = []
    for a, b in [('cost_aware', 'always_reverify'), ('cost_aware', 'cost_blind'), ('cost_aware', 'llm_proposal')]:
        contrasts.append({'policies': [a, b], 'observations': len(observations),
                          'different_actions': sum(o['actions'][a] != o['actions'][b] for o in observations),
                          'scope': 'Recorded one-step suggestions only; no counterfactual episode outcomes or total costs.'})
    frozen = session.get('fingerprint', {})
    current = engine.code_fingerprint()
    return {'version': VERSION, 'new_provider_calls': 0,
            'scope': 'one_step_actions_on_identical_recorded_inputs_and_admitted_claims',
            'scored_turns': len(observations), 'skipped_turns': len(skipped),
            'unique_public_inputs': len({o['public_sha256'] for o in observations}),
            'unique_case_ids': len({o['case'] for o in observations}),
            'source_code_sha256': frozen.get('sha256'), 'evaluator_code_sha256': current['sha256'],
            'same_evaluator_as_source': frozen == current, 'contrasts': contrasts,
            'notes': ['Recorded trajectories select which inputs are observed; turns are not independent samples.',
                      'The recorded admitted claims are used as-is; no new extraction or filtering is performed.',
                      'Alternative actions are not executed and receive no invented replies or success labels.',
                      'If source and evaluator fingerprints differ, these are current-controller diagnostics, not an original-version replay.'],
            'observations': observations, 'skipped': skipped}


def audit_csv(session):
    audit = decision_audit(session)
    keys = ('episode_id', 'case', 'step', 'subject', 'time', 'deadline', 'source_policy', 'provider', 'model', 'public_sha256',
            'admitted_sha256', 'admitted_status', 'compared_policy', 'action', 'recipient',
            'immediate_query_cost', 'recorded_action', 'recorded_recipient', 'scope')
    out = io.StringIO(newline='')
    writer = csv.DictWriter(out, fieldnames=keys)
    writer.writeheader()
    for observation in audit['observations']:
        for policy, action in observation['actions'].items():
            recorded = observation['recorded_action'] or {}
            row = {k: observation[k] for k in ('episode_id', 'case', 'step', 'subject', 'time', 'deadline', 'source_policy',
                                             'public_sha256', 'admitted_sha256', 'admitted_status')}
            row.update(provider=observation['profile']['provider'], model=observation['profile']['model'],
                       compared_policy=policy, action=action['action'], recipient=action['recipient'],
                       immediate_query_cost=observation['immediate_query_cost'][policy],
                       recorded_action=recorded.get('action'), recorded_recipient=recorded.get('recipient'),
                       scope='one_step_no_counterfactual_outcome')
            writer.writerow({k: "'" + v if isinstance(v, str) and v.startswith(('=', '+', '-', '@')) else v
                             for k, v in row.items()})
    return '\ufeff' + out.getvalue()


def report(session):
    summary = analysis.summarize(session)
    audit = decision_audit(session)
    selected = [c for c in session['dataset']['cases'] if c['id'] in session['config']['case_ids']]
    warnings = []
    if session['config']['mode'] != 'live': warnings.append('OFFLINE FIXTURE: not LLM performance.')
    if any(c['split'] != 'evaluation' for c in selected): warnings.append('Development/candidate cases: not independent evaluation.')
    if len(session['config']['models']) < 2: warnings.append('Single model profile: no between-chatbot comparison.')
    if not summary['complete']: warnings.append('Incomplete coverage: retain pending and failed attempts.')
    if not audit['same_evaluator_as_source']: warnings.append('Audit evaluator differs from source code fingerprint.')
    integrity = contracts.digest(session['dataset']) == session.get('dataset_sha256')
    if not integrity: warnings.append('Dataset integrity mismatch: do not interpret this as a validated frozen run.')
    if not session.get('study_design'): warnings.append('Legacy experiment: no study design envelope was recorded.')
    conditions = []
    for group in summary['groups']:
        rows = [r for r in session['runs'] if analysis.group_key(r) == group['condition']]
        counts = Counter(r['status'] for r in rows)
        returned = sorted({s['returned_model'] for r in rows for s in r['steps']
                           if isinstance(s.get('returned_model'), str) and s['returned_model']})
        if len(returned) > 1:
            warnings.append('Multiple returned model versions in profile: '+group['condition'])
        conditions.append(dict(group, not_started=group['assigned']-len(rows),
                               returned_models=returned,
                               statuses=dict(counts),
                               technical_failures=counts['error']+counts['interrupted_unknown'],
                               limit_failures=counts['deadline_missed']+counts['step_limit'],
                               validated_extraction_turns=sum(
                                   'accepted_extraction_checks' in s for r in rows for s in r['steps'])))
    return {'version': VERSION, 'experiment_id': session['id'], 'mode': session['config']['mode'],
            'purpose': session['config']['purpose'], 'dataset_integrity_matches': integrity,
            'study_design': copy.deepcopy(session.get('study_design')),
            'unique_case_ids': len(selected), 'family_labels': len({c['family'] for c in selected}),
            'repetitions_per_condition': session['config']['repeats'], 'conditions': conditions,
            'warnings': warnings, 'decision_audit': audit,
            'remaining_research_steps': ['Literature-backed contribution and related-work comparison.',
                'Independent scenarios, reviewer agreement and leakage checks.',
                'Predefined analysis, effect sizes and justified sample size.',
                'Live smoke tests for each selected model/profile before a larger study.',
                'Human-team or embodied validation if required by the final research claims.']}


def markdown_report(session):
    data = report(session)
    def text(value):
        return html.escape(str(value)).replace('|', '\\|').replace('\n', ' ')
    def json_block(value):
        return '\n'.join('    '+line for line in json.dumps(value,ensure_ascii=False,indent=2).splitlines())
    lines = ['# RSS2027 — Research progress and experiment report', '',
             f"Experiment: {text(session['name'])}", f"ID: {session['id']}",
             f"Mode: {data['mode']} / {data['purpose']}",
             f"Cases: {data['unique_case_ids']}; family labels: {data['family_labels']}; repetitions: {data['repetitions_per_condition']}",
             '', '## Scope', '',
             'Synthetic equipment coordination with scripted humans. No clinical or physical-robot validation. '
             'Family labels do not establish scenario independence. Repetitions and dialogue turns are not independent cases.', '',
             '## Frozen study design', '',
             json_block(data['study_design']) if data['study_design'] else 'No design envelope in this legacy run.',
             '', '## Results, including coverage and errors', '',
             '| Condition | Finished / assigned | Reference met / assigned | Questions | Cost (synthetic) | Raw / admitted extraction errors | Technical failures | Deadline / step limits | Not started |',
             '|---|---:|---:|---:|---:|---:|---:|---:|---:|']
    for g in data['conditions']:
        lines.append(f"| {text(g['condition'])} | {g['finished']}/{g['assigned']} | {g['outcome_met']}/{g['assigned']} | {g['questions']} | {g['query_cost']} | {g['extraction_error_turns']}/{g['accepted_extraction_error_turns']} | {g['technical_failures']} | {g['limit_failures']} | {g['not_started']} |")
    lines += ['', '## Provider usage and returned model versions', '',
              '| Condition | Attempted calls | Input tokens | Output tokens | Returned model IDs |',
              '|---|---:|---:|---:|---|']
    for g in data['conditions']:
        lines.append(f"| {text(g['condition'])} | {g['api_calls']} | {g['input_tokens']} | {g['output_tokens']} | {text(', '.join(g['returned_models']) or 'Not reported')} |")
    lines += ['', 'Extraction errors above count turns with at least one failed saved check, not independent cases or an accuracy rate.',
              '', '## Frozen configuration and actual batch budgets', '',
              json_block({'config': session['config'], 'batches': session.get('batches', []),
                                    'dataset_sha256': session.get('dataset_sha256'),
                                    'code_sha256': session.get('fingerprint', {}).get('sha256')})]
    audit = data['decision_audit']
    lines += ['', '## Controlled one-step diagnostic', '',
              f"Validated recorded turns: {audit['scored_turns']}; skipped turns: {audit['skipped_turns']}; unique public input hashes: {audit['unique_public_inputs']}.",
              'All compared controllers receive the same public state and the same admitted extraction for each saved input. '
              'Alternative actions are not executed: no counterfactual outcome, future dialogue, or total cost is inferred.', '',
              '| Compared policies | Different next actions / audited turns |', '|---|---:|']
    for c in audit['contrasts']:
        lines.append(f"| {text(' vs '.join(c['policies']))} | {c['different_actions']}/{c['observations']} |")
    lines += ['', '## Limitations and integrity notes', '']
    lines += ['- ' + text(note) for note in data['warnings'] + audit['notes']]
    lines += ['', '## Work still required for the paper', '']
    lines += ['- ' + text(note) for note in data['remaining_research_steps']]
    lines += ['', 'Tokens are provider-reported. Synthetic interruption cost is not API currency. '
              'A frozen design is not a preregistration or a power analysis. The oracle gate is not a real robot safety mechanism.', '']
    return '\n'.join(lines)
