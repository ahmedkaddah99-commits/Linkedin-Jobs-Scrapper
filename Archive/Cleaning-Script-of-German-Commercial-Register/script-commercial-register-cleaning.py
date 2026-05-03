import argparse
import json
import re
from pathlib import Path

INPUT_FILE = "input.json"
OUTPUT_FILE = "cleaned_output.json"
PROGRESS_EVERY = 100_000

ACTIVE_STATUS = "currently registered"
REMOVED_STATUS = "removed"
STRICT_CAPTION_SUFFIX = re.compile(r"(?:^|\s)(GmbH|AG)[\s\.,]*$")
CITY_FROM_ID_PATTERN = re.compile(
    r"^de-oc-(?P<city>.+?)(?:-\d+)?-(?:hrb|hra|gnr|pr|vr)-\d+[a-z]*$",
    re.IGNORECASE,
)


def first_value(value):
    if isinstance(value, list):
        return value[0] if value else None
    return value


def has_strict_company_suffix(caption):
    if not isinstance(caption, str):
        return False

    normalized = " ".join(caption.strip().split())
    return bool(STRICT_CAPTION_SUFFIX.search(normalized))


def extract_city(company_id):
    if not isinstance(company_id, str):
        return None

    match = CITY_FROM_ID_PATTERN.match(company_id.strip())
    if not match:
        return None

    city = match.group("city").replace("-", " ").strip()
    return city or None


def should_keep(row):
    if not isinstance(row, dict):
        return False

    properties = row.get("properties", {})
    if not isinstance(properties, dict):
        return False

    status = first_value(properties.get("status"))
    legal_form = first_value(properties.get("legalForm"))

    if status == REMOVED_STATUS:
        return False

    if status != ACTIVE_STATUS:
        return False

    if legal_form not in {"Unternehmen", "Kapitalgesellschaft"}:
        return False

    if not has_strict_company_suffix(row.get("caption")):
        return False

    if extract_city(row.get("id")) is None:
        return False

    return True


def transform_row(row):
    return {
        "city": extract_city(row.get("id")),
        "Company name": row.get("caption"),
    }


def filter_rows(input_path, output_path):
    processed = 0
    kept = 0

    with input_path.open("r", encoding="utf-8") as src, output_path.open(
        "w", encoding="utf-8"
    ) as dst:
        dst.write("[\n")
        first_output = True

        for line_number, line in enumerate(src, start=1):
            line = line.strip()
            if not line:
                continue

            processed += 1

            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"Invalid JSON on line {line_number}: {exc}"
                ) from exc

            if not should_keep(row):
                continue

            if not first_output:
                dst.write(",\n")

            json.dump(transform_row(row), dst, ensure_ascii=False)
            first_output = False
            kept += 1

            if processed % PROGRESS_EVERY == 0:
                print(f"Processed {processed:,} rows, kept {kept:,} rows...")

        dst.write("\n]\n")

    return processed, kept


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Keep only active rows whose legalForm is Unternehmen or "
            "Kapitalgesellschaft, whose caption ends strictly with GmbH or AG, "
            "and output only city plus Company name."
        )
    )
    parser.add_argument(
        "--input",
        default=INPUT_FILE,
        help="Input JSONL file name or path.",
    )
    parser.add_argument(
        "--output",
        default=OUTPUT_FILE,
        help="Output JSON file name or path.",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    base_dir = Path(__file__).resolve().parent
    input_path = Path(args.input)
    output_path = Path(args.output)

    if not input_path.is_absolute():
        input_path = base_dir / input_path

    if not output_path.is_absolute():
        output_path = base_dir / output_path

    processed, kept = filter_rows(input_path, output_path)

    print(f"Done. Processed {processed:,} rows.")
    print(f"Kept {kept:,} rows.")
    print(f"Saved to {output_path}")


if __name__ == "__main__":
    main()
