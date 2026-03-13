import argparse
import json
import re
from pathlib import Path
from typing import Dict, List

from job_seeker_config import cfg_int, cfg_str, load_job_seeker_config

GERMAN_CHAR_SET = set("\u00e4\u00f6\u00fc\u00c4\u00d6\u00dc\u00df")
DEFAULT_GERMAN_SPECIAL_CHAR_THRESHOLD = 20
FRENCH_CHAR_SET = set(
    "\u00e0\u00e2\u00e6\u00e7\u00e8\u00e9\u00ea\u00eb\u00ee\u00ef\u00f4\u0153\u00f9\u00fb\u00fc\u00ff"
    "\u00c0\u00c2\u00c6\u00c7\u00c8\u00c9\u00ca\u00cb\u00ce\u00cf\u00d4\u0152\u00d9\u00db\u00dc\u0178"
)
DEFAULT_FRENCH_SPECIAL_CHAR_THRESHOLD = 0
SPANISH_CHAR_SET = set(
    "\u00e1\u00e9\u00ed\u00f1\u00f3\u00fa\u00fc\u00c1\u00c9\u00cd\u00d1\u00d3\u00da\u00dc\u00a1\u00bf"
)
DEFAULT_SPANISH_SPECIAL_CHAR_THRESHOLD = 0
TITLE_GENDER_MARKER_PATTERN = re.compile(
    r"(?i)\b(?:m/w/d|w/m/d|d/m/w|m\|w\|d|w\|m\|d|d\|m\|w|all genders)\b"
)

CEFR_LEVEL_ORDER = {
    "A1": 1,
    "A2": 2,
    "B1": 3,
    "B2": 4,
    "C1": 5,
    "C2": 6,
}

GERMAN_LEVEL_REQUIREMENT_PATTERNS = [
    (re.compile(r"\bc2(?:\s*[-/]?\s*level)?\s*(?:in\s+)?(?:german|deutsch)\b", re.IGNORECASE), "C2"),
    (re.compile(r"\bc1(?:\s*[-/]?\s*level)?\s*(?:in\s+)?(?:german|deutsch)\b", re.IGNORECASE), "C1"),
    (re.compile(r"\b(?:mindestens|min\.?)\s*c1\s*(?:in\s+)?(?:german|deutsch)\b", re.IGNORECASE), "C1"),
    (re.compile(r"\bfluent(?:\s+in)?\s+german\b", re.IGNORECASE), "C1"),
    (re.compile(r"\bnative\s+german\b", re.IGNORECASE), "C2"),
    (re.compile(r"\bmuttersprach(?:lich(?:e|en|er)?)?\s*(?:deutsch|german)\b", re.IGNORECASE), "C2"),
    (re.compile(r"\bverhandlungssicher(?:e|en)?\s+deutschkenntnisse\b", re.IGNORECASE), "C1"),
    (re.compile(r"\bflie(?:ss|ß)end(?:e|en|er)?\s+deutschkenntnisse\b", re.IGNORECASE), "C1"),
    (re.compile(r"\bsehr\s+gute\s+deutschkenntnisse\b", re.IGNORECASE), "C1"),
    (re.compile(r"\bprofessional(?:\s+level)?\s+german\b", re.IGNORECASE), "C1"),
]


def load_json_file(path: Path) -> List[Dict]:
    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)
    if not isinstance(data, list):
        raise ValueError(f"Expected a list in {path}, got: {type(data).__name__}")
    return data


def save_json_file(path: Path, payload: List[Dict]) -> None:
    with path.open("w", encoding="utf-8") as file:
        json.dump(payload, file, indent=4, ensure_ascii=False)


def count_german_special_chars(text: str) -> int:
    return sum(1 for char in (text or "") if char in GERMAN_CHAR_SET)


def count_special_chars(text: str, char_set: set) -> int:
    return sum(1 for char in (text or "") if char in char_set)


def normalize_title_for_language_rules(title: str) -> str:
    normalized = TITLE_GENDER_MARKER_PATTERN.sub(" ", title or "")
    return re.sub(r"\s+", " ", normalized).strip()


def normalize_cefr_level(raw_level: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]", "", str(raw_level or "").upper())
    return cleaned if cleaned in CEFR_LEVEL_ORDER else "B2"


