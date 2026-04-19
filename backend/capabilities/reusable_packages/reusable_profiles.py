from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List, Mapping

from .support import (
    cfg_list,
    cfg_str,
    load_baseline_profile_text,
    load_reusable_packages_config,
    load_json_file,
    resolve_path,
    save_json_file,
)


ROLE_SUMMARY_BY_CATEGORY = {
    "moving_helper_loader": "Reliable and physically resilient operations helper with practical logistics background. Experienced in loading, unloading, and coordinating movement of equipment while maintaining safety and punctual execution.",
    "waiter_service_staff": "Customer-focused service worker with hands-on operations and field-service experience. Strong under pressure, fast in busy environments, and committed to high service quality.",
    "cook_kitchen_staff": "Disciplined kitchen support profile with strong routine execution, hygiene awareness, and ability to keep fast-paced preparation and cleanup tasks on schedule.",
    "warehouse_logistics": "Operations-focused logistics worker with practical fleet and inventory coordination experience. Strong in sorting, handling, and day-to-day warehouse workflows with high reliability.",
    "delivery_driver": "Field operations profile with route coordination and transport workflow experience. Strong time management, reliability, and careful handling of goods in daily delivery operations.",
    "cleaning_facility_support": "Dependable support worker with strong execution discipline, attention to detail, and consistency in maintaining clean, safe, and operational work environments.",
    "production_packaging": "Hands-on production helper profile with strong stamina and focus on throughput, quality checks, and packaging tasks in repetitive and fast-paced environments.",
    "retail_store_support": "Store operations support profile with practical customer-facing and inventory support experience. Reliable in stock handling, floor support, and daily operational routines.",
    "other_operational": "Reliable operations worker with practical logistics and service background, high work ethic, and readiness for physical and shift-based operational tasks.",
}

ROLE_SKILLS_BY_CATEGORY = {
    "moving_helper_loader": ["Loading and unloading support", "Packing and material handling", "Team lifting and safety awareness", "Fast execution in physical tasks"],
    "waiter_service_staff": ["Customer service in high-traffic settings", "Order and table support", "Team coordination during peak hours", "Reliable shift execution"],
    "cook_kitchen_staff": ["Kitchen prep and station support", "Dishwashing and hygiene routines", "Food handling discipline", "Fast support in busy shifts"],
    "warehouse_logistics": ["Warehouse and inventory routines", "Sorting, picking, and packing", "Logistics workflow coordination", "Operational reliability"],
    "delivery_driver": ["Route and dispatch coordination", "Timely delivery workflow support", "Careful goods handling", "Daily service reliability"],
    "cleaning_facility_support": ["Cleaning process consistency", "Facility hygiene support", "Attention to detail", "Shift reliability"],
    "production_packaging": ["Production line support", "Packaging and labeling routines", "Repetitive-task endurance", "Quality and throughput awareness"],
    "retail_store_support": ["Stockroom and shelf support", "Basic cashier/store operations support", "Customer-facing communication", "Daily opening/closing task support"],
    "other_operational": ["Physical work readiness", "Operational discipline", "Team collaboration", "Punctual and reliable execution"],
}


def sanitize_filename(value: str, max_length: int = 80) -> str:
    cleaned = "".join(char if char.isalnum() or char in ("-", "_") else "_" for char in (value or ""))
    while "__" in cleaned:
        cleaned = cleaned.replace("__", "_")
    cleaned = cleaned.strip("_")
    return (cleaned or "item")[:max_length]


def build_role_cv_text(
    candidate_name: str,
    candidate_email: str,
    candidate_location: str,
    availability: str,
    languages: List[str],
    baseline_cv_text: str,
    category: Dict,
) -> str:
    category_id = str(category.get("id") or "other_operational")
    category_name = str(category.get("name") or "Other Operational")
    role_summary = ROLE_SUMMARY_BY_CATEGORY.get(category_id, ROLE_SUMMARY_BY_CATEGORY["other_operational"])
    role_skills = ROLE_SKILLS_BY_CATEGORY.get(category_id, ROLE_SKILLS_BY_CATEGORY["other_operational"])

    lines = [
        candidate_name,
        f"Email: {candidate_email}",
        f"Location: {candidate_location}",
        f"Availability: {availability}",
    ]
    if languages:
        lines.append(f"Languages: {', '.join(languages)}")
    lines.extend(["", f"TARGET ROLE CATEGORY: {category_name}", "", "ROLE SUMMARY", role_summary, "", "KEY SKILLS"])
    lines.extend([f"- {item}" for item in role_skills])
    lines.extend(["", "BASELINE EXPERIENCE (SOURCE CV)", baseline_cv_text.strip()])
    return "\n".join(lines).strip()


