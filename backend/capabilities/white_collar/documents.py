import argparse
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from google import genai

from backend.config.job_seeker import (
    cfg_bool,
    cfg_float,
    cfg_int,
    cfg_list,
    cfg_str,
    load_job_seeker_config,
    load_project_dotenv,
    normalize_windows_env_path,
)
from backend.profiles.cv_text import load_cv_text

from .common import load_json_file, save_json_file
from .cv_structuring import ensure_structured_cv_fields
from .generation import generate_docs_for_job
from .rendering import (
    DEFAULT_LANGUAGES,
    convert_docx_to_pdf,
    create_cv_document,
    resolve_assets_profile_png,
    resolve_optional_image_path,
    resolve_profile_image_path,
)
from .tracker_export import save_to_excel


DEFAULT_CANDIDATE_NAME = "Kaddah Ahmed"
DEFAULT_CANDIDATE_EMAIL = "ahmed.kaddah@tutamail.com"
DEFAULT_CV_FONT = "Calibri"


def main() -> int:
    load_project_dotenv()
    config = load_job_seeker_config()

    default_input_json = cfg_str(config, ("runtime", "stage4", "input_json"), "stage3_filtered_ai.json")
    default_output_json = cfg_str(config, ("outputs", "stage4_json"), "stage4_documents.json")
    default_output_xlsx = cfg_str(config, ("outputs", "stage4_xlsx"), "final_jobs_with_docs.xlsx")
    default_docs_dir = cfg_str(config, ("outputs", "docs_dir"), "generated_docs")
    default_stage4_checkpoint = cfg_str(config, ("runtime", "stage4", "checkpoint_json"), "stage4_checkpoint.json")
    default_deepseek_model = cfg_str(
        config,
        ("ai", "models", "stage4_docs_deepseek"),
        os.getenv("DEEPSEEK_STAGE4_MODEL", "deepseek-chat"),
    )
    default_gemini_fallback_model = (
        cfg_str(config, ("ai", "models", "stage4_docs_fallback_gemini"), "")
        or os.getenv("GEMINI_DOCS_MODEL", "gemini-2.5-flash")
    )
    default_candidate_name = cfg_str(config, ("candidate", "name"), "") or os.getenv(
        "CANDIDATE_NAME",
        DEFAULT_CANDIDATE_NAME,
    )
    default_candidate_email = cfg_str(config, ("candidate", "email"), "") or os.getenv(
        "CANDIDATE_EMAIL",
        DEFAULT_CANDIDATE_EMAIL,
    )
    default_profile_image = cfg_str(config, ("candidate", "profile_image_path"), "") or os.getenv(
        "CV_PROFILE_IMAGE_PATH",
        "",
    )
    default_cv_font = cfg_str(config, ("candidate", "cv_font"), DEFAULT_CV_FONT) or DEFAULT_CV_FONT
    default_languages = [str(item) for item in cfg_list(config, ("candidate", "languages"), DEFAULT_LANGUAGES)]
    default_stage4_extra_prompt = cfg_str(config, ("ai", "prompts", "stage4_extra_instructions"), "")
    default_stage4_prompt_override = cfg_str(config, ("ai", "prompts", "stage4_prompt_override"), "")
    default_stage4_sleep_seconds = cfg_float(
        config,
        ("runtime", "stage4", "sleep_seconds"),
        float(os.getenv("STAGE4_SLEEP_SECONDS", "4")),
    )
    default_stage4_retries = cfg_int(
        config,
        ("runtime", "stage4", "retries"),
        int(os.getenv("STAGE4_RETRIES", "3")),
    )
    default_stage4_retry_sleep = cfg_float(
        config,
        ("runtime", "stage4", "retry_sleep_seconds"),
        float(os.getenv("STAGE4_RETRY_SLEEP_SECONDS", "3")),
    )
    default_stage4_max_jobs = cfg_int(
        config,
        ("runtime", "stage4", "max_jobs"),
        int(os.getenv("STAGE4_MAX_JOBS", "0")),
    )
    default_stage4_excel_mode = cfg_str(
        config,
        ("runtime", "stage4", "excel_mode"),
        os.getenv("STAGE4_EXCEL_MODE", "new-sheet"),
    )
    if default_stage4_excel_mode not in ("new-sheet", "append-rows"):
        default_stage4_excel_mode = "new-sheet"
    default_stage4_sheet_name = cfg_str(
        config,
        ("runtime", "stage4", "sheet_name"),
        os.getenv("STAGE4_SHEET_NAME", ""),
    )
    default_stage4_run_date = cfg_str(
        config,
        ("runtime", "stage4", "run_date"),
        os.getenv("STAGE4_RUN_DATE", ""),
    )
    default_stage4_force_regenerate = cfg_bool(
        config,
        ("runtime", "stage4", "force_regenerate"),
        os.getenv("STAGE4_FORCE_REGENERATE", "false").lower() in ("1", "true", "yes"),
    )

    parser = argparse.ArgumentParser(
        description=(
            "Stage 4: generate a structured CV and export both .docx and .pdf per job, "
            "plus JSON/XLSX."
        )
    )
    parser.add_argument("--input", default=default_input_json, help="Input JSON from Stage 3.")
    parser.add_argument("--output-json", default=default_output_json, help="Output JSON with generated documents.")
    parser.add_argument("--output-xlsx", default=default_output_xlsx, help="Output Excel file.")
    parser.add_argument("--checkpoint", default=default_stage4_checkpoint, help="Checkpoint for resumable generation.")
    parser.add_argument("--docs-dir", default=default_docs_dir, help="Directory where .docx files are stored.")
    parser.add_argument(
        "--model",
        default=default_deepseek_model,
        help="Primary DeepSeek model for Stage 4 (e.g., deepseek-reasoner, deepseek-chat).",
    )
    parser.add_argument(
        "--fallback-model",
        default=default_gemini_fallback_model,
        help="Gemini fallback model used only if DeepSeek fails.",
    )
    parser.add_argument(
        "--candidate-name",
        default=default_candidate_name,
        help="Candidate name used in document title, filename, and signature.",
    )
    parser.add_argument(
        "--candidate-email",
        default=default_candidate_email,
        help="Candidate email shown in CV header.",
    )
    parser.add_argument(
        "--profile-image",
        default=default_profile_image,
        help="Optional path to profile image shown on the top-right of the CV header.",
    )
    parser.add_argument(
        "--cv-font",
        default=default_cv_font,
        choices=["Calibri", "Arial"],
        help="CV font family.",
    )
    parser.add_argument(
        "--languages",
        nargs="*",
        default=default_languages,
        help="Language lines printed in LANGUAGES section.",
    )
    parser.add_argument(
        "--stage4-extra-prompt",
        default=default_stage4_extra_prompt,
        help="Extra instructions appended to Stage 4 generation prompt.",
    )
    parser.add_argument(
        "--stage4-prompt-override",
        default=default_stage4_prompt_override,
        help=(
            "Optional full prompt override. Supports placeholders: {{CV_TEXT}}, {{JOB_ID}}, "
            "{{JOB_TITLE}}, {{JOB_COMPANY}}, {{JOB_CITY}}, {{JOB_DESCRIPTION}}, {{CANDIDATE_NAME}}."
        ),
    )
    parser.add_argument("--sleep-seconds", type=float, default=default_stage4_sleep_seconds)
    parser.add_argument("--retries", type=int, default=default_stage4_retries)
    parser.add_argument("--retry-sleep", type=float, default=default_stage4_retry_sleep)
    parser.add_argument(
        "--max-jobs",
        type=int,
        default=default_stage4_max_jobs,
        help="0 means all jobs. Use a positive number to cap AI document generation for quota control.",
    )
    parser.add_argument(
        "--excel-mode",
        choices=["new-sheet", "append-rows"],
        default=default_stage4_excel_mode,
        help="new-sheet: create a dated sheet each run. append-rows: append into one sheet.",
    )
    parser.add_argument(
        "--sheet-name",
        default=default_stage4_sheet_name,
        help="Sheet name. For new-sheet mode, empty means run date; for append-rows, default is jobs.",
    )
    parser.add_argument(
        "--run-date",
        default=default_stage4_run_date,
        help="Override run date (YYYY-MM-DD). Empty uses today.",
    )
    parser.add_argument(
        "--force-regenerate",
        action=argparse.BooleanOptionalAction,
        default=default_stage4_force_regenerate,
        help="Ignore existing stage4 checkpoint and regenerate docs for all selected jobs.",
    )
    args = parser.parse_args()

    try:
        run_stage4_pipeline(args, config=config)
    except Exception as exc:
        print(f"Stage 4 failed: {exc}")
        return 1
    return 0


