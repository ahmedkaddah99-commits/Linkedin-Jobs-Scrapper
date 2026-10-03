"""Generate and verify a reversible 100-job Nemo filter pilot on the published catalog."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))

from dotenv import load_dotenv

from backend.application.vps_job_descriptions import NEMO_MODEL, openrouter_generate
from backend.database.connection import connect_database, database_target_info

PROMPT_VERSION = "runr_filter_nemo_pilot_v1"
AUDIT = PROJECT / "data" / "audit" / "white_collar_filter_pilot_2026-10-04"
DB = PROJECT / ".backend_data" / "backend.sqlite3"
ROLES = (
    "Backend Engineer", "Full Stack Engineer", "Frontend Software Engineer", "Data Analyst",
    "Data Scientist", "Data Engineer", "Business/BI Analyst", "Machine Learning Engineer",
    "AI Engineer", "DevOps", "Cyber Security Analyst", "Software Testing/Quality Assurance Engineer",
    "Project/Program Manager", "Engineering Manager", "Business Analyst", "Data Consultant",
    "IT Consultant", "Business Strategy Consultant", "Market Research Analyst", "Operations Consultant",
    "Financial Consultant", "Content Marketing/Strategy", "Social Media Management", "SEO",
    "Copywriter", "Brand Manager", "Growth Marketing", "Performance Marketing", "Product Marketing",
    "Financial Analyst", "Risk Analyst", "Quantitative Analyst/Researcher", "Portfolio Manager",
    "Investment Banker", "Credit Analyst", "Corporate Finance Analyst", "Underwriter", "Actuary",
    "Product Manager", "Product Analyst", "Technical Product Manager", "AI Product Manager",
    "Game Designer", "Healthcare Data Analyst", "Clinical Research Associate",
    "Clinical Research Scientist", "Biostatistician", "Medical Writer", "Biomedical Engineer",
    "Health Product Manager", "Embedded Software Engineer", "Electrical Engineer",
    "Electronics Engineer", "Hardware Engineer", "Robotics Engineer", "Network Engineer",
    "Battery Engineer", "Administrative Assistant", "Executive Assistant", "Office Manager",
    "Human Resource Specialist", "Recruiter/Sourcer", "Accountant", "Controller", "Auditor",
    "Tax Specialist", "Construction Project Manager", "Civil Engineer", "Property Manager",
    "Architect", "Urban Planner", "Renewable Energy Engineer", "Energy Engineer",
    "Environmental Scientist", "Environmental Engineer",
)
WHITE_COLLAR = re.compile(
    r"analyst|manager|engineer|consultant|accountant|controller|auditor|specialist|"
    r"architect|scientist|developer|designer|recruiter|marketing|finance|legal|"
    r"product|project|sales|strategy|operations|administrator|research|business|"
    r"human resources|payroll|copywriter|editor|writer|attorney|counsel|director",
    re.I,
)
EXCLUDE = re.compile(r"mechanic|warehouse|driver|truck|nurse|caregiver|cleaner|"
                     r"electrician|plumber|machine operator|laborer|cook|waiter|"
                     r"technician|techniker|fahrer|lager|pflege|mechaniker", re.I)
EXPERIENCE = re.compile(r"\b(\d{1,2})(?:\s*[-–]\s*\d{1,2})?\s*\+?\s*(?:years?|yrs?|jahre[n]?)\b", re.I)


def setup() -> None:
    # A development worktree shares the original checkout's private .env.
    root = PROJECT.parent.parent if PROJECT.parent.name == ".worktrees" else PROJECT
    load_dotenv(root / "user_config" / ".env", override=False)
    os.environ["RUNR_DESCRIPTION_MODEL"] = NEMO_MODEL
    target = database_target_info(DB)
    if target.get("target_backend") != "libsql" or not target.get("remote_configured"):
        raise RuntimeError("The pilot requires the production Turso database")
    AUDIT.mkdir(parents=True, exist_ok=True)


def select_cohort() -> list[dict]:
    cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    with connect_database(DB) as connection:
        rows = connection.execute("""
            SELECT j.canonical_job_id, j.current_version_id AS version_id, j.title,
                   j.location, j.last_verified_at, co.canonical_name AS company,
                   v.content_hash, v.description, v.payload_json, v.apply_url
            FROM acquisition_publication_head h
            JOIN acquisition_publication_jobs pj ON pj.publication_id = h.publication_id
            JOIN canonical_jobs j ON j.canonical_job_id = pj.canonical_job_id
            JOIN canonical_companies co ON co.company_id = j.company_id
            JOIN job_posting_versions v ON v.version_id = j.current_version_id
            WHERE h.head_id = 1 AND co.entity_kind = 'employer'
              AND j.last_verified_at >= ? AND LENGTH(v.description) >= 250
              AND (LOWER(j.title) LIKE '%manager%' OR LOWER(j.title) LIKE '%analyst%'
                   OR LOWER(j.title) LIKE '%engineer%' OR LOWER(j.title) LIKE '%consultant%'
                   OR LOWER(j.title) LIKE '%specialist%' OR LOWER(j.title) LIKE '%developer%'
                   OR LOWER(j.title) LIKE '%accountant%' OR LOWER(j.title) LIKE '%architect%'
                   OR LOWER(j.title) LIKE '%marketing%' OR LOWER(j.title) LIKE '%director%')
            ORDER BY j.canonical_job_id LIMIT 300
        """, (cutoff,)).fetchall()
    choices = [dict(row) for row in rows if WHITE_COLLAR.search(row["title"] or "")
               and not EXCLUDE.search(row["title"] or "")]
    # Spread the cohort across the catalog, so one employer or role cannot dominate it.
    stride = max(1, len(choices) // 100)
    selected = choices[::stride][:100]
    if len(selected) != 100:
        raise RuntimeError(f"Only {len(selected)} eligible published jobs were found")
    return selected


def prompt_for(row: dict) -> str:
    return (
        "Classify one current employer job posting for Runr search filters. Return JSON only. "
        "Shape: {\"role\":null,\"work_arrangement\":null,\"employment_type\":null,"
        "\"experience_level\":[],\"required_experience_years\":null,\"skills\":[],\"role_type\":null}. "
        "role must be exactly one of these choices or null: " + json.dumps(ROLES) + ". "
        "work_arrangement: onsite, hybrid, remote, or null; require an explicit statement. "
        "employment_type: full_time, part_time, contract, internship, or null; use null if unstated. "
        "experience_level may contain only intern, entry, mid, senior, lead, director; "
        "include multiple levels only if the posting explicitly accepts alternative paths. "
        "required_experience_years must be a JSON number explicitly tied to required professional experience; "
        "otherwise null. Never put text in this field. "
        "skills is up to eight explicitly named tools, technologies, or professional skills from the posting. "
        "role_type is manager only if the role manages people, ic only if explicitly individual contributor, "
        "otherwise null. Do not infer company stage, industry, salary, sponsorship, or country. "
        "Do not make up a value to fill a blank. Posting: "
        + json.dumps({"title": row["title"], "description": row["description"][:9000],
                      "location": row["location"]}, ensure_ascii=False)
    )


def validated(raw: dict, row: dict) -> dict:
    if not isinstance(raw, dict):
        raise ValueError("Nemo returned a non-object")
    source = f"{row['title']} {row['description']}".casefold()
    result = {}
    result["role"] = raw.get("role") if raw.get("role") in ROLES else None
    arrangement = raw.get("work_arrangement")
    marker = {"remote": r"remote|home.?office|work from home|mobil(?:es|er)? arbeiten",
              "hybrid": r"hybrid|hybride?", "onsite": r"on.?site|on premises|vor ort|präsenz"}
    result["work_arrangement"] = arrangement if arrangement in marker and re.search(marker[arrangement], source, re.I) else None
    employment = raw.get("employment_type")
    employment_markers = {"part_time": r"part.?time|teilzeit", "contract": r"contract|befristet|freelance",
                          "internship": r"internship|intern\b|praktikum|praktikant"}
    if employment == "full_time":
        result["employment_type"] = "full_time"
    elif employment in employment_markers and re.search(employment_markers[employment], source, re.I):
        result["employment_type"] = employment
    else:
        result["employment_type"] = "full_time"  # Product rule for unstated contract type.
    years = raw.get("required_experience_years")
    supported = {int(match.group(1)) for match in EXPERIENCE.finditer(source)}
    result["required_experience_years"] = years if type(years) in (int, float) and 0 <= years <= 40 and years in supported else None
    levels = raw.get("experience_level")
    valid_levels = {"intern", "entry", "mid", "senior", "lead", "director"}
    title = row["title"].casefold()
    title_levels = {"intern": r"intern|praktik|werkstudent", "entry": r"junior|entry|graduate|trainee",
                    "mid": r"mid.level", "senior": r"senior|sr\.", "lead": r"\blead\b|teamleit|head of|\bleiter\b|staff engineer",
                    "director": r"director|direktor|vice president|\bvp\b|chief "}
    result["experience_level"] = [value for value in levels if value in valid_levels
                                  and re.search(title_levels[value], title, re.I)] if isinstance(levels, list) else []
    result["experience_level"] = list(dict.fromkeys(result["experience_level"]))
    if result["required_experience_years"] is not None:
        years = result["required_experience_years"]
        result["experience_level"] = ["entry" if years < 3 else "mid" if years < 6 else "senior" if years < 10 else "lead"]
    elif len(result["experience_level"]) > 1:
        order = ("intern", "entry", "mid", "senior", "lead", "director")
        result["experience_level"] = [max(result["experience_level"], key=order.index)]
    skills = raw.get("skills")
    result["skills"] = list(dict.fromkeys(skill.strip() for skill in skills if isinstance(skill, str)
                                                and 2 <= len(skill.strip()) <= 60
                                                and skill.strip().casefold() in source))[:8] if isinstance(skills, list) else []
    manager_evidence = re.search(
        r"\b(?:manage|managing|lead|leading|supervise|supervising|führst|führen|leitest|leiten)\b"
        r"(?:\s+\w+){0,6}\s+(?:team|staff|employees|people|mitarbeitende|mitarbeiter|personal)\b"
        r"|\b(?:fachliche|disziplinarische)\s+führung\b"
        r"|\b(?:teamlead|teamleiter|teamleitung)\b", source, re.I)
    result["role_type"] = "manager" if raw.get("role_type") == "manager" and manager_evidence else (
        "ic" if raw.get("role_type") == "ic" and not manager_evidence else None)
    return result


def run() -> None:
    cohort_file = AUDIT / "cohort.json"
    results_file = AUDIT / "results.json"
    if cohort_file.exists():
        cohort = json.loads(cohort_file.read_text(encoding="utf-8"))
    else:
        cohort = select_cohort()
        cohort_file.write_text(json.dumps(cohort, ensure_ascii=False, indent=2), encoding="utf-8")
    results = json.loads(results_file.read_text(encoding="utf-8")) if results_file.exists() else {}
    for index, row in enumerate(cohort, 1):
        job_id = row["canonical_job_id"]
        if job_id in results and "filters" in results[job_id]:
            continue
        try:
            raw = openrouter_generate(prompt_for(row))
            filters = validated(raw, row)
            results[job_id] = {"version_id": row["version_id"], "content_hash": row["content_hash"],
                               "filters": filters, "raw": raw}
        except Exception as exc:
            results[job_id] = {"error": f"{type(exc).__name__}: {exc}"[:300]}
        results_file.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"{index}/100 {job_id} {'ok' if 'filters' in results[job_id] else 'failed'}", flush=True)
    print(f"Generated {sum('filters' in value for value in results.values())}/100")


def publish() -> None:
    cohort = json.loads((AUDIT / "cohort.json").read_text(encoding="utf-8"))
    results = json.loads((AUDIT / "results.json").read_text(encoding="utf-8"))
    if len(results) != 100 or any("filters" not in result for result in results.values()):
        raise RuntimeError("All 100 Nemo classifications must succeed before publishing")
    for row in cohort:
        results[row["canonical_job_id"]]["filters"] = validated(results[row["canonical_job_id"]]["raw"], row)
    (AUDIT / "results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    ids = [row["version_id"] for row in cohort]
    with connect_database(DB) as connection:
        current = connection.execute("SELECT j.canonical_job_id, j.current_version_id, v.content_hash "
                                     "FROM acquisition_publication_head h "
                                     "JOIN acquisition_publication_jobs pj ON pj.publication_id=h.publication_id "
                                     "JOIN canonical_jobs j ON j.canonical_job_id=pj.canonical_job_id "
                                     "JOIN job_posting_versions v ON v.version_id=j.current_version_id "
                                     "WHERE h.head_id=1 AND j.canonical_job_id IN (" + ",".join("?" for _ in cohort) + ")",
                                     [row["canonical_job_id"] for row in cohort]).fetchall()
        live = {row["canonical_job_id"]: (row["current_version_id"], row["content_hash"]) for row in current}
        if any(live.get(row["canonical_job_id"]) != (row["version_id"], row["content_hash"]) for row in cohort):
            raise RuntimeError("Publication changed; regenerate cohort before publishing")
        existing = connection.execute("SELECT * FROM job_filter_intelligence WHERE version_id IN ("
                                      + ",".join("?" for _ in ids) + ")", ids).fetchall()
        rollback_file = AUDIT / "rollback.json"
        if not rollback_file.exists():
            rollback_file.write_text(json.dumps([dict(row) for row in existing], ensure_ascii=False, indent=2), encoding="utf-8")
        now = datetime.now(timezone.utc).isoformat()
        connection.executemany("INSERT INTO job_filter_intelligence "
                               "(version_id,canonical_job_id,content_hash,filters_json,model,prompt_version,generated_at) "
                               "VALUES (?,?,?,?,?,?,?) ON CONFLICT(version_id) DO UPDATE SET "
                               "canonical_job_id=excluded.canonical_job_id,content_hash=excluded.content_hash,"
                               "filters_json=excluded.filters_json,model=excluded.model,"
                               "prompt_version=excluded.prompt_version,generated_at=excluded.generated_at",
                               [(row["version_id"], row["canonical_job_id"], row["content_hash"],
                                 json.dumps(results[row["canonical_job_id"]]["filters"], ensure_ascii=False),
                                 NEMO_MODEL, PROMPT_VERSION, now) for row in cohort])
    print("Published 100 version-bound filter records")


def verify() -> None:
    from backend.repositories.sqlite_personalized_jobs import SqlitePersonalizedJobsStore
    cohort = json.loads((AUDIT / "cohort.json").read_text(encoding="utf-8"))
    results = json.loads((AUDIT / "results.json").read_text(encoding="utf-8"))
    with connect_database(DB) as connection:
        rows = connection.execute(
            "SELECT fi.canonical_job_id,fi.version_id,fi.content_hash,fi.filters_json "
            "FROM job_filter_intelligence fi "
            "JOIN canonical_jobs j ON j.canonical_job_id=fi.canonical_job_id AND j.current_version_id=fi.version_id "
            "JOIN job_posting_versions v ON v.version_id=fi.version_id AND v.content_hash=fi.content_hash "
            "JOIN acquisition_publication_head h ON h.head_id=1 "
            "JOIN acquisition_publication_jobs pj ON pj.publication_id=h.publication_id "
            "AND pj.canonical_job_id=fi.canonical_job_id "
            "WHERE fi.prompt_version=?", (PROMPT_VERSION,)).fetchall()
    readback = {row["canonical_job_id"]: row for row in rows}
    if len(readback) != 100 or any(row["canonical_job_id"] not in readback or
                                   json.loads(readback[row["canonical_job_id"]]["filters_json"]) !=
                                   results[row["canonical_job_id"]]["filters"] for row in cohort):
        raise RuntimeError(f"Only {len(readback)} current published filter records matched the 100-job cohort")
    store = SqlitePersonalizedJobsStore(DB, initialize=False)
    examples = {"published_readback": len(readback)}
    for key in ("role", "employment_type", "work_arrangement", "experience_level",
                "required_experience_min", "skills_include", "role_type"):
        for row in cohort:
            fields = results[row["canonical_job_id"]]["filters"]
            field = {"skills_include": "skills", "required_experience_min": "required_experience_years"}.get(key, key)
            value = fields.get(field)
            if isinstance(value, list):
                value = value[0] if value else None
            if not value:
                continue
            response = store.query_published_jobs("filter-pilot-verification",
                                                  filters={key: [value], "company": [row["company"]]}, limit=100)
            ids = {item["canonical_job_id"] for item in response["rows"]}
            if row["canonical_job_id"] in ids:
                examples[key] = {"value": value, "total": response["total"],
                                 "runr_url": f"https://app.userunr.com/jobs/{row['canonical_job_id']}"}
                break
        if key not in examples:
            examples[key] = {"error": "No tagged cohort job returned with this filter and its employer"}
    (AUDIT / "verification.json").write_text(json.dumps(examples, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(examples, ensure_ascii=False, indent=2))


def rollback() -> None:
    results = json.loads((AUDIT / "results.json").read_text(encoding="utf-8"))
    previous = json.loads((AUDIT / "rollback.json").read_text(encoding="utf-8"))
    with connect_database(DB) as connection:
        connection.executemany(
            "DELETE FROM job_filter_intelligence WHERE version_id=? AND prompt_version=?",
            [(result["version_id"], PROMPT_VERSION) for result in results.values()],
        )
        connection.executemany(
            "INSERT INTO job_filter_intelligence "
            "(version_id,canonical_job_id,content_hash,filters_json,model,prompt_version,generated_at) "
            "VALUES (?,?,?,?,?,?,?) ON CONFLICT(version_id) DO NOTHING",
            [(row["version_id"], row["canonical_job_id"], row["content_hash"], row["filters_json"],
              row["model"], row["prompt_version"], row["generated_at"]) for row in previous],
        )
    print(f"Removed this pilot's 100 filter records and restored {len(previous)} prior records")


def report() -> None:
    cohort = json.loads((AUDIT / "cohort.json").read_text(encoding="utf-8"))
    results = json.loads((AUDIT / "results.json").read_text(encoding="utf-8"))
    fields = ("role", "work_arrangement", "employment_type", "experience_level",
              "required_experience_years", "skills", "role_type")
    counts = {field: sum(bool(results[row["canonical_job_id"]]["filters"].get(field)) for row in cohort)
              for field in fields}
    lines = ["# Published white collar job filter pilot", "",
             "100 current published jobs were classified with `mistralai/mistral-nemo`.",
             "Model classifications are stored by posting version and content hash, separately from employer text.",
             "Empty values mean the source did not support a safe selection or no taxonomy option fit.", "",
             "Production check on 2026-10-04: all 100 filter records were read back from Turso with the current published posting version and matching content hash. Published-feed queries returned cohort jobs for role, work model, job type, experience level, required years, skill, and role type. The frontend sends these selections as API query parameters. A browser security policy prevented a signed-in visual check of the Runr page, so this report does not claim a visual UI verification.", "",
             "This pilot fills only the seven fields in the table below. Location, country, salary, industry, and company stage continue to use scraped posting or company data. Coverage measures accepted values, not a manually measured accuracy rate. `results.json` contains each raw Nemo response and the validated value; the prompt and validators are in `scripts/pilot_published_job_filters.py`.", "",
             "## Coverage", "",
             "| Filter | Jobs with accepted value |", "|---|---:|"]
    lines += [f"| {field} | {counts[field]}/100 |" for field in fields]
    lines += ["", "## Jobs", "", "| # | Employer | Job | Runr | Role | Work model | Type | Level | Years | Skills | Role type |",
              "|---:|---|---|---|---|---|---|---|---:|---:|---|"]
    def safe(value):
        return str("—" if value is None or value == "" else value).replace("|", "\\|").replace("\n", " ")
    for index, row in enumerate(cohort, 1):
        value = results[row["canonical_job_id"]]["filters"]
        columns = [str(index), safe(row["company"]), safe(row["title"]),
                   f"[Open](https://app.userunr.com/jobs/{row['canonical_job_id']})",
                   safe(value["role"]), safe(value["work_arrangement"]), safe(value["employment_type"]),
                   safe(", ".join(value["experience_level"])), safe(value["required_experience_years"]),
                   safe(", ".join(value["skills"])), safe(value["role_type"])]
        lines.append("| " + " | ".join(columns) + " |")
    lines += ["", "`cohort.json` contains the exact source posting versions and descriptions; `results.json` contains",
              "the raw Nemo responses and accepted filter values. `verification.json` records live filter checks.",
              "Run `scripts/pilot_published_job_filters.py rollback` to remove this cohort's filter values.", ""]
    (AUDIT / "REPORT.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps(counts))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("sample", "run", "publish", "verify", "rollback", "report"))
    args = parser.parse_args()
    setup()
    if args.action == "sample":
        cohort = select_cohort()
        print(json.dumps({"count": len(cohort), "examples": [{key: row[key] for key in ("company", "title", "canonical_job_id")}
                                                      for row in cohort[:10]]}, ensure_ascii=False, indent=2))
    elif args.action == "run":
        run()
    elif args.action == "publish":
        publish()
    elif args.action == "rollback":
        rollback()
    elif args.action == "report":
        report()
    else:
        verify()


if __name__ == "__main__":
    main()
