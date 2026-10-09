# Repository Hygiene Runbook

Status: active

Date: 2026-05-31

Use this runbook with the source-control artifact policy in `docs/architecture/source_control_artifact_policy.md`.

## Artifact Locations

- Source code: `backend/`, `frontend/src/`, `frontend/scripts/`, `scripts/`, `deploy/`, and root operator files.
- Durable docs: `README.md`, `ARCHITECTURE.md`, `docs/architecture/`, and curated docs under `docs/`.
- Historical reports: `docs/reports/`.
- Generated backend outputs: `backend/config/outputs/`.
- Generated document exports: `generated_docs/` and user asset export folders.
- Runtime data: `.backend_*`, `.runr_*`, `.backend_data*/`, `logs/`, temp folders, and SQLite files.
- Local user-owned data: `user_config/profile_photos/`, `user_config/candidate_assets/`, `user_config/cv_master.txt`, `user_config/job_seeker_config.json`, and live discovery lists.
- External datasets and archives: `Archive/`, `Jobs-Urls/`, `test CV/`, and `test-CV/` unless a small sanitized fixture is promoted under `tests/fixtures/`.

## Cleanup Rules

- Do not delete user data as part of hygiene cleanup.
- Prefer `.gitignore` updates first.
- For files already tracked by git, use `git rm --cached` so local files remain on disk.
- Before untracking a path, run `git status --short` and confirm it matches the artifact policy.
- If a generated file is needed by a test, copy a small sanitized version into `tests/fixtures/` before untracking the original.

## Safe Untracking Commands

These commands are intentionally not run by this ticket. Review and run them only after confirming the paths are still generated/runtime/user-owned data.

```powershell
git rm -r --cached -- node_modules
git rm -r --cached -- Archive
git rm -r --cached -- Jobs-Urls
git rm -r --cached -- backend/config/outputs
git rm -r --cached -- generated_docs
git rm -r --cached -- "test CV"
git rm -r --cached -- test-CV
git rm -r --cached -- user_config/profile_photos
git rm -r --cached -- user_config/candidate_assets
git rm --cached -- final_jobs_with_docs.xlsx working-file.xlsx deepseek_excluded_jobs.json highly_curated_jobs.json
git rm --cached -- stage1_scrape_snapshot.json stage2_filtered_local.json stage2_rejected_local.json stage3_filtered_ai.json stage3_rejected_local.json stage4_checkpoint.json stage4_documents.json
git rm --cached -- user_config/cv_master.txt user_config/_profile_from_cv.png user_config/manual_job_urls.txt user_config/job_seeker_config.json
git rm --cached -- user_config/discovered_regular_company_career_sites.live.txt user_config/discovered_phd_university_career_sites.live.txt
```

Avoid `git clean`, `git reset --hard`, and recursive filesystem deletion for repository hygiene work.
