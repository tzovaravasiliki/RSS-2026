"""Conservative, bounded-language support filter for verification claims.

Uses public message text only. This is a lexical engineering guard for the
Greek/English constructions below, NOT a general semantic verifier. It never
adds claims, changes their value, refreshes timestamps, or reads gold labels.
Unrecognized constructions are rejected and remain unknown to controllers.
"""
import re
import unicodedata

VERSION = 'explicit-support-v1'


def normalize(text):
    return ''.join(c for c in unicodedata.normalize('NFD', text.casefold())
                   if unicodedata.category(c) != 'Mn')


# Reject questions, uncertainty, prospective/conditional and reported-negation
# clauses. A later separate, explicit assertion can still be recognized.
NON_ASSERTION = re.compile(
    r'\b(?:αν|εαν|θα|να|ισως|μηπως|υποθετ\w*|δεν\s+(?:γνωριζ\w*|ξερ\w*|ειπα|λεω)|'
    r'if|unless|whether|maybe|might|could|can|will|would|should|must|please|unsure|unknown|'
    r'(?:do\s+not|don.t)\s+know|did\s+not\s+say)\b')
CHECK = re.compile(r'\b(?:ελεγχ\w*|check|verification|inspection)\b')
COMPLETED = re.compile(r'\b(?:ολοκληρωθηκε|ολοκληρωθει|ολοκληρωμεν\w*|completed|complete|passed)\b')
NEGATED_COMPLETION = re.compile(
    r'\b(?:δεν|οχι|μη|not|never)\s+(?:(?:εχει|ειναι|ηταν|ακομη|ηδη|ποτε|πληρως|'
    r'is|has|had|been|yet|fully|was|ever|now|currently)\s+){0,4}$')
PENDING = re.compile(r'\b(?:εκκρεμ\w*|pending|incomplete|unfinished|failed)\b')
CONFIRMATION = re.compile(r'\b(?:επιβεβαιωσ\w*|confirmation|acknowledg\w*)\b')
CART = re.compile(r'\bC\d+(?:-[A-Za-z]+)?\b', re.IGNORECASE)


def explicit_status(text):
    """Return (set of explicitly recognized Boolean statuses, matched clauses).

    Empty set means no recognized assertion, never False. Conflicting statuses
    in a single message are ambiguous; neither can support a model claim.
    """
    statuses, clauses = set(), []
    parts = re.split(r'([.!?;\n\u037e]+)', text)
    for i in range(0, len(parts), 2):
        original = parts[i]
        punctuation = parts[i+1] if i+1 < len(parts) else ''
        clause = normalize(original.strip())
        if (not clause or any(c in punctuation for c in '?;\u037e')
                or any(c in original for c in '\"«»“”‘’')
                or NON_ASSERTION.search(clause) or not CHECK.search(clause)):
            continue
        # "Confirmation is pending" does not assert an incomplete check.
        if CONFIRMATION.search(clause):
            continue
        values = set()
        completions = list(COMPLETED.finditer(clause))
        if completions:
            # Scope negation to the completion phrase. An unrelated "not"
            # elsewhere in the sentence must not invert a positive result.
            for match in completions:
                values.add(not bool(NEGATED_COMPLETION.search(clause[:match.start()])))
        elif PENDING.search(clause) and not re.search(r'\b(?:δεν|οχι|μη|not|never)\b', clause):
            values.add(False)
        if values:
            statuses.update(values)
            clauses.append(original.strip())
    return statuses, clauses


def filter_claims(items, public):
    """Return indexes of supported claims and an audit entry for every item.

    Cart binding is deliberately conservative: a message naming multiple
    distinct canonical carts cannot support a claim in this small grammar.
    Conflict flags are not resolved by this filter.
    """
    messages = {m['message_id']:m for m in public['messages'] if m['speaker'] != 'ROBOT'}
    task = public['task']
    aliases = task.get('aliases', {})
    canonical = lambda value: aliases.get(value, value)
    accepted, audit = [], []
    for index, item in enumerate(items):
        message = messages[item['message_id']]
        values, clauses = explicit_status(message['text'])
        carts = set(CART.findall(message['text']))
        # Use exact public spellings for case-insensitive occurrences.
        known = {x.casefold():x for x in task['known_subjects']}
        carts = {canonical(known.get(x.casefold(), x)) for x in carts}
        if not carts:
            carts = {canonical(task['default_subject'])}
        target = canonical(item['subject'])
        reason = 'supported'
        if not values:
            reason = 'no_explicit_status'
        elif len(values) != 1:
            reason = 'ambiguous_status'
        elif item['value'] not in values:
            reason = 'polarity_mismatch'
        elif len(carts) != 1 or target not in carts:
            reason = 'ambiguous_or_wrong_cart'
        supported = reason == 'supported'
        if supported:
            accepted.append(index)
        audit.append({**item, 'accepted':supported, 'reason':reason,
                      'recognized_status':('completed' if True in values else 'incomplete')
                          if len(values) == 1 else 'unknown_or_ambiguous',
                      'supporting_clauses':clauses})
    return accepted, audit
