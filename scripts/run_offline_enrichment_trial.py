"""Generate the offline deterministic enrichment trial reports.

The script is intentionally limited to checked-in fixtures and local
providers. It does not accept provider URLs, credentials, production targets,
or publication options.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.enrichment.evaluation import (
    ALTERNATE_RULE_VERSION,
    DEFAULT_RULE_VERSION,
    OfflineTrialOrchestrator,
    render_markdown_report,
    report_json,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the offline deterministic enrichment trial")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("docs/reports"),
        help="Directory for report-only Markdown and JSON artifacts",
    )
    args = parser.parse_args()

    orchestrator = OfflineTrialOrchestrator()
    baseline, candidate, replay = orchestrator.replay(
        baseline_rule_version=DEFAULT_RULE_VERSION,
        candidate_rule_version=ALTERNATE_RULE_VERSION,
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    stem = "deterministic_enrichment_trial_2026-08-12"
    (args.output_dir / f"{stem}.json").write_text(report_json(baseline), encoding="utf-8")
    (args.output_dir / f"{stem}.md").write_text(render_markdown_report(baseline, replay), encoding="utf-8")
    print(f"wrote {args.output_dir / f'{stem}.md'}")
    print(f"wrote {args.output_dir / f'{stem}.json'}")
    print(f"promotion recommendation: {baseline.report['promotion']['recommendation']}")
    print(f"replay changes: {replay.changed_outputs}/{replay.compared_outputs}")
    del candidate
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