def detect_reasons(
    job: Dict,
    german_special_char_threshold: int,
    french_special_char_threshold: int,
    spanish_special_char_threshold: int,
    max_german_level: str,
) -> List[str]:
    title = str(job.get("title") or "")
    description = str(job.get("full_description") or "")
    normalized_title = normalize_title_for_language_rules(title)
    combined_text = f"{normalized_title}\n{description}"

    reasons: List[str] = []
    allowed_german_level = normalize_cefr_level(max_german_level)
    max_level_rank = CEFR_LEVEL_ORDER[allowed_german_level]

    german_char_count = count_german_special_chars(combined_text)
    if german_special_char_threshold >= 0 and german_char_count > german_special_char_threshold:
        reasons.append(
            "Text contains German-specific letters above threshold "
            f"({german_char_count}>{german_special_char_threshold})"
        )

    french_char_count = count_special_chars(combined_text, FRENCH_CHAR_SET)
    if french_char_count > french_special_char_threshold:
        reasons.append(
            "Text contains French-specific letters above threshold "
            f"({french_char_count}>{french_special_char_threshold})"
        )

    spanish_char_count = count_special_chars(combined_text, SPANISH_CHAR_SET)
    if spanish_char_count > spanish_special_char_threshold:
        reasons.append(
            "Text contains Spanish-specific letters above threshold "
            f"({spanish_char_count}>{spanish_special_char_threshold})"
        )

    for pattern, required_level in GERMAN_LEVEL_REQUIREMENT_PATTERNS:
        if pattern.search(combined_text) and CEFR_LEVEL_ORDER[required_level] > max_level_rank:
            reasons.append(
                f"German level requirement ({required_level}) is above configured maximum ({allowed_german_level})"
            )

    # preserve order, remove duplicates
    return list(dict.fromkeys(reasons))


def main() -> int:
    config = load_job_seeker_config()
    default_input = cfg_str(config, ("runtime", "stage2", "input_json"), "highly_curated_jobs.json")
    default_output = cfg_str(config, ("runtime", "stage2", "output_json"), "stage2_filtered_local.json")
    default_rejected = cfg_str(config, ("runtime", "stage2", "rejected_output_json"), "stage2_rejected_local.json")
    default_german_special_char_threshold = cfg_int(
        config,
        ("runtime", "stage2", "german_special_char_threshold"),
        DEFAULT_GERMAN_SPECIAL_CHAR_THRESHOLD,
    )
    default_french_special_char_threshold = cfg_int(
        config,
        ("runtime", "stage2", "french_special_char_threshold"),
        DEFAULT_FRENCH_SPECIAL_CHAR_THRESHOLD,
    )
    default_spanish_special_char_threshold = cfg_int(
        config,
        ("runtime", "stage2", "spanish_special_char_threshold"),
        DEFAULT_SPANISH_SPECIAL_CHAR_THRESHOLD,
    )
    default_stage2_max_german_level = cfg_str(
        config,
        ("runtime", "stage2", "max_german_level"),
        "B2",
    )

    parser = argparse.ArgumentParser(
        description="Stage 2 local filtering: remove likely non-English jobs via language-specific local rules."
    )
    parser.add_argument("--input", default=default_input, help="Input JSON from Stage 1.")
    parser.add_argument("--output", default=default_output, help="Local-filtered approved jobs.")
    parser.add_argument("--rejected", default=default_rejected, help="Locally rejected jobs with reasons.")
    parser.add_argument(
        "--german-special-char-threshold",
        type=int,
        default=max(0, int(default_german_special_char_threshold)),
        help="Reject only if German special-character count in title/description is above this threshold.",
    )
    parser.add_argument(
        "--french-special-char-threshold",
        type=int,
        default=max(0, int(default_french_special_char_threshold)),
        help="Reject only if French special-character count in title/description is above this threshold.",
    )
    parser.add_argument(
        "--spanish-special-char-threshold",
        type=int,
        default=max(0, int(default_spanish_special_char_threshold)),
        help="Reject only if Spanish special-character count in title/description is above this threshold.",
    )
    parser.add_argument(
        "--max-german-level",
        default=default_stage2_max_german_level,
        help="Maximum accepted German CEFR level (A1, A2, B1, B2, C1, C2). Jobs requiring higher are rejected.",
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"ERROR: Input file not found: {input_path}")
        return 1

    jobs = load_json_file(input_path)
    approved: List[Dict] = []
    rejected: List[Dict] = []

    for job in jobs:
        reasons = detect_reasons(
            job,
            max(0, int(args.german_special_char_threshold)),
            max(0, int(args.french_special_char_threshold)),
            max(0, int(args.spanish_special_char_threshold)),
            args.max_german_level,
        )
        if reasons:
            rejected.append(
                {
                    **job,
                    "local_filter_reasons": reasons,
                    "local_filter_reason": " | ".join(reasons),
                }
            )
        else:
            approved.append(job)

    save_json_file(Path(args.output), approved)
    save_json_file(Path(args.rejected), rejected)

    print(f"Stage 2 complete. Input: {len(jobs)}")
    print(f"Approved (local): {len(approved)} -> {args.output}")
    print(f"Rejected (local): {len(rejected)} -> {args.rejected}")
    print(f"German special-char threshold: {max(0, int(args.german_special_char_threshold))}")
    print(f"French special-char threshold: {max(0, int(args.french_special_char_threshold))}")
    print(f"Spanish special-char threshold: {max(0, int(args.spanish_special_char_threshold))}")
    print(f"Max German level: {normalize_cefr_level(args.max_german_level)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
