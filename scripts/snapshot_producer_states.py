"""Copy one SQLite producer state to a consistent, run-scoped read snapshot."""

from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
from pathlib import Path
from time import monotonic


def snapshot_database(source: Path, destination: Path) -> dict[str, int | float]:
    source = source.resolve(strict=True)
    destination = destination.resolve(strict=False)
    if destination.exists():
        raise FileExistsError(destination)
    if source == destination:
        raise ValueError("Source and destination must differ")
    destination.parent.mkdir(parents=True, exist_ok=True)
    source_bytes = source.stat().st_size
    if shutil.disk_usage(destination.parent).free < source_bytes * 2:
        raise OSError("Insufficient free space for a producer-state snapshot")
    started = monotonic()
    try:
        with sqlite3.connect(f"file:{source.as_posix()}?mode=ro", uri=True) as source_db:
            with sqlite3.connect(destination) as snapshot_db:
                source_db.backup(snapshot_db, pages=1024, sleep=0.05)
    except BaseException:
        destination.unlink(missing_ok=True)
        raise
    return {
        "source_bytes": source_bytes,
        "snapshot_bytes": destination.stat().st_size,
        "duration_seconds": round(monotonic() - started, 3),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(snapshot_database(args.source, args.destination), sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
