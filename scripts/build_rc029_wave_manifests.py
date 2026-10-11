"""Build deterministic RC-029 wave manifests from an RC-005 manifest."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.application.expansion_wave_manifest import build_expansion_wave_manifest
from backend.application.source_eligibility_manifest import load_manifest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cohort", choices=("all", "pilot", "expansion"), default="all")
    parser.add_argument("--wave-size", type=int, required=True)
    parser.add_argument("--request-cap", type=int, required=True)
    parser.add_argument("--credit-cap", type=float, required=True)
    parser.add_argument("--max-failure-rate", type=float, required=True)
    parser.add_argument("--max-queue-age-seconds", type=int, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    source_manifest = load_manifest(args.manifest)
    wave_manifest = build_expansion_wave_manifest(
        source_manifest,
        cohort=args.cohort,
        wave_size=args.wave_size,
        request_cap=args.request_cap,
        credit_cap=args.credit_cap,
        max_failure_rate=args.max_failure_rate,
        max_queue_age_seconds=args.max_queue_age_seconds,
    )
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(wave_manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "wave_manifest_hash": wave_manifest["wave_manifest_hash"], "waves": len(wave_manifest["waves"])}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
