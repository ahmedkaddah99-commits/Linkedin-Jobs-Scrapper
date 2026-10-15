"""Cheap, deterministic pre-detail job-title filter for the owner's target roles."""
from __future__ import annotations

import json, re
from functools import lru_cache
from pathlib import Path

DEFAULT_POLICY_PATH = Path(__file__).resolve().parents[2] / "data" / "job_role_policy.json"

@lru_cache(maxsize=4)
def load_policy(path: str = str(DEFAULT_POLICY_PATH)):
    return json.loads(Path(path).read_text(encoding="utf-8"))

def normalize_title(title: str) -> str:
    text = str(title or "").casefold().translate(str.maketrans({'ä':'ae','ö':'oe','ü':'ue','ß':'ss'}))
    return re.sub(r"[^a-z0-9+#]+", " ", text).strip()

def title_matches(title: str, *, policy_path: str | None = None) -> bool:
    text = normalize_title(title)
    if not text:
        return False
    policy = load_policy(policy_path or str(DEFAULT_POLICY_PATH))
    if any(re.search(pattern, text) for pattern in policy["excluded_title_patterns"]):
        return False
    return any(re.search(pattern, text) for pattern in policy["included_title_patterns"])

def rejection_reason(title: str) -> str:
    return "owner_role_policy_excluded" if not title_matches(title) else ""

def exceeds_experience_limit(text: str, *, max_years: int = 2) -> bool:
    """Require experience context; do not confuse company age/benefits with requirements."""
    import html
    value = html.unescape(re.sub(r"<[^>]+>", " ", str(text or ""))).casefold()
    value = value.translate(str.maketrans({"\u00e4": "ae", "\u00f6": "oe", "\u00fc": "ue", "\u00df": "ss", "\u2013": "-", "\u2014": "-"}))
    numbers = {"one":1,"two":2,"three":3,"four":4,"five":5,"six":6,"seven":7,"eight":8,"nine":9,"ten":10,"ein":1,"eine":1,"einem":1,"zwei":2,"drei":3,"vier":4,"fuenf":5,"sechs":6,"sieben":7,"acht":8,"neun":9,"zehn":10}
    value = re.sub(r"\b("+"|".join(numbers)+r")\b", lambda m: str(numbers[m[0]]), value)
    for sentence in re.split(r"[.!?;\n]", value):
        if not re.search(r"experience|erfahrung|berufspraxis|berufstaetigkeit", sentence):
            continue
        if re.search(r"preferred|desirable|idealerweise|wuenschenswert|von vorteil|a plus|internship|praktik", sentence):
            continue
        for m in re.finditer(r"(?P<prefix>more than|over|mehr als|ueber)?\s*(?P<low>\d+)\s*(?:[-/]|to|bis)?\s*(?P<high>\d+)?\s*\+?\s*(?:years?|jahr(?:e|en)?|jaehrig\w*)", sentence):
            # Required lower bound: 2-3 years can accept someone with two years.
            n = int(m['low'])
            if n > max_years or (m['prefix'] and n >= max_years):
                return True
    return False


def accepts_record(record):
    title = record.get('job_title') or record.get('title') or record.get('title_raw') or ''
    description = record.get('description_text') or record.get('description') or record.get('full_description') or record.get('description_html') or ''
    return title_matches(title) and not exceeds_experience_limit(description)
