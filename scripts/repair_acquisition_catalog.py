"""Run the shared acquisition catalog repair pass.

Default is a read-only dry run. Use --apply only after reviewing the JSON
report; even apply mode does not delete rows or merge ambiguous companies.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend import create_backend
from backend.acquisition.repair import repair_acquisition_catalog


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-root", default=".backend_data", help="SQLite database path or backend data directory")
    parser.add_argument("--apply", action="store_true", help="Apply safe annotations and unambiguous company ownership fixes")
    args = parser.parse_args()
    application = create_backend(Path(args.database_root), storage_backend="sqlite")
    store = application.repositories.acquisition_store
    if store is None:
        raise RuntimeError("acquisition_store_unavailable")
    print(json.dumps(repair_acquisition_catalog(store, apply=bool(args.apply)), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
