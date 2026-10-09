"""Show receipt metric structure and enumerated outcomes without job payloads."""
import json
from pathlib import Path
from observe import SOURCES, json_objects

for source in SOURCES:
    objects = json_objects(Path('/srv/runr/exports/receipts') / f'{source}-latest-metrics.json')
    print(json.dumps({'source': source, 'objects': len(objects), 'summaries': [
        {'keys': sorted(obj), 'status': obj.get('status') if obj.get('status') in {
            'completed', 'partial', 'failed', 'discovery_failed', 'source_failed', 'confirmed_complete'
        } else None, 'nested_keys': {key: sorted(value) for key, value in obj.items() if isinstance(value, dict)}}
        for obj in objects[-6:] if isinstance(obj, dict)
    ]}))