def write_docx(path: Path, text: str) -> bool:
    try:
        from docx import Document
    except Exception:
        return False
    document = Document()
    for raw_line in (text or "").splitlines():
        line = raw_line.rstrip()
        if not line:
            document.add_paragraph("")
            continue
        document.add_paragraph(line)
    path.parent.mkdir(parents=True, exist_ok=True)
    document.save(path)
    return True


def build_stage4_args(config: dict | None = None, overrides: Mapping[str, Any] | None = None) -> SimpleNamespace:
    config = config or load_reusable_packages_config()
    payload = {
        "input": cfg_str(config, ("runtime", "stage4", "input_json"), "outputs/stage3_classified_jobs.json"),
        "role_cv_output_dir": cfg_str(config, ("runtime", "stage4", "role_cv_output_dir"), "outputs/role_cvs"),
        "role_cv_index_json": cfg_str(config, ("runtime", "stage4", "role_cv_index_json"), "outputs/stage4_role_cvs.json"),
        "categories": cfg_list(config, ("classification", "categories"), []),
        "candidate_name": cfg_str(config, ("candidate", "name"), "Ahmed Kaddah"),
        "candidate_email": cfg_str(config, ("candidate", "email"), ""),
        "candidate_location": cfg_str(config, ("candidate", "location"), ""),
        "availability": cfg_str(config, ("candidate", "availability"), ""),
        "languages": [str(item) for item in cfg_list(config, ("candidate", "languages"), []) if str(item).strip()],
    }
    if overrides:
        payload.update({key: value for key, value in overrides.items() if value is not None})
    return SimpleNamespace(**payload)


def run_stage4_pipeline(args, *, config: dict | None = None, jobs: List[Dict] | None = None) -> dict[str, Any]:
    _ = config
    input_path = resolve_path(args.input)
    if jobs is None:
        if not input_path.exists():
            raise FileNotFoundError(f"input file not found: {input_path}")
        jobs = load_json_file(input_path)
        if not isinstance(jobs, list):
            raise ValueError("input JSON must be a list of jobs.")

    categories = [item for item in (getattr(args, "categories", None) or []) if isinstance(item, dict) and item.get("id")]
    if not categories:
        raise ValueError("no categories configured.")

    jobs_per_category: Dict[str, int] = {}
    for job in jobs:
        category_id = str(job.get("role_category_id") or "other_operational")
        jobs_per_category[category_id] = jobs_per_category.get(category_id, 0) + 1

    role_cv_output_dir = resolve_path(args.role_cv_output_dir)
    baseline_cv_text = load_baseline_profile_text()
    cv_index_records: List[Dict] = []

    for category in categories:
        category_id = str(category.get("id") or "").strip()
        category_name = str(category.get("name") or "").strip() or category_id
        if not category_id:
            continue
        cv_text = build_role_cv_text(
            candidate_name=args.candidate_name,
            candidate_email=args.candidate_email,
            candidate_location=args.candidate_location,
            availability=args.availability,
            languages=list(args.languages),
            baseline_cv_text=baseline_cv_text,
            category=category,
        )
        safe_name = sanitize_filename(f"{category_id}_{category_name}")
        txt_path = role_cv_output_dir / f"{safe_name}.txt"
        docx_path = role_cv_output_dir / f"{safe_name}.docx"
        txt_path.parent.mkdir(parents=True, exist_ok=True)
        txt_path.write_text(cv_text, encoding="utf-8")
        docx_created = write_docx(docx_path, cv_text)
        cv_index_records.append(
            {
                "category_id": category_id,
                "category_name": category_name,
                "jobs_assigned_count": int(jobs_per_category.get(category_id, 0)),
                "cv_txt_path": str(txt_path),
                "cv_docx_path": str(docx_path) if docx_created else "",
                "docx_created": bool(docx_created),
            }
        )

    index_payload = {"role_cv_count": len(cv_index_records), "role_cvs": cv_index_records}
    index_path = resolve_path(args.role_cv_index_json)
    save_json_file(index_path, index_payload)
    print("Stage 4 complete.")
    print(f"Generated role CVs: {len(cv_index_records)}")
    print(f"Role CV directory: {role_cv_output_dir}")
    print(f"Role CV index: {index_path}")
    return {
        "role_cv_index": index_payload,
        "role_cv_records": cv_index_records,
        "role_cv_output_dir": str(role_cv_output_dir),
        "role_cv_index_path": str(index_path),
    }