def run_stage4_pipeline(args, *, config=None, jobs: Optional[List[Dict]] = None) -> List[Dict]:
    load_project_dotenv()
    if config is None:
        config = load_job_seeker_config()

    default_linkedin_profile_url = cfg_str(config, ("candidate", "profile_links", "linkedin", "url"), "")
    default_linkedin_profile_text = cfg_str(config, ("candidate", "profile_links", "linkedin", "text"), "LinkedIn")
    default_linkedin_profile_icon = cfg_str(config, ("candidate", "profile_links", "linkedin", "icon"), "in")
    default_linkedin_logo_path = (
        cfg_str(config, ("candidate", "profile_links", "linkedin", "logo_path"), "")
        or cfg_str(config, ("candidate", "profile_links", "linkedin", "icon_path"), "")
        or cfg_str(config, ("candidate", "profile_links", "linkedin", "image_path"), "")
    )
    default_github_profile_url = cfg_str(config, ("candidate", "profile_links", "github", "url"), "")
    default_github_profile_text = cfg_str(config, ("candidate", "profile_links", "github", "text"), "GitHub")
    default_github_profile_icon = cfg_str(config, ("candidate", "profile_links", "github", "icon"), "GH")
    default_github_logo_path = (
        cfg_str(config, ("candidate", "profile_links", "github", "logo_path"), "")
        or cfg_str(config, ("candidate", "profile_links", "github", "icon_path"), "")
        or cfg_str(config, ("candidate", "profile_links", "github", "image_path"), "")
    )

    deepseek_api_key = os.getenv("DEEPSEEK_API_KEY")
    gemini_api_key = os.getenv("GEMINI_API_KEY")
    if not deepseek_api_key and not gemini_api_key:
        raise RuntimeError("Both DEEPSEEK_API_KEY and GEMINI_API_KEY are missing in environment/user_config/.env")

    if jobs is None:
        input_path = Path(args.input)
        if not input_path.exists():
            raise FileNotFoundError(f"Input file not found: {input_path}")
        jobs = load_json_file(input_path)
        if not isinstance(jobs, list):
            raise ValueError("Input JSON must be a list of jobs.")
    else:
        jobs = list(jobs)

    if args.max_jobs > 0:
        jobs = jobs[: args.max_jobs]

    run_dt = datetime.now()
    run_date = args.run_date.strip() or run_dt.strftime("%Y-%m-%d")
    run_timestamp = run_dt.isoformat(timespec="seconds")
    docs_dir = Path(args.docs_dir)
    candidate_name = (args.candidate_name or DEFAULT_CANDIDATE_NAME).strip() or DEFAULT_CANDIDATE_NAME
    candidate_email = (args.candidate_email or DEFAULT_CANDIDATE_EMAIL).strip() or DEFAULT_CANDIDATE_EMAIL
    cv_font_name = (args.cv_font or DEFAULT_CV_FONT).strip() or DEFAULT_CV_FONT
    languages = [str(item).strip() for item in (args.languages or DEFAULT_LANGUAGES) if str(item).strip()]
    if not languages:
        languages = list(DEFAULT_LANGUAGES)
    normalized_profile_input = normalize_windows_env_path(args.profile_image)
    profile_image_path = resolve_profile_image_path(normalized_profile_input)
    if normalized_profile_input and not profile_image_path:
        print(f"WARNING: profile image must be an existing .png file, got: {normalized_profile_input}")
    if not profile_image_path:
        profile_image_path = resolve_assets_profile_png(docs_dir)
        if profile_image_path:
            print(f"INFO: using profile photo from assets PNG: {profile_image_path}")
        else:
            print("WARNING: no PNG profile image found in docs _assets folder.")

    profile_links: List[Dict[str, str]] = []
    if default_linkedin_profile_url:
        linkedin_logo_path = resolve_optional_image_path(default_linkedin_logo_path)
        profile_links.append(
            {
                "icon": default_linkedin_profile_icon,
                "text": default_linkedin_profile_text or default_linkedin_profile_icon or "LinkedIn",
                "url": default_linkedin_profile_url,
                "logo_path": linkedin_logo_path,
            }
        )
    if default_github_profile_url:
        github_logo_path = resolve_optional_image_path(default_github_logo_path)
        profile_links.append(
            {
                "icon": default_github_profile_icon,
                "text": default_github_profile_text or default_github_profile_icon or "GitHub",
                "url": default_github_profile_url,
                "logo_path": github_logo_path,
            }
        )

    cv_text = load_cv_text()
    gemini_client = genai.Client(api_key=gemini_api_key) if gemini_api_key else None

    checkpoint_path = Path(args.checkpoint)
    checkpoint = {"generated_records": []}
    if checkpoint_path.exists() and not args.force_regenerate:
        loaded_checkpoint = load_json_file(checkpoint_path)
        if isinstance(loaded_checkpoint, dict):
            checkpoint.update(loaded_checkpoint)

    generated_by_id = {}
    for record in checkpoint.get("generated_records", []):
        job_id = str(record.get("job_id"))
        if job_id:
            generated_by_id[job_id] = record

    total_jobs = len(jobs)
    checkpoint_changed = False

    for index, job in enumerate(jobs, start=1):
        job_id = str(job.get("job_id"))
        if job_id in generated_by_id and not args.force_regenerate:
            existing_record = generated_by_id[job_id]
            for passthrough_key in [
                "posted_time_text",
                "posted_age_hours",
                "posted_datetime_estimated_utc",
                "applicant_count",
                "priority_rank",
                "priority_tier",
                "priority_bucket",
                "priority_rule",
                "source_type",
                "filter_status",
                "source_url",
                "manual_approved",
            ]:
                if passthrough_key in job and existing_record.get(passthrough_key) != job.get(passthrough_key):
                    existing_record[passthrough_key] = job.get(passthrough_key)
                    checkpoint_changed = True
            if not existing_record.get("run_date"):
                existing_record["run_date"] = run_date
                checkpoint_changed = True
            if not existing_record.get("run_timestamp"):
                existing_record["run_timestamp"] = run_timestamp
                checkpoint_changed = True
            if not existing_record.get("linkedin_link"):
                existing_record["linkedin_link"] = existing_record.get("link", "")
                checkpoint_changed = True
            if not existing_record.get("apply_link"):
                existing_record["apply_link"] = existing_record.get("linkedin_link", "")
                checkpoint_changed = True

            ensure_structured_cv_fields(existing_record, candidate_name=candidate_name, cv_text=cv_text)

            missing_cv_doc = not existing_record.get("cv_docx")
            has_text_content = bool(existing_record.get("cv_professional_summary")) and bool(
                existing_record.get("cv_professional_experience")
            )
            if missing_cv_doc and has_text_content:
                try:
                    cv_doc_path = create_cv_document(
                        existing_record,
                        docs_dir=docs_dir,
                        run_date=existing_record.get("run_date", run_date),
                        candidate_name=candidate_name,
                        candidate_email=candidate_email,
                        cv_font_name=cv_font_name,
                        languages=languages,
                        profile_image_path=profile_image_path,
                        profile_links=profile_links,
                    )
                    existing_record["cv_docx"] = cv_doc_path
                    existing_record["tailored_cv_docx"] = cv_doc_path
                    existing_record["doc_generation_error"] = None
                    checkpoint_changed = True
                except Exception as exc:
                    existing_record["doc_generation_error"] = str(exc)
                    checkpoint_changed = True
            elif missing_cv_doc and existing_record.get("tailored_cv_docx"):
                existing_record["cv_docx"] = existing_record.get("tailored_cv_docx")
                checkpoint_changed = True

            missing_pdf = not existing_record.get("cv_pdf")
            if not missing_pdf and existing_record.get("cv_pdf") and not Path(existing_record["cv_pdf"]).exists():
                missing_pdf = True
            if existing_record.get("cv_docx") and missing_pdf:
                try:
                    existing_record["cv_pdf"] = convert_docx_to_pdf(existing_record["cv_docx"])
                    existing_record["pdf_generation_error"] = None
                    checkpoint_changed = True
                except Exception as exc:
                    existing_record["cv_pdf"] = ""
                    existing_record["pdf_generation_error"] = str(exc)
                    checkpoint_changed = True

            continue

        print(f"Generating docs for job {index}/{total_jobs}: {job_id} - {job.get('title', '')}")

        try:
            generated_payload = generate_docs_for_job(
                deepseek_api_key=deepseek_api_key,
                deepseek_model=args.model,
                gemini_client=gemini_client,
                gemini_model=args.fallback_model,
                cv_text=cv_text,
                job=job,
                candidate_name=candidate_name,
                extra_instructions=args.stage4_extra_prompt,
                prompt_override=args.stage4_prompt_override,
                retries=max(1, args.retries),
                retry_sleep=max(0.0, args.retry_sleep),
            )

            temp_record = {
                **job,
                **generated_payload,
                "run_date": run_date,
                "run_timestamp": run_timestamp,
            }
            ensure_structured_cv_fields(temp_record, candidate_name=candidate_name, cv_text=cv_text)
            cv_doc_path = create_cv_document(
                temp_record,
                docs_dir=docs_dir,
                run_date=run_date,
                candidate_name=candidate_name,
                candidate_email=candidate_email,
                cv_font_name=cv_font_name,
                languages=languages,
                profile_image_path=profile_image_path,
                profile_links=profile_links,
            )
            try:
                cv_pdf_path = convert_docx_to_pdf(cv_doc_path)
                pdf_generation_error = None
            except Exception as exc:
                cv_pdf_path = ""
                pdf_generation_error = str(exc)

            generated_record = {
                **temp_record,
                "cv_docx": cv_doc_path,
                "cv_pdf": cv_pdf_path,
                "tailored_cv_docx": cv_doc_path,
                "pdf_generation_error": pdf_generation_error,
                "doc_generation_error": None,
            }
        except Exception as exc:
            generated_record = {
                **job,
                "cv_professional_summary": "",
                "cv_professional_experience": [],
                "cv_strategic_initiatives": [],
                "cv_skills": [],
                "cv_education": [],
                "tailored_cv": "",
                "cv_docx": "",
                "cv_pdf": "",
                "tailored_cv_docx": "",
                "pdf_generation_error": "",
                "run_date": run_date,
                "run_timestamp": run_timestamp,
                "doc_generation_error": str(exc),
            }

        if not generated_record.get("linkedin_link"):
            generated_record["linkedin_link"] = generated_record.get("link", "")
        if not generated_record.get("apply_link"):
            generated_record["apply_link"] = generated_record.get("linkedin_link", "")

        generated_by_id[job_id] = generated_record
        save_json_file(checkpoint_path, {"generated_records": list(generated_by_id.values())})
        checkpoint_changed = False

        if args.sleep_seconds > 0:
            time.sleep(args.sleep_seconds)

    if checkpoint_changed:
        save_json_file(checkpoint_path, {"generated_records": list(generated_by_id.values())})

    final_records = []
    for job in jobs:
        job_id = str(job.get("job_id"))
        if job_id in generated_by_id:
            final_records.append(generated_by_id[job_id])

    output_json_path = Path(args.output_json)
    output_xlsx_path = Path(args.output_xlsx)
    save_json_file(output_json_path, final_records)
    save_to_excel(
        records=final_records,
        output_path=output_xlsx_path,
        excel_mode=args.excel_mode,
        sheet_name=args.sheet_name.strip(),
        run_date=run_date,
    )

    failed_count = sum(1 for item in final_records if item.get("doc_generation_error"))
    pdf_failed_count = sum(1 for item in final_records if item.get("pdf_generation_error"))
    print("Stage 4 complete.")
    print(f"Generated records: {len(final_records)} -> {output_json_path}")
    print(f"Excel export: {output_xlsx_path} (mode={args.excel_mode})")
    print(f"Word docs directory: {docs_dir.resolve()}")
    print(f"Candidate name: {candidate_name}")
    print(f"Profile image: {profile_image_path if profile_image_path else 'not provided'}")
    print(f"Generation errors: {failed_count}")
    print(f"PDF conversion errors: {pdf_failed_count}")
    print(f"Checkpoint saved: {checkpoint_path}")
    return final_records


__all__ = [
    "create_cv_document",
    "ensure_structured_cv_fields",
    "generate_docs_for_job",
    "load_json_file",
    "main",
    "run_stage4_pipeline",
    "save_to_excel",
]


if __name__ == "__main__":
    raise SystemExit(main())
