"""Repair an immutable workbook job CSV using its deterministic source evidence."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import csv
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import re
import sys
import threading
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from bs4 import BeautifulSoup
from scripts.workbook_employer_dry_run import Transport, atomic_json, blue_collar_evidence, plain, text, now


def present(value):
    value = str(value or "").strip()
    if value.casefold() in ("", "n/a", "none", "null", "unknown", "-", "[]", "{}"):
        return False
    if value.startswith(("[", "{")):
        try:
            obj = json.loads(value)
            if isinstance(obj, (dict, list)):
                return any(present(v) for v in (obj.values() if isinstance(obj, dict) else obj))
        except ValueError:
            pass
    return True


def decode_nuxt(values, root=0):
    """Resolve devalue indices as data, never evaluate JavaScript."""
    memo = {}

    def resolve(index):
        if not isinstance(index, int):
            return index
        if index < 0:
            return None
        if index in memo:
            return memo[index]
        value = values[index]
        if isinstance(value, dict):
            result = {}
            memo[index] = result
            result.update({k: resolve(v) for k, v in value.items()})
            return result
        if isinstance(value, list):
            if value and isinstance(value[0], str) and value[0] in ("Reactive", "ShallowReactive", "Ref", "ShallowRef"):
                return resolve(value[1])
            result = []
            memo[index] = result
            result.extend(resolve(v) for v in value)
            return result
        return value

    return resolve(root)


def name(value):
    if isinstance(value, dict):
        return text(value.get("name") or value.get("label") or value.get("descriptor"))
    return text(value)


def raw_metadata(raw):
    """Only copy explicitly named source fields; do not infer from prose."""
    patch = {}
    org = raw.get("hiringOrganization") or raw.get("company") or raw.get("companyName")
    if org:
        patch["legal_employer"] = name(org)
    patch["employment_type"] = name(raw.get("employmentType") or raw.get("typeOfEmployment") or raw.get("timeType"))
    patch["department"] = name(raw.get("department"))
    patch["function"] = name(raw.get("function"))
    patch["seniority"] = name(raw.get("experienceLevel"))
    patch["date_posted"] = text(raw.get("datePosted") or raw.get("releasedDate"))
    patch["working_hours"] = text(raw.get("workHours"))
    patch["responsibilities"] = plain(raw.get("responsibilities"))
    patch["qualifications"] = plain(raw.get("qualifications"))
    patch["requirements"] = plain(raw.get("requirements"))
    loc = raw.get("location")
    if isinstance(loc, dict):
        for field, key in (
            ("country", "country"),
            ("region", "region"),
            ("city", "city"),
            ("postal_code", "postalCode"),
        ):
            patch[field] = name(loc.get(key))
        patch["location"] = text(loc.get("fullLocation")) or ", ".join(
            patch.get(k, "") for k in ("city", "region", "country") if patch.get(k)
        )
    source_loc = raw.get("jobLocation")
    if isinstance(source_loc, dict):
        address = source_loc.get("address", {})
        if isinstance(address, dict):
            for field, key in (
                ("country", "addressCountry"),
                ("region", "addressRegion"),
                ("city", "addressLocality"),
                ("postal_code", "postalCode"),
            ):
                patch[field] = name(address.get(key))
            patch["location"] = ", ".join(
                name(address.get(k))
                for k in ("streetAddress", "addressLocality", "addressRegion", "postalCode", "addressCountry")
                if present(name(address.get(k)))
            )
    return {k: v for k, v in patch.items() if present(v)}


def html_metadata(soup):
    def prop(key):
        e = soup.select_one('[itemprop="' + key + '"]')
        if not e:
            return ""
        if key == "hiringOrganization":
            e = e.select_one('[itemprop="name"]') or e
        return e.get("content") or e.get_text(" ", strip=True)

    patch = {}
    for field, key in (
        ("legal_employer", "hiringOrganization"),
        ("employment_type", "employmentType"),
        ("city", "addressLocality"),
        ("region", "addressRegion"),
        ("country", "addressCountry"),
        ("postal_code", "postalCode"),
        ("working_hours", "workHours"),
    ):
        patch[field] = prop(key)
    patch["location"] = ", ".join(
        prop(k)
        for k in ("streetAddress", "addressLocality", "addressRegion", "postalCode", "addressCountry")
        if present(prop(k))
    )
    candidates = soup.select('[itemprop="description"], .jobdescription, .job-description, .o-jobad__content')
    texts = [e.get_text(" ", strip=True) for e in candidates]
    if texts:
        patch["description"] = max(texts, key=len)
    label_map = {
        "unternehmen": "legal_employer",
        "company": "legal_employer",
        "organisation": "department",
        "geschäftsbereich": "function",
        "vollzeit / teilzeit": "employment_type",
        "erfahrungsniveau": "seniority",
        "remote oder büro": "workplace",
        "job id": "job_id",
    }
    rich = []
    for field in soup.select(".article__content__view__field"):
        label = field.select_one(".article__content__view__field__label")
        value = field.select_one(".article__content__view__field__value")
        if not value:
            continue
        value_text = value.get_text(" ", strip=True)
        if label:
            target = label_map.get(label.get_text(" ", strip=True).casefold())
            if target:
                patch[target] = value_text
        elif len(value_text) > 600:
            rich.append(value_text)
    if rich:
        patch["description"] = max(rich, key=len)
    locations = [
        e.get_text(" ", strip=True) for e in soup.select(".posting-location .article__content__view__field__value")
    ]
    additional = [
        ", ".join(e.get_text(" ", strip=True) for e in group.select(".MultipleDataSetFieldValue"))
        for group in soup.select(".additional-posting-locations .MultipleDataSetFields")
    ]
    if locations or additional:
        patch["location"] = "; ".join(dict.fromkeys(v for v in [", ".join(locations), *additional] if v))
    return {k: v for k, v in patch.items() if present(v)}


class Repair:
    def __init__(self, source, out):
        self.source, self.out = source, out
        out.mkdir(parents=True, exist_ok=True)
        self.transport = Transport(out)
        self.changes, self.errors, self.exclusions = [], [], []
        self.lock = threading.Lock()
        self.done = 0
        self.krones = self.krones_records()

    def cached(self, url):
        if not url or not url.startswith(("https://", "http://")):
            return None
        for candidate in dict.fromkeys((url, url.rstrip("/") + "/")):
            key = hashlib.sha256(("GET" + candidate + "null").encode()).hexdigest()
            file = self.source / "cache" / (key + ".json")
            if file.exists():
                try:
                    data = json.loads(file.read_text(encoding="utf-8"))
                    if data.get("status") == 200:
                        return data
                except ValueError:
                    pass
        return None

    def krones_records(self):
        u = "https://www.krones.com/de/karriere/jobs/jobs-deutschland/"
        cached = self.cached(u)
        if not cached:
            return {}
        soup = BeautifulSoup(cached["body"], "lxml")
        values = json.loads(soup.select_one("#__NUXT_DATA__").get_text())
        records = {}
        for i, value in enumerate(values):
            if isinstance(value, dict) and all(k in value for k in ("id", "title", "url", "locations")):
                records[str(value["id"])] = decode_nuxt(values, i)
        return records

    @lru_cache(maxsize=512)
    def cached_html_patch(self, url):
        cached = self.cached(url)
        if cached and cached["body"].lstrip().startswith("<"):
            return html_metadata(BeautifulSoup(cached["body"], "lxml"))
        return None

    def repair(self, pair):
        index, original = pair
        r = dict(original)
        sources = []
        rawpath = self.source / r["raw_record_file"] if r.get("raw_record_file") else None
        complete_core = (
            r["rank"] not in ("174", "377")
            and len(plain(r.get("description"))) >= 500
            and present(r.get("legal_employer"))
            and present(r.get("employment_type"))
            and any(present(r.get(k)) for k in ("location", "city", "country", "region"))
            and not r["title"].strip().isdigit()
        )
        if complete_core:
            r["original_csv_record_number"] = str(index)
            if rawpath:
                r["raw_record_file"] = str(rawpath.resolve())
            self.checkpoint()
            return r
        raw = {}
        if rawpath and rawpath.exists():
            try:
                raw = json.loads(rawpath.read_text(encoding="utf-8"))
            except ValueError:
                pass

        def apply(patch, url, force=False):
            for k, v in patch.items():
                if not present(v):
                    continue
                # A source-rich description can replace a short source summary.
                allowed = (
                    force
                    or not present(r.get(k))
                    or (
                        k == "description" and len(plain(r.get(k))) < 500 and len(plain(v)) > len(plain(r.get(k))) + 100
                    )
                )
                if allowed and text(r.get(k)) != text(v):
                    before = r.get(k, "")
                    r[k] = text(v)
                    sources.append(url)
                    with self.lock:
                        self.changes.append(
                            {
                                "csv_record_number": index,
                                "rank": r["rank"],
                                "company_name": r["company_name"],
                                "job_detail_url": r["job_detail_url"],
                                "field": k,
                                "before": before,
                                "after": r[k],
                                "source_url": url,
                            }
                        )

        try:
            apply(raw_metadata(raw), r.get("source_page") or r["job_detail_url"])
            if r["rank"] == "174":
                listing = self.krones.get(original["job_id"])
                if not listing:
                    raise ValueError("Cannot resolve original Krones reference")
                reason = blue_collar_evidence(listing["title"])
                if reason:
                    with self.lock:
                        self.exclusions.append(
                            {
                                "csv_record_number": index,
                                "rank": r["rank"],
                                "title": listing["title"],
                                "job_detail_url": listing["url"],
                                **reason,
                            }
                        )
                    return None
                data = self.transport.request(listing["url"]).json()
                opening = data.get("jobOpening") or {}
                location = (opening.get("locations") or [{}])[0]
                address = location.get("address") or {}
                apply(
                    {
                        "title": data.get("position") or listing["title"],
                        "job_id": data.get("id"),
                        "job_detail_url": data.get("jobPublicationURL") or listing["url"],
                        "description": "\n\n".join(
                            plain(data.get(k))
                            for k in ("introduction", "tasks", "profile", "weOffer", "closingText")
                            if data.get(k)
                        ),
                        "responsibilities": plain(data.get("tasks")),
                        "qualifications": plain(data.get("profile")),
                        "requirements": plain(data.get("profile")),
                        "legal_employer": name(opening.get("company")) or listing.get("company"),
                        "location": opening.get("location") or text(listing.get("locations")),
                        "city": address.get("city"),
                        "country": name(address.get("country")),
                        "postal_code": address.get("zipCode"),
                        "department": opening.get("department"),
                        "industry": text([name(v) for v in opening.get("categories", [])]),
                        "employment_type": text([name(v) for v in opening.get("workingTimes", [])]),
                        "working_hours": text([name(v) for v in opening.get("workingTimes", [])]),
                        "source_start_date": data.get("startDate"),
                        "source_end_date": data.get("endDate"),
                    },
                    listing["url"],
                    force=True,
                )
            elif r["rank"] == "377":
                ref = raw.get("ref")
                if ref and urlsplit(ref).hostname == "api.smartrecruiters.com":
                    data = self.transport.request(ref).json()
                    sections = data.get("jobAd", {}).get("sections", {})
                    patch = raw_metadata(data)
                    patch.update(
                        description="\n\n".join(plain(v.get("text")) for v in sections.values() if isinstance(v, dict)),
                        responsibilities=plain(sections.get("jobDescription", {}).get("text")),
                        qualifications=plain(sections.get("qualifications", {}).get("text")),
                    )
                    apply(patch, ref)
                    for field in data.get("customField", []):
                        if field.get("fieldLabel") == "Target Group" and str(
                            field.get("valueLabel", "")
                        ).casefold().startswith("blue collar"):
                            with self.lock:
                                self.exclusions.append(
                                    {
                                        "csv_record_number": index,
                                        "rank": r["rank"],
                                        "title": r["title"],
                                        "job_detail_url": r["job_detail_url"],
                                        "reason": "source_explicit_blue_collar_target_group",
                                    }
                                )
                            return None
            needs_html = (
                any(not present(r.get(k)) for k in ("legal_employer", "location", "employment_type"))
                or len(plain(r.get("description"))) < 500
            )
            if needs_html and r["rank"] not in ("174", "377"):
                for url in dict.fromkeys((original.get("job_detail_url"), original.get("source_page"))):
                    patch = self.cached_html_patch(url)
                    if patch is not None:
                        apply(patch, url)
                        break
            if sources:
                r["repair_source_urls"] = json.dumps(list(dict.fromkeys(sources)), ensure_ascii=False)
                r["repair_fields"] = "; ".join(k for k in original if r.get(k) != original.get(k))
                r["repaired_at"] = now()
            r["original_csv_record_number"] = str(index)
            if rawpath:
                r["raw_record_file"] = str(rawpath.resolve())
            if r["title"].strip().isdigit():
                raise ValueError("Unresolved numeric-only title")
            return r
        except Exception as exc:
            with self.lock:
                self.errors.append(
                    {
                        "csv_record_number": index,
                        "rank": original["rank"],
                        "company_name": original["company_name"],
                        "title": original["title"],
                        "job_detail_url": original["job_detail_url"],
                        "error": str(exc)[:200],
                    }
                )
            # Numeric Krones placeholders are quarantined, never labelled valid.
            return None if original["title"].strip().isdigit() else r
        finally:
            self.checkpoint()

    def checkpoint(self):
        with self.lock:
            self.done += 1
            if self.done % 250 == 0:
                status = {
                    "processed": self.done,
                    "field_repairs": len(self.changes),
                    "errors": len(self.errors),
                    "excluded": len(self.exclusions),
                }
                atomic_json(self.out / "repair_progress.json", status)
                print(json.dumps(status), flush=True)


def write_csv(path, rows, fields=None):
    fields = fields or list(dict.fromkeys(k for r in rows for k in r))
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--workers", type=int, default=6)
    args = p.parse_args()
    source_csv = args.source / "jobs.csv"
    with source_csv.open("rb") as f:
        digest = hashlib.file_digest(f, "sha256").hexdigest()
    with source_csv.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        fields = reader.fieldnames
        rows = list(reader)
    runner = Repair(args.source, args.output)
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        repaired = [r for r in pool.map(runner.repair, enumerate(rows, 2)) if r is not None]
    write_csv(
        args.output / "jobs_repaired.csv",
        repaired,
        fields + ["original_csv_record_number", "repair_fields", "repair_source_urls", "repaired_at"],
    )
    write_csv(args.output / "field_changes.csv", runner.changes)
    write_csv(args.output / "repair_errors.csv", runner.errors)
    write_csv(args.output / "excluded_or_quarantined.csv", runner.exclusions + runner.errors)
    with source_csv.open("rb") as f:
        unchanged = digest == hashlib.file_digest(f, "sha256").hexdigest()
    summary = {
        "at": now(),
        "input_jobs": len(rows),
        "output_jobs": len(repaired),
        "changed_jobs": sum(bool(r.get("repair_fields")) for r in repaired),
        "field_changes": len(runner.changes),
        "errors": len(runner.errors),
        "excluded": len(runner.exclusions),
        "original_sha256": digest,
        "original_unchanged": unchanged,
    }
    atomic_json(args.output / "repair_summary.json", summary)
    print(json.dumps(summary), flush=True)


if __name__ == "__main__":
    main()
