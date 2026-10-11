"""Dry-run by default; emit a bounded catalog storage maintenance receipt."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import shutil
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from backend.acquisition.storage_retention import maintain_catalog_storage


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir', type=Path, default=Path(os.environ.get('RUNR_DATA_DIR','/var/lib/runr/acquisition-data')))
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--batch-size', type=int, default=1000)
    parser.add_argument('--max-seconds', type=float, default=30)
    parser.add_argument('--max-batches', type=int, default=100)
    parser.add_argument('--metrics-file', type=Path)
    parser.add_argument('--physical-reclamation-report', action='store_true', help='Report only; never runs VACUUM. Requires separately reviewed supported operator procedure.')
    args = parser.parse_args()
    receipt = maintain_catalog_storage(args.data_dir/'backend.sqlite3', apply=args.apply,
        batch_size=args.batch_size, max_seconds=args.max_seconds, max_batches=args.max_batches)
    if args.data_dir.exists():
        free = shutil.disk_usage(args.data_dir).free
        receipt['local_free_bytes'] = free
        receipt['local_capacity_warning'] = free < receipt['capacity_warning_threshold_bytes']
    receipt['remote_capacity_check'] = 'database allocated pages are measured; organization billing usage must be checked separately'
    if args.physical_reclamation_report:
        receipt['physical_reclamation_report'] = dict(performed=False,
            required='Verified provider support, recent backup, exclusive maintenance window, enough temporary space',
            automatic_vacuum=False)
    if args.metrics_file:
        metrics = {
            'runr_catalog_storage_maintenance_last_success_timestamp_seconds': time.time(),
            'runr_catalog_storage_allocated_bytes': receipt.get('allocated_bytes', 0),
            'runr_catalog_storage_capacity_warning': int(receipt.get('capacity_warning', False)),
            'runr_catalog_storage_capacity_critical': int(receipt.get('capacity_critical', False)),
            'runr_catalog_storage_retention_blocked': int(bool(receipt.get('source_phase_skipped'))),
            'runr_catalog_storage_deleted_rows': sum(receipt.get(key, 0) for key in (
                'deleted_memberships', 'deleted_publications', 'deleted_rejections',
                'deleted_empty_provenance', 'deleted_source_observations')),
        }
        args.metrics_file.parent.mkdir(parents=True, exist_ok=True)
        temporary = args.metrics_file.with_suffix('.prom.tmp')
        temporary.write_text(''.join(f'{key} {value}\n' for key, value in metrics.items()), encoding='utf-8')
        temporary.replace(args.metrics_file)
    print(json.dumps(receipt, sort_keys=True))


if __name__ == '__main__':
    main()
