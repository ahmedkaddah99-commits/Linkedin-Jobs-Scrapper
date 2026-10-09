"""Download official occupation aliases and build a reproducible title dictionary."""
import csv
import hashlib
import json
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import urlopen
from urllib.error import HTTPError

from scripts.audit_title_collars import normalize_title

ROOT = Path(__file__).resolve().parents[1]
SOURCES = ROOT / 'data/audit/title_collar_2026-10-08/web_sources'


def page(offset):
    path = SOURCES / f'esco_de_page_{offset}.json'
    url = f'https://ec.europa.eu/esco/api/search?type=occupation&language=de&limit=100&offset={offset}&full=true'
    if not path.exists():
        for attempt in range(4):
            try:
                with urlopen(url, timeout=180) as response:
                    path.write_bytes(response.read())
                break
            except HTTPError as error:
                if error.code == 500:
                    # Some full multilingual records fail at the official API.
                    # Save the returned preferred labels without inventing aliases.
                    with urlopen(url.replace('full=true', 'full=false'), timeout=180) as response:
                        path.write_bytes(response.read())
                    break
                if attempt == 3:
                    raise
                time.sleep(2)
            except Exception:
                if attempt == 3:
                    raise
                time.sleep(2)
    return json.loads(path.read_text(encoding='utf-8-sig'))


def main():
    SOURCES.mkdir(parents=True, exist_ok=True)
    probe = ROOT / 'data/audit/title_collar_2026-10-08/esco_probe.json'
    if probe.exists():
        (SOURCES / 'esco_de_page_0.json').write_bytes(probe.read_bytes())
    first = page(0)
    count = (first['total'] + first['limit'] - 1) // first['limit']
    with ThreadPoolExecutor(max_workers=4) as pool:
        pages = [first, *pool.map(page, range(1, count))]
    occupations = {r['uri']: r for p in pages for r in p['_embedded']['results']}
    assert len(occupations) == first['total'], (len(occupations), first['total'])
    entries = {}
    generic = {'assistant', 'associate', 'specialist', 'manager', 'engineer', 'technician', 'operator', 'helper', 'worker', 'leader', 'supervisor', 'director', 'head', 'student', 'intern', 'officer', 'staff', 'employee', 'coordinator', 'agent', 'clerk', 'lead', 'expert', 'professional', 'berater', 'mitarbeiter', 'fachkraft', 'techniker', 'leiter', 'leitung', 'assistent', 'assistenz', 'spezialist', 'praktikant', 'hilfskraft', 'inspector', 'inspektor', 'controller', 'checker', 'inspector general'}

    def add(label, collar, source, code):
        # Slash-separated German male/female labels are separate title phrases.
        for part in label.split('/'):
            term = normalize_title(part)
            if not term or term in generic or len(term) < 6 or len(term.split()) > 12:
                continue
            record = entries.setdefault(term, {'categories': set(), 'references': set()})
            record['categories'].add(collar)
            record['references'].add((source, code))

    for r in occupations.values():
        code = str(r.get('code', ''))
        if not code or code[0] not in '123456789':
            continue
        collar = 'white' if code[0] in '1234' or code.startswith('52') else 'blue'
        for lang in ('de', 'en'):
            labels = [r.get('preferredLabel', {}).get(lang, ''), *r.get('alternativeLabel', {}).get(lang, [])]
            for label in labels:
                add(label, collar, 'ESCO', code)
    onet = SOURCES / 'onet_31_0_job_titles.csv'
    with onet.open(encoding='utf-8-sig', newline='') as stream:
        for r in csv.DictReader(stream):
            code = r['O*NET-SOC Code']
            collar = 'white' if int(code[:2]) in {11, 13, 15, 17, 19, 21, 23, 25, 27, 29, 41, 43} else 'blue'
            add(r['Job Title'], collar, 'O*NET', code)
    dictionary = {'version': 'official_occupation_aliases_2026_10_08',
        'retrieved_at': datetime.now(timezone.utc).isoformat(),
        'sources': [{'name': 'ESCO web API', 'url': 'https://ec.europa.eu/esco/api/search', 'occupations': len(occupations), 'note': 'API dataset version is not asserted from the portal version.'}, {'name': 'O*NET 31.0 Job Titles', 'url': 'https://www.onetcenter.org/dl_files/database/db_31_0_csv/job_titles.csv', 'license': 'https://www.onetcenter.org/license_db.html'}],
        'mapping_policy': 'Runr interpretation, not source collar labels. ESCO groups 1-4 and 52 white; 5-9 except 52 blue. O*NET SOC 11-29,41,43 white; other groups blue. Existing explicit rules and owner overrides take precedence. Conflicting aliases remain unresolved.',
        'terms': {term: {'collar': next(iter(r['categories'])) if len(r['categories']) == 1 else 'unresolved', 'references': sorted(r['references'])} for term, r in sorted(entries.items())},
        'raw_source_sha256': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in SOURCES.glob('*') if p.is_file()}}
    (ROOT / 'scripts/title_occupation_dictionary.json').write_text(json.dumps(dictionary, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'Built dictionary with {len(entries)} normalized aliases', flush=True)


if __name__ == '__main__':
    main()
