"""Bounded thirty-day catalog discovery expiry; dry-run by default."""
import argparse
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from backend.acquisition.job_lifecycle import maintain_job_lifecycle


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir', type=Path, default=Path(os.environ.get('RUNR_DATA_DIR', '/var/lib/runr/acquisition-data')))
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--batch-size', type=int, default=100)
    parser.add_argument('--max-batches', type=int, default=20)
    parser.add_argument('--max-seconds', type=float, default=30)
    parser.add_argument('--receipt', type=Path)
    args = parser.parse_args()
    result = maintain_job_lifecycle(args.data_dir / 'backend.sqlite3', apply=args.apply,
        batch_size=args.batch_size, max_batches=args.max_batches, max_seconds=args.max_seconds)
    rendered = json.dumps(result, sort_keys=True)
    if args.receipt:
        args.receipt.parent.mkdir(parents=True, exist_ok=True)
        temporary = args.receipt.with_suffix('.tmp')
        temporary.write_text(rendered + '\n', encoding='utf-8')
        temporary.replace(args.receipt)
    print(rendered)


if __name__ == '__main__':
    main()
