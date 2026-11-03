"""Synthetic temporal environment and shared gold-backed dispatch evaluator."""
from __future__ import annotations
import copy
from dataclasses import dataclass, replace

POLICIES = ('legacy_reuse', 'always_reverify', 'cost_aware')


@dataclass(frozen=True)
class Evidence:
    subject: str
    value: bool
    source: str
    timestamp: int
    ttl: int = 100


@dataclass(frozen=True)
class PublicState:
    case_id: str
    subject: str
    now: int
    deadline: int
    evidence: tuple
    aliases: dict
    conflict: bool
    sources: tuple
    probability_knows: dict
    available_at: dict
    query_cost: dict
    attempted: tuple
    received_answer: bool


@dataclass(frozen=True)
class Scenario:
    public: PublicState
    actual_verified: bool
    actual_access: tuple
    family: str


def canonical(subject, aliases):
    return aliases.get(subject, subject)


def current_evidence(view):
    """Shared binding/freshness/contradiction check. Independent of hidden truth."""
    if view.conflict:
        return None
    valid = [e for e in view.evidence if canonical(e.subject, view.aliases) == canonical(view.subject, view.aliases)
             and 0 <= view.now - e.timestamp <= e.ttl]
    return max(valid, key=lambda e: e.timestamp).value if valid else None


def choose(policy, view):
    if policy not in POLICIES:
        raise ValueError('Unknown policy')
    if policy == 'legacy_reuse' and view.evidence:
        # Deliberately weak stress baseline: ignores binding, TTL and conflicts.
        latest = max(view.evidence, key=lambda e: e.timestamp)
        return {'action': 'dispatch' if latest.value else 'escalate', 'recipient': None}
    value = current_evidence(view)
    # Always-reverify deliberately incurs one new query even if evidence is valid.
    if policy != 'always_reverify' or view.received_answer:
        if value is not None:
            return {'action': 'dispatch' if value else 'escalate', 'recipient': None}
    remaining = [h for h in view.sources if h not in view.attempted]
    if not remaining:
        return {'action': 'escalate', 'recipient': None}
    if policy == 'cost_aware':
        possible = [h for h in remaining if view.probability_knows[h] > 0 and
                    max(view.now, view.available_at[h]) + 1 <= view.deadline]
        if not possible:
            return {'action': 'escalate', 'recipient': None}
        # Greedy one-step heuristic, NOT an optimal VOI or learned policy.
        def score(h):
            return 30. * view.probability_knows[h] - view.query_cost[h] - max(0, view.available_at[h]-view.now)
        recipient = max(possible, key=score)
    else:
        recipient = remaining[0]
    return {'action': 'wait' if view.available_at[recipient] > view.now else 'ask',
            'recipient': recipient}


class Environment:
    def __init__(self, scenario):
        self.scenario = copy.deepcopy(scenario)
        self.view = copy.deepcopy(scenario.public)

    def step(self, action):
        view = self.view
        kind, human = action['action'], action['recipient']
        event = {'time': view.now, 'action': kind, 'recipient': human}
        if kind == 'dispatch':
            supported = current_evidence(view) is True
            safe = self.scenario.actual_verified
            event.update(result='delivered' if safe and supported else 'dispatch_blocked',
                         truth_violation=not safe, unsupported=not supported)
        elif kind == 'escalate':
            event.update(result='escalated', actual_verified=self.scenario.actual_verified)
        elif kind == 'wait':
            self.view = replace(view, now=view.now+1)
            event['result'] = 'waited'
        elif kind == 'ask':
            if human not in view.sources or view.available_at[human] > view.now:
                raise ValueError('Invalid or unavailable query recipient')
            event['cost'] = view.query_cost[human]
            knowledge = human in self.scenario.actual_access
            answer = self.scenario.actual_verified if knowledge else 'unknown'
            event.update(result='answered' if knowledge else 'unknown', answer=answer,
                         subject=view.subject)
            probabilities = dict(view.probability_knows)
            if not knowledge:
                probabilities[human] = 0.
            evidence = view.evidence + ((Evidence(view.subject, answer, human, view.now+1),) if knowledge else ())
            self.view = replace(view, now=view.now+1, evidence=evidence,
                conflict=False if knowledge else view.conflict,
                probability_knows=probabilities,
                attempted=view.attempted+(human,), received_answer=view.received_answer or knowledge)
        else:
            raise ValueError('Invalid action')
        if self.view.now > view.deadline and kind in ('ask', 'wait'):
            event['result'] = 'deadline_missed'
        return event
