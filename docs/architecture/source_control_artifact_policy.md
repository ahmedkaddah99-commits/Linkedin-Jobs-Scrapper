# Source-Control Artifact Policy

Status: accepted for cleanup planning

Date: 2026-05-31

This policy defines what belongs in git for this project and what should remain local runtime data. It is intentionally conservative: no generated output or user-owned data should be deleted during cleanup. Follow-up cleanup should first ignore future noise, then untrack existing generated files with `git rm --cached` so local files stay on disk.

## Source Files

Keep these in git:

- `backend/` source code, excluding generated outputs and local runtime data.
- `frontend/` source code, lockfile, config, and scripts, excluding `frontend/node_modules/` and `frontend/dist/`.
- `scripts/`, `deploy/`, `docs/`, `tests/`, and intentional small fixtures.
- Root operator files such as `README.md`, `ARCHITECTURE.md`, `requirements*.txt`, `package.json`, `package-lock.json`, `ecosystem.config.cjs`, `run_daily.ps1`, and `workspace_runner.py`.
- `.env.example` and other sanitized example config files.

## Test Fixtures

Keep only deliberate, small, deterministic fixtures in git.

Preferred fixture locations:

- `tests/fixtures/`
- `test-CV/fixtures/` only if the directory is explicitly converted into a maintained fixture package.
- `docs/examples/` for static examples that are part of documentation.

Do not keep generated CV matrices, generated Word/PDF exports, bulk-export zips, live scraped jobs, or user-specific assets as fixtures. If a test needs one of those, add the smallest sanitized file under `tests/fixtures/` and document why it exists.

## Generated Outputs

These are generated/runtime outputs and should not be tracked:

- `backend/config/outputs/`
- `generated_docs/`, except a deliberately maintained placeholder such as `generated_docs/_assets/.gitkeep` if needed.
- Root stage outputs such as `stage1_scrape_snapshot.json`, `stage2_filtered_local.json`, `stage2_rejected_local.json`, `stage3_filtered_ai.json`, `stage3_rejected_local.json`, `stage3_checkpoint.json`, `stage4_checkpoint.json`, and `stage4_documents.json`.
- `final_jobs_with_docs.xlsx`, `working-file.xlsx`, `deepseek_excluded_jobs.json`, and `highly_curated_jobs.json`.
- `manual_url_jobs.json` and `manual_url_failures.json`.
- Generated `.docx`, `.pdf`, `.xlsx`, and `.zip` files unless they are explicitly sanitized fixtures under `tests/fixtures/`.

Follow-up cleanup should untrack existing generated files with `git rm --cached`, not delete them from disk.

## Local Runtime Data

These are local runtime data and should not be tracked:

- `.backend_data/`
- `.backend_data_test/`
- `.backend_test_tmp/`
- `.backend_auth_cli_test/`
- `.backend_data_cli_test/`
- `.pytest_cache/`
- `__pycache__/`
- `.runr_*`
- `.backend_*`
- `logs/`
- SQLite databases such as `*.sqlite`, `*.sqlite3`, and `*.db` unless a tiny fixture database is explicitly placed under `tests/fixtures/`.

## Local User Data

These are user-owned or user-derived and should not be tracked:

- `user_config/.env`
- `user_config/cv_master.txt`
- `user_config/_profile_from_cv.png`
- `user_config/profile_photos/`
- `user_config/candidate_assets/`
- `user_config/manual_job_urls.txt`
- `user_config/job_seeker_config.json`
- `user_config/discovered_regular_company_career_sites.live.txt`
- `user_config/discovered_phd_university_career_sites.live.txt`

If the app needs starter user config, add sanitized examples such as `user_config/job_seeker_config.example.json` or docs instructions. Do not commit real CVs, profile photos, candidate documents, uploaded assets, or live discovery lists.

The static logo files currently under `user_config/` should be moved in a later cleanup to a source-owned location such as `frontend/public/` or `backend/assets/` if the product uses them.

## Archives And External Datasets

These should not be tracked in the active product repo:

- `Archive/`
- `Jobs-Urls/` unless specific files are promoted to sanitized fixtures.
- External raw datasets, cleaned snapshots, exploratory notebooks/scripts, and old stage-output dumps.

If an archived script is still useful, move the script alone into `scripts/` or `docs/archive/` and keep its raw input/output data out of git.

## Dependency Directories

These should never be tracked:

- `node_modules/`
- `frontend/node_modules/`
- `.venv/`
- any package-manager cache directories.

The root `node_modules/` directory is currently tracked and should be untracked in a follow-up cleanup.

## Recommended Ignore Updates

Wave 1 should update `.gitignore` to include at least:

```gitignore
node_modules/
frontend/node_modules/
frontend/dist/
.venv/
.pytest_cache/
__pycache__/
*.pyc
*.sqlite
*.sqlite3
*.db
.backend_*
.runr_*
logs/
backend/config/outputs/
generated_docs/
!generated_docs/_assets/
stage*_local.json
stage*_ai.json
stage*_checkpoint.json
stage*_documents.json
manual_url_jobs.json
manual_url_failures.json
final_jobs_with_docs.xlsx
working-file.xlsx
deepseek_excluded_jobs.json
highly_curated_jobs.json
user_config/.env
user_config/cv_master.txt
user_config/_profile_from_cv.png
user_config/profile_photos/
user_config/candidate_assets/
user_config/manual_job_urls.txt
user_config/job_seeker_config.json
user_config/*.live.txt
Archive/
Jobs-Urls/
test CV/
```

Keep `test-CV/` only if it is converted into a maintained fixture package. Otherwise ignore and untrack it too.

## Safe Follow-Up Commands

These commands are recommendations for Wave 1. They remove files from git tracking only; they do not delete local files.

Run each group only after reviewing `git status --short` and confirming the path still matches this policy:

```powershell
git rm -r --cached -- node_modules
git rm -r --cached -- Archive
git rm -r --cached -- backend/config/outputs
git rm -r --cached -- generated_docs
git rm -r --cached -- "test CV"
git rm -r --cached -- test-CV
git rm -r --cached -- user_config/profile_photos
git rm -r --cached -- user_config/candidate_assets
git rm --cached -- final_jobs_with_docs.xlsx deepseek_excluded_jobs.json highly_curated_jobs.json stage1_scrape_snapshot.json stage2_filtered_local.json stage2_rejected_local.json stage3_filtered_ai.json stage3_rejected_local.json stage4_checkpoint.json stage4_documents.json
git rm --cached -- user_config/cv_master.txt user_config/_profile_from_cv.png user_config/manual_job_urls.txt user_config/job_seeker_config.json user_config/discovered_regular_company_career_sites.live.txt user_config/discovered_phd_university_career_sites.live.txt
```

If any path is needed as a fixture, copy a sanitized minimal version into `tests/fixtures/` before untracking the original. Do not use `git clean`, `git reset --hard`, or recursive deletion as part of this cleanup.

## Decision Summary

- Source code, small fixtures, config examples, and durable docs belong in git.
- Generated outputs, runtime databases/logs, dependency folders, user assets, real CVs, and live scraped data do not belong in git.
- Cleanup should prefer ignore rules plus `git rm --cached`.
- Local user data must remain on disk unless the user explicitly asks to delete it.
