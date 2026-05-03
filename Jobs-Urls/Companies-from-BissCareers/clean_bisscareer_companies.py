from __future__ import annotations

import csv
from pathlib import Path


INPUT_FILE = Path(__file__).with_name("uncleaned-companies-data-bisscareer.txt")
OUTPUT_FILE = Path(__file__).with_name("cleaned-companies-data-bisscareer.csv")

FIELDNAMES = [
    "company",
    "estimated_revenue_eur_million",
    "city",
    "sectors_active",
    "website",
]


def iter_rows(raw_text: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []

    for line_number, line in enumerate(raw_text.splitlines(), start=1):
        if line.count("\t") != 4:
            continue

        company, revenue, city, sectors_active, website = [part.strip() for part in line.split("\t")]
        rows.append(
            {
                "company": company,
                "estimated_revenue_eur_million": revenue.replace(",", ""),
                "city": city,
                "sectors_active": sectors_active,
                "website": website,
            }
        )

    return rows


def main() -> None:
    raw_text = INPUT_FILE.read_text(encoding="utf-8", errors="replace")
    rows = iter_rows(raw_text)

    with OUTPUT_FILE.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Wrote {len(rows)} rows to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
