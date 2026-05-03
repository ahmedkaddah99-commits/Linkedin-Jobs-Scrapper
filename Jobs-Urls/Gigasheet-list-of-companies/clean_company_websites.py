from __future__ import annotations

import csv
from pathlib import Path


INPUT_FILE = Path("Germany Business List export 2026-05-01 15-59-29.csv")
OUTPUT_FILE = Path("Germany Business List export 2026-05-01 15-59-29.cleaned.csv")
WEBSITE_COLUMN = "website"


def main() -> None:
    input_path = Path(__file__).with_name(INPUT_FILE.name)
    output_path = Path(__file__).with_name(OUTPUT_FILE.name)

    total_rows = 0
    kept_rows = 0

    with input_path.open("r", encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)

        if reader.fieldnames is None or WEBSITE_COLUMN not in reader.fieldnames:
            raise ValueError(f"CSV is missing required column: {WEBSITE_COLUMN}")

        with output_path.open("w", encoding="utf-8", newline="") as target:
            writer = csv.DictWriter(target, fieldnames=reader.fieldnames)
            writer.writeheader()

            for row in reader:
                total_rows += 1
                website = (row.get(WEBSITE_COLUMN) or "").strip()
                if website:
                    writer.writerow(row)
                    kept_rows += 1

    removed_rows = total_rows - kept_rows
    print(f"Input: {input_path.name}")
    print(f"Output: {output_path.name}")
    print(f"Total rows: {total_rows}")
    print(f"Kept rows: {kept_rows}")
    print(f"Removed rows: {removed_rows}")


if __name__ == "__main__":
    main()
