import json
import re
from pathlib import Path


def compact_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "")).strip()


def load_json_file(path: Path):
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def save_json_file(path: Path, payload) -> None:
    with path.open("w", encoding="utf-8") as file:
        json.dump(payload, file, indent=4, ensure_ascii=False)


def strip_json_fences(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.removeprefix("```json").removeprefix("```").strip()
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3].strip()
    return cleaned


def sanitize_filename(value: str, max_length: int = 90) -> str:
    cleaned = re.sub(r"[^\w\-\. ]+", "", value or "").strip()
    cleaned = re.sub(r"\s+", "_", cleaned)
    if not cleaned:
        cleaned = "item"
    return cleaned[:max_length]
