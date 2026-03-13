# LinkedIn Jobs Automation (Scraper + DeepSeek)

This project automates:
1. Scraping and enriching LinkedIn jobs.
2. Filtering jobs (local rules + AI relevance check).
3. Generating tailored CV outputs per job (DOCX/PDF + JSON/XLSX).

## Tech Stack
- Python 3.12.7
- Free Dependencies
- DeepSeek API (main AI provider)
- Gemini API (optional fallback in Stage 4)
- ScrapeOps API (Scrapper) - make sure to activate email to get full access to all feautes for free.

Main pipeline scripts:
- `stage1_scrape_enrich.py`
- `stage2_filter_local.py`
- `stage3_filter_ai.py`
- `stage4_docs_export.py`
- `orchestrator.py`

## Setup (Windows + venv)
```powershell
# from repo root
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Create `user_config/.env`:
```env
SCRAPEOPS_API_KEY=your_scrapeops_key
DEEPSEEK_API_KEY=your_deepseek_key
# optional fallback for stage 4:
GEMINI_API_KEY=your_gemini_key
```

## How To Run

Run full pipeline (Stage 1 -> 4):
```powershell
.\.venv\Scripts\python.exe orchestrator.py
```


## Most Important: How To Customize For Different Job Targets

Edit `user_config/job_seeker_config.json` and adjust:

### 1) Job target rules
- `job_search.keywords`: add/remove target roles.
- `job_search.linkedin_geo_id`: change location.
- `job_search.experience_levels`: adjust seniority.
- `job_search.forbidden_title_keywords`: exclude unwanted roles.
- Stage-2 thresholds (`runtime.stage2.*_special_char_threshold`) for local language filtering behavior.

### 2) AI filtering behavior
- `ai.prompts.stage3_prompt_override` controls what Stage 3 accepts/rejects.
- Keep JSON schema exactly as required by the script.

### 3) Candidate profile used for CV generation
- `candidate.cv_path`: path to your master CV text file (default `user_config/cv_master.txt`).
- `candidate.name`, `candidate.email`, `candidate.languages`: used in generated CV header.
- `candidate.profile_links.linkedin.*` and `candidate.profile_links.github.*`: optional top-of-CV hyperlinks.
  - `url`: target URL (leave empty to hide that link)
  - `text`: clickable text shown next to the icon
  - `icon`: short icon label (for example `in` or `GH`)

### 4) Profile image
- Use **PNG only**.
- Placement: place image in `generated_docs/_assets/` and title it _profile_from_cv.png to replace existing sample image


## CV Content + Format Requirements (Very Important)

The generator parses your master CV text and expects clear section structure.

Recommended section labels in `user_config/cv_master.txt`:
- `PROFESSIONAL EXPERIENCE`
- `PROJECTS`
- `SKILLS`
- `EDUCATION`

Formatting guidance:
- Experience entries should be one role header line + bullet lines.
- Use bullet markers (`- ...`) under roles/projects/thesis.
- Keep degree title and thesis title stable (AI may reword thesis bullets only).

### PROFESSIONAL EXPERIENCE behavior (confirmed)
- The section is **partially protected**, not fully untouched.
- Preserved from your master CV:
  - role titles
  - company names
  - date/period values
  - role order
- Can still be changed:
  - bullet points may be tailored/reworded for each job.
- Fallback behavior:
  - if AI does not provide matched bullets, baseline bullets from `user_config/cv_master.txt` are kept.

### Hardcoded output section titles in generated CV DOCX
The generated CV currently prints these section headings:
- `PROFESSIONAL SUMMARY`
- `PROFESSIONAL EXPERIENCE`
- `PROJECTS`
- `SKILLS`
- `EDUCATION`

If you want different output headings, change them in `stage4_docs_export.py`.

## Common Output Files
- `highly_curated_jobs.json` (Stage 1 output)
- `stage2_filtered_local.json` / `stage2_rejected_local.json`
- `stage3_filtered_ai.json` / `stage3_rejected_local.json`
- `stage4_documents.json`
- `final_jobs_with_docs.xlsx`
- `generated_docs/<run-date>/...` (DOCX/PDF CV files)

## Post-Generation Workflow (How to Track Applications)

After each run, the most important output file is:
- `final_jobs_with_docs.xlsx`

Why it matters:
- It contains the full job list with generated document paths (CV DOCX/PDF and related outputs).
- Stage 4 writes run results into its own sheet, so each run is separated and easy to review.
- Deduplicates Jobs that already exist in any of the sheets even if the job id is not that same.

Practical workflow:
1. Open `final_jobs_with_docs.xlsx` after generation finishes.
2. Copy the current run’s rows/sheet into your separate tracking workbook.
3. In your tracker, keep at least:
   - `Applied?` column
   - `Notes` column
4. Continue applying from the tracker while the automation keeps generating new roles in future runs.

This gives you a stable process:
- Automation handles discovery/filtering/CV generation.
- Your tracker handles application status and manual notes.
