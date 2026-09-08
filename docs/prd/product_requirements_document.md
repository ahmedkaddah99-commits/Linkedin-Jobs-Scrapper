# Product Requirements Document
## LinkedIn Job Automation App — Feature Gap Analysis & Prioritization

> **How to read this document**
> - 🟡 **Partially Migrated** — Feature existed in old scripts but is not yet fully wired into the new frontend/backend.
> - 🔴 **Missing from Migration** — Was present in old scripts but has been lost or not yet connected in the refactor.
> - 🟢 **Completely New** — Does not exist anywhere in the codebase today.
>
> Requirements are ordered from **highest priority / easiest to integrate** → **lowest priority / most complex**.

---

## Phase 1 — Core Infrastructure & Profile Setup
*These are the foundation. Nothing else works well without them.*

---

### REQ-01 — CV Upload & Auto-Parsing into Structured Profile Sections
**Priority:** P0 | 🟡 Partially Migrated

**Current state:**  
The old pipeline reads [user_config/cv_master.txt](file:///c:/Users/ahmed/Projects_Local/job-automation/Linkedin%20Jobs%20Scrapper/user_config/cv_master.txt) as raw text and injects it into AI prompts. The new [SettingsPage](file:///c:/Users/ahmed/Projects_Local/job-automation/Linkedin%20Jobs%20Scrapper/frontend/src/pages/SettingsPage.jsx#445-655) has an "Upload New CV" and "Replace Current CV" button rendered in the UI, but these buttons are **not wired** to any backend endpoint. The `/settings` API only handles structured profile fields (name, role title, summary, experience entries). There is no CV file upload endpoint or CV text parsing logic exposed to the frontend.

**Requirement:**  
When the user uploads a CV file (PDF or DOCX), the backend must:
1. Extract raw text from the file.
2. Auto-populate structured sections: Professional Summary, Work Experience entries, Skills/Competencies.
3. Persist the raw CV text as the `cv_master` record so later pipeline stages can use it.
4. Surface a diff/preview so the user can review and edit the auto-filled fields before saving.

**Required fields marked mandatory (\*):**
- Full Name *
- Email *
- Professional Summary *
- At least one Work Experience entry *

**Acceptance criteria:**
- Upload button accepts PDF and DOCX.
- After upload, the Profile tab in Settings is pre-filled with the extracted content.
- User can edit any section before saving.
- The raw CV text is stored and used by the pipeline's AI stages (Stage 1 title filter, Stage 3 screen, Stage 4 generation).

---

### REQ-02 — LinkedIn & GitHub Profile Links in Candidate Config
**Priority:** P0 | 🟡 Partially Migrated

**Current state:**  
The old [job_seeker_config.json](file:///c:/Users/ahmed/Projects_Local/job-automation/Linkedin%20Jobs%20Scrapper/user_config/job_seeker_config.json) has `profile_links.linkedin` and `profile_links.github` with URL, display text, icon, and logo path. The new Settings > Profile tab has a single "Website / Portfolio" field — no LinkedIn or GitHub fields exist in the UI or the `/settings` API schema yet.

**Requirement:**  
Add named social link fields to the Profile tab:
- LinkedIn URL
- GitHub URL
- (Optional) additional link

These must be persisted in the candidate config and injected into generated CV documents (header section, hyperlink-styled rows in DOCX output).

**Acceptance criteria:**
- Fields appear under Settings > Profile.
- Saved values are embedded in generated DOCX output as clickable links next to the candidate's name.

---

### REQ-03 — Workspace Job Search Filters: Time Window, Experience Level, Forbidden Title Keywords
**Priority:** P0 | 🟡 Partially Migrated

**Current state:**  
The old [job_seeker_config.json](file:///c:/Users/ahmed/Projects_Local/job-automation/Linkedin%20Jobs%20Scrapper/user_config/job_seeker_config.json) stores `time_posted_seconds`, `experience_levels` (array of LinkedIn level codes), and `forbidden_title_keywords`. These flow into Stage 1 scraping and Stage 2 local filter. In the new Workspace Builder, users can set search keywords and geo ID via configuration fields, but **experience levels**, **time window**, and **forbidden title keyword lists** are not exposed as workspace configuration fields in the builder catalog.

**Requirement:**  
Expose the following as first-class workspace configuration fields in the Workspace Builder and persist them as workspace settings:
- **Time posted window** — select: Last 24h / Last 48h / Last week / Last 2 weeks / Last month
- **Experience levels** — multi-select: Internship / Entry / Associate / Mid-Senior / Director / Executive
- **Forbidden title keywords** — tag list input (comma-separated or chip input)
- **Low applicant threshold** — numeric field (currently hardcoded at 80)

**Acceptance criteria:**
- Fields appear in the "Search And Routing Settings" section of the Workspace Builder.
- Values are passed to Stage 1 scraper and Stage 2 local filter at run time.
- Existing workspaces show saved values when edited.

---

### REQ-04 — Language Filter Settings per Workspace
**Priority:** P0 | 🟡 Partially Migrated

**Current state:**  
The old [job_seeker_config.json](file:///c:/Users/ahmed/Projects_Local/job-automation/Linkedin%20Jobs%20Scrapper/user_config/job_seeker_config.json)'s `runtime.stage2` and `runtime.stage3` include language thresholds (`max_german_level: "B2"`, French/Spanish char thresholds). These drive Stage 2 and Stage 3 language rejection filters. The new workspace builder does not expose any language filter settings.

**Requirement:**  
Add a "Language Requirements" section to the Workspace Builder with:
- **Max German level** — select: A1 / A2 / B1 / B2 / C1 / C2 / Any
- **Reject French jobs** — toggle
- **Reject Spanish jobs** — toggle
- **Candidate languages** — tag list (e.g. "German — B1/B2")

The candidate languages list should also appear in Settings > Profile for global use.

**Acceptance criteria:**
- Filter runs at Stage 2 and Stage 3 using workspace-specific language settings.
- Candidate languages list in Profile Settings is injected into generated CV documents' Languages section.

---

### REQ-05 — AI Stage Model & Prompt Configuration per Workspace
**Priority:** P1 | 🟡 Partially Migrated

**Current state:**  
The old config has `ai.models` (per-stage model names) and `ai.prompts` (per-stage prompt overrides and extra instructions). These are file-level and per-user. The new backend has a `prompt_family` concept on workspaces and a secrets system, but there is no UI for editing the AI model used per stage or overriding prompts per workspace.

**Requirement:**  
Add an "AI Configuration" section to the Workspace Builder (collapsed/advanced):
- **Stage 1 model** — text input (e.g. `deepseek-chat`)
- **Stage 3 model** — text input (e.g. `deepseek-chat`)
- **Stage 4 model** — text input + fallback model field
- **Stage 1 extra instructions** — textarea
- **Stage 3 extra instructions** — textarea
- **Stage 4 extra instructions** — textarea

Full prompt override fields can be omitted from the UI for now (they are very advanced) but should not break the pipeline if they exist in the DB.

**Acceptance criteria:**
- AI model and extra instruction fields are persisted in workspace settings.
- Pipeline stages pick up workspace-level model overrides instead of the global config.

---

## Phase 2 — CV Design & Document Generation
*Covers document look, template, and coloring options.*

---

### REQ-06 — CV Template & Color Scheme Selection (No-Design-Required)
**Priority:** P1 | 🟢 Completely New

**Current state:**  
The backend renders CVs using a single hardcoded DOCX template (defined in [backend/capabilities/tailored_documents/rendering.py](file:///c:/Users/ahmed/Projects_Local/job-automation/Linkedin%20Jobs%20Scrapper/backend/capabilities/tailored_documents/rendering.py)). There is no user-facing template or color selector.

**Requirement:**  
The user should be able to choose their CV visual style without being a designer:
1. **Template selector** — a preselected set of CV layout templates (e.g. Classic, Modern, Compact, EuroPass-style). Shown as visual thumbnail cards. Default option is one pre-selected.
2. **Color palette selector** — 6–10 curated color schemes the user can pick from (shown as color swatches). The app applies the chosen primary/accent colors to headings, section dividers, and link text in the DOCX output.
3. **Font selection** — dropdown of safe professional fonts (Calibri, Arial, Georgia, etc.).

> [!IMPORTANT]
> This is a product-facing UI feature but requires backend support for template parameterization. The rendering module needs to accept a `template_id`, `color_scheme`, and `font` at generation time.

**Acceptance criteria:**
- Template and color scheme settings appear under Settings > Documents.
- A preview card shows an approximation of the visual style.
- The selected template/color/font is persisted per user and used by Stage 4 document generation.

---

### REQ-07 — Profile Photo in CV (Toggle + Upload)
**Priority:** P1 | 🟡 Partially Migrated

**Current state:**  
The old config has `profile_image_path` pointing to [user_config/_profile_from_cv.png](file:///c:/Users/ahmed/Projects_Local/job-automation/Linkedin%20Jobs%20Scrapper/user_config/_profile_from_cv.png). The new Settings > Profile card shows a placeholder avatar and an "edit" icon camera button, but it leads nowhere — no image upload endpoint exists.

**Requirement:**  
- Add a working photo upload in Settings > Profile (accept JPG/PNG, max 2MB, crop to square).
- Add a **"Include photo in CV"** toggle in Settings > Documents.
- When toggle is ON, the profile photo is embedded in the top-right of the generated DOCX.
- When toggle is OFF, no photo is included.

**Acceptance criteria:**
- Photo upload endpoint exists in the backend.
- Generated DOCX reflects the toggle state.

---

### REQ-08 — System-Preselected Job Title Options for CV Target Focus
**Priority:** P2 | 🟢 Completely New

**Current state:**  
No such feature exists. The pipeline targets a generic job search keyword list.

**Requirement:**  
When starting a new workspace or run, the app should present a preselected set of role categories (e.g. "Product Manager", "Business Analyst", "Project Manager", "Consultant") that the user can target. This drives:
- The job search keywords.
- The AI screening prompt context.
- The CV emphasis (which skills/experiences to foreground in tailored generation).

The user can select one primary target role, or up to 3 max role types to blend.

**Acceptance criteria:**
- Role selector appears in the Workspace Builder as a "Target Role" section.
- Selected roles adjust the default keyword list and AI prompt context automatically.

---

## Phase 3 — Job Tracker (Application Pipeline UI)
*Tracking applications sent and their status.*

---

### REQ-09 — Application Tracker View (Kanban or Table)
**Priority:** P1 | 🟡 Partially Migrated

**Current state:**  
The old pipeline exported a final [final_jobs_with_docs.xlsx](file:///c:/Users/ahmed/Projects_Local/job-automation/Linkedin%20Jobs%20Scrapper/final_jobs_with_docs.xlsx) tracker file. The new backend has a `SqliteJobStore` and `SqliteReviewStore` with job status, but the frontend's Review Queue page is the only job-level view — it is focused on pre-send review, not post-send tracking. There is no dedicated "tracker" page showing applied, responded, or rejected applications.

**Requirement:**  
Add a **Tracker page** (new frontend route `/tracker`) with the following columns/states:
- **Applied** — job was approved and documents were generated; application submitted
- **Email Confirmed** — application submitted; email confirmation received
- **Interview Invited** — employer requested an interview
- **Rejected** — application was rejected (by employer or user)

User can manually move a job card between columns or update its status.

> [!NOTE]
> The "Applied" flag should be settable from the Review Queue page once the user approves a job package — a single "Mark as Applied" action.

**Acceptance criteria:**
- Tracker page is accessible from the main nav.
- All jobs from completed runs that have been approved in Review Queue appear in the tracker.
- User can update status per job; status is persisted in the backend.
- Each card shows: job title, company, run date, status badge, link to job posting.

---

### REQ-10 — Email Verification Flag for Applications
**Priority:** P2 | 🟢 Completely New

**Current state:**  
No email tracking exists anywhere in the codebase.

**Requirement:**  
In the Tracker view, the user should be able to:
- Toggle a job's status to "Email Confirmed" once they receive a confirmation email.
- Optionally flag "Applied" automatically when the status is set from the Review Queue (configurable in Review Preferences as "Auto-mark Applied on Approve").

**Note:** Email *reading* (e.g. Gmail integration) is out of scope for this phase. This is a manual flag only.

**Acceptance criteria:**
- "Email Confirmed" toggle appears on each tracker card.
- Toggling updates the backend status immediately.

---

### REQ-11 — Application Rejection Notification & Status Auto-Update
**Priority:** P3 | 🟢 Completely New

**Current state:**  
No notification system exists.

**Requirement:**  
When the user manually marks a job as "Rejected" in the tracker, the app should:
- Record a rejection timestamp.
- Show it in a "Rejected" status bucket in the tracker.
- (Future) Support notifications when an employer's system sends a rejection — out of scope for now; manual-only.

**Acceptance criteria:**
- Rejected jobs show in a "Rejected" column/filter in the Tracker.
- Rejection reason (optional text note) can be entered per card.

---

## Phase 4 — Job Discovery: Direct Company Scraping & Apply
*The power feature for bypassing job boards.*

---

### REQ-12 — Direct Company Career Page Scraping as a Source
**Priority:** P2 | 🟡 Partially Migrated

**Current state:**  
The old `bc_automation` scripts had logic to scrape company career pages directly (Stepstone, LinkedIn, Indeed). The new backend has a connector-based architecture (`backend/connectors/job_boards/`) but the direct company career page scraper has not been ported as a named connector in the workspace builder catalog. Manual URL ingestion (`manual_url_ingestion.py` / `user_config/manual_job_urls.txt`) works but requires file editing.

**Requirement:**  
Expose a **"Company Career Sites"** source option in the Workspace Builder:
- The user can maintain a list of target companies (company name + career site URL) in Settings > Sources.
- The pipeline scrapes those URLs for open roles matching the workspace keywords.
- Found jobs enter the same pipeline filter stages as LinkedIn-sourced jobs.

Additionally, promote the **Manual URL Ingestion** workflow into the UI:
- Add a "Paste Job URLs" input in the Review Queue or Workspace page instead of requiring file edits.

**Acceptance criteria:**
- Company list is editable in Settings or Workspace Builder.
- Manual URL paste field exists in the UI and triggers the manual ingestion endpoint.
- Scraped company jobs flow through Stages 2–4 identically to LinkedIn jobs.

---

### REQ-13 — Career Profile: Apply on Company Site (Easy Apply Automation)
**Priority:** P3 | 🟢 Completely New

**Current state:**  
No apply automation exists anywhere. The pipeline generates documents; applying is always manual.

**Requirement:**  
After the user approves a job in the Review Queue and the CV + cover letter are generated, provide a **"Apply on Company Site"** button that:
1. Opens the job's application URL in a new tab.
2. Optionally pre-fills form fields using browser automation (Playwright/Selenium) with data from the candidate profile.

> [!CAUTION]
> Browser automation for form submission is highly site-specific and fragile. This is labeled as a **prototype-level** feature — the initial version should only open the URL and optionally export a data payload the user can paste. Full form automation is future scope.

**Acceptance criteria (v1):**
- "Apply" button visible on approved job cards in the Review Queue.
- Clicking it opens the job URL in a new browser tab.
- A "Copy Application Data" action copies name, email, and a one-paragraph summary to clipboard.

---

## Phase 5 — Referrals & Networking (New Capabilities)
*Fully new feature area — build after core features are complete.*

---

### REQ-14 — Referral Contacts Database
**Priority:** P3 | 🟢 Completely New

**Current state:**  
No referral or contact management exists anywhere.

**Requirement:**  
Add a **Referrals section** (Settings > Referrals or dedicated nav link) where the user can maintain a list of contacts at target companies:
- Contact name, company, LinkedIn URL, relationship note.
- "Can refer me" flag.

When a job at a known referral contact's company appears in the Review Queue, the app should highlight it with a "You have a contact here" badge.

**Acceptance criteria:**
- Contacts are editable in the UI.
- Matched jobs in Review Queue show a referral badge.

---

### REQ-15 — Referral Outreach Message Generation
**Priority:** P3 | 🟢 Completely New

**Current state:**  
No message generation for outreach exists.

**Requirement:**  
For any job where the user has a referral contact on file, generate a contextual LinkedIn outreach message (or email draft) using the candidate's CV and the job description. The message should:
- Be concise (3–4 sentences).
- Reference the specific role.
- Ask for a referral naturally.
- Be editable before the user sends it.

**Acceptance criteria:**
- "Generate Outreach Message" button appears on referral-matched job cards.
- Generated message pre-populates an editable text box.
- User can copy the message to clipboard with one click.

---

### REQ-16 — LinkedIn Hiring Manager Outreach
**Priority:** P4 | 🟢 Completely New

**Current state:**  
No LinkedIn integration for messaging exists.

**Requirement:**  
Identify the hiring manager for a given job posting (via LinkedIn data or company website) and generate a short, targeted outreach message to send them directly. 

> [!CAUTION]
> LinkedIn's ToS restricts automated messaging. This feature should be implemented as a **"draft and copy" helper only** — the user manually sends the message through LinkedIn. Direct automation of LinkedIn messaging is explicitly out of scope.

**Acceptance criteria:**
- "Find Hiring Manager" action attempts to identify the hiring manager name/title from the job data.
- A pre-written, editable message is generated.
- User copies and sends manually via LinkedIn.

---

## Summary Table

| ID | Requirement | Type | Priority |
|----|-------------|------|----------|
| REQ-01 | CV Upload & Auto-Parsing | 🟡 Partial Migration | P0 |
| REQ-02 | LinkedIn & GitHub Profile Links | 🟡 Partial Migration | P0 |
| REQ-03 | Job Search Filters (time, exp, forbidden) | 🟡 Partial Migration | P0 |
| REQ-04 | Language Filter Settings per Workspace | 🟡 Partial Migration | P0 |
| REQ-05 | AI Stage Model & Prompt Config | 🟡 Partial Migration | P1 |
| REQ-06 | CV Template & Color Scheme Selection | 🟢 New | P1 |
| REQ-07 | Profile Photo Toggle & Upload | 🟡 Partial Migration | P1 |
| REQ-08 | Target Role Presets | 🟢 New | P2 |
| REQ-09 | Application Tracker View | 🟡 Partial Migration | P1 |
| REQ-10 | Email Verification Flag | 🟢 New | P2 |
| REQ-11 | Rejection Notification & Status | 🟢 New | P3 |
| REQ-12 | Direct Company Scraping + Manual URL UI | 🟡 Partial Migration | P2 |
| REQ-13 | Apply on Company Site (v1) | 🟢 New | P3 |
| REQ-14 | Referral Contacts Database | 🟢 New | P3 |
| REQ-15 | Referral Outreach Message Generation | 🟢 New | P3 |
| REQ-16 | LinkedIn Hiring Manager Outreach | 🟢 New | P4 |

---

## Implementation Sequence Recommendation

```
Phase 1 (Core / P0): REQ-01 → REQ-02 → REQ-03 → REQ-04
Phase 2 (Documents / P1): REQ-05 → REQ-07 → REQ-06 → REQ-09
Phase 3 (Discovery / P2): REQ-08 → REQ-12 → REQ-10
Phase 4 (Advanced / P3+): REQ-11 → REQ-13 → REQ-14 → REQ-15 → REQ-16
```
