import json
import re
from pathlib import Path


def compact_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "")).strip()


def load_json_file(path: str | Path):
    file_path = Path(path).expanduser()
    with file_path.open("r", encoding="utf-8") as file:
        return json.load(file)


def save_json_file(path: str | Path, payload) -> None:
    file_path = Path(path).expanduser()
    with file_path.open("w", encoding="utf-8") as file:
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


MAX_GENERATED_DOCUMENT_FILENAME_LENGTH = 50


def build_custom_document_filename(
    candidate_name: str,
    role: str,
    company: str,
    document_kind: str,
    extension: str,
    *,
    max_length: int = MAX_GENERATED_DOCUMENT_FILENAME_LENGTH,
) -> str:
    """Build a short, application-platform-safe name for a tailored file.

    The extension counts toward the limit. Each identifying component is kept
    in the name, trimming the longest component first when the full name is
    too long. This is intentionally used only for generated, job-specific
    documents; uploaded and supporting assets keep their original names.
    """
    suffix = str(extension or "").strip()
    if suffix and not suffix.startswith("."):
        suffix = f".{suffix}"
    suffix = re.sub(r"[^\w.]", "", suffix)
    if not suffix:
        suffix = ".bin"

    def compact_part(value: str) -> str:
        return re.sub(r"[^\w-]", "", str(value or "").strip())

    parts = [
        compact_part(candidate_name),
        compact_part(role),
        compact_part(company),
        compact_part(document_kind),
    ]
    parts = [part for part in parts if part]
    if not parts:
        parts = ["Document"]

    stem_limit = max(1, int(max_length) - len(suffix))
    while len("_".join(parts)) > stem_limit:
        # Keep the document kind recognizable and shorten the largest
        # identifying component first.
        candidates = [index for index in range(len(parts) - 1) if len(parts[index]) > 3]
        if not candidates:
            break
        index = max(candidates, key=lambda item: len(parts[item]))
        parts[index] = parts[index][:-1]

    stem = "_".join(parts)[:stem_limit].rstrip("_") or "Document"
    return f"{stem}{suffix}"
