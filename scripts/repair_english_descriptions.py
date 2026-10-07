"""Requeue current German descriptions and unattempted supplemental fields.

Dry run by default. Saves targeted row IDs before --apply mutates the queue.
"""
import argparse
import json
import re
import time
from pathlib import Path
from backend.config import load_project_dotenv
from backend.application.description_translation import source_language
from scripts.process_catalog_enrichment import execute


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--audit', type=Path, required=True)
    args = parser.parse_args()
    load_project_dotenv()
    query = """SELECT q.version_id,q.state,q.gap_pass_attempted,d.summary_json
        FROM acquisition_publication_head h
        JOIN acquisition_publication_jobs p ON p.publication_id=h.publication_id
        JOIN canonical_jobs j ON j.canonical_job_id=p.canonical_job_id
        JOIN job_enrichment_queue q ON q.version_id=j.current_version_id
        LEFT JOIN job_description_intelligence d ON d.version_id=q.version_id AND d.content_hash=q.content_hash
        WHERE h.head_id=1 AND q.version_id>? ORDER BY q.version_id LIMIT 200"""
    rows = []
    cursor = ''
    while True:
        for attempt in range(3):
            try:
                page = execute(query, (cursor,))
                break
            except TimeoutError:
                if attempt == 2:
                    raise
                time.sleep(2)
        if not page:
            break
        rows.extend(page)
        cursor = page[-1]['version_id']
        print(json.dumps({'event': 'repair_inventory', 'read': len(rows)}), flush=True)
    targets = []
    for row in rows:
        summary = json.loads(row['summary_json'] or '{}')
        text = ' '.join(str(item.get('text', '') if isinstance(item, dict) else item)
                        for value in summary.values() for item in (value if isinstance(value, list) else [value]))
        german = len(text) >= 80 and bool(re.search(r'\b(?:und|für|Ihre|Sie|Aufgaben|Erfahrung|Kenntnisse|mit|Wir)\b', text)) and source_language(text) == 'de'
        if german or row['gap_pass_attempted'] == 0:
            targets.append({**row, 'german': german})
    args.audit.parent.mkdir(parents=True, exist_ok=True)
    args.audit.write_text(json.dumps(targets, ensure_ascii=False), encoding='utf-8')
    if args.apply:
        for offset in range(0, len(targets), 100):
            batch = json.dumps([{'id': row['version_id'], 'error': 'english_description_repair' if row['german'] else ''}
                                for row in targets[offset:offset + 100]])
            execute("""UPDATE job_enrichment_queue INDEXED BY sqlite_autoindex_job_enrichment_queue_1
                SET state='pending',next_attempt_at='',gap_pass_attempted=0,
                error_code=(SELECT json_extract(value,'$.error') FROM json_each(?)
                            WHERE json_extract(value,'$.id')=job_enrichment_queue.version_id)
                WHERE version_id IN (SELECT json_extract(value,'$.id') FROM json_each(?)) AND state!='processing'""",
                (batch, batch))
    print(json.dumps({'targeted': len(targets), 'german': sum(r['german'] for r in targets), 'applied': args.apply}))


if __name__ == '__main__':
    main()
