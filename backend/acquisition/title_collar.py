"""Read-only runtime use of the existing, owner-approved title decisions."""
import html
import json
import os
import re
import unicodedata
from functools import lru_cache
from pathlib import Path


def normalize(title):
    text = unicodedata.normalize('NFKC', html.unescape(str(title or ''))).casefold()
    text = text.replace('\u00ad', '').replace('ä', 'ae').replace('ö', 'oe').replace('ü', 'ue').replace('ß', 'ss')
    text = re.sub(r'(?<=\w)[:*/_]innen\b', 'innen', text)
    text = re.sub(r'(?<=\w)[:*/_]in\b', 'in', text)
    return re.sub(r'[^\w]+', ' ', text).strip()


@lru_cache(maxsize=4)
def load_policy(path):
    policy = json.loads(Path(path).read_text(encoding='utf-8'))
    policy['compiled'] = {category: [re.compile(p) for p in rules.values()]
                          for category, rules in policy['rules'].items() if category in ('white', 'blue', 'ambiguous', 'policy')}
    return policy


def classify_title(title, *, policy_path=None):
    path = policy_path or os.environ.get('RUNR_TITLE_COLLAR_POLICY')
    if not path:
        return None
    policy = load_policy(str(path))
    text = normalize(title)
    if text in policy['decisions']:
        return policy['decisions'][text]
    matches = {category: any(rule.search(text) for rule in rules) for category, rules in policy['compiled'].items()}
    if matches.get('policy') or (matches.get('white') and matches.get('blue')):
        return 'blue'
    if matches.get('ambiguous'):
        return None
    if matches.get('white'):
        return 'white'
    if matches.get('blue'):
        return 'blue'
    words = text.split()
    found = set()
    for start in range(len(words)):
        for size in range(1, min(policy['max_words'], len(words)-start)+1):
            term = ' '.join(words[start:start+size])
            if term in policy['terms']:
                found.add(policy['terms'][term]['collar'])
    return next(iter(found)) if len(found) == 1 and 'unresolved' not in found else None
