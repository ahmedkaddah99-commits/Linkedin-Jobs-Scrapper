# CV assistance and connections refinement — 11 October 2026

## Scope

Implemented the pasted owner feedback, with the later correction to exclude all imagery, including profile pictures. No generated image is referenced or committed.

- AI Tools replaces Quick Access on selected-job detail pages; Quick Access stays on the browsing page. Job content uses the available width.
- Colored, expandable connections cards show real contacts or designed empty states, with reduced-motion support. School/company overlap remains evidence-based.
- Work-email benefit copy attributes the 3× response-rate statement to Jobright, not Runr. The existing provider is Hunter Email Finder (Found); production lacks HUNTER_API_KEY. API documentation: https://hunter.io/api-documentation#email-finder-found. Claim source: https://www.linkedin.com/posts/jobright-ai_jobright-jobsearch-opentowork-activity-7246911791543267328-6aEN.
- Modern circular CV score, numeric dimension scores, full-description keyword extraction, AI requirement analysis with explicit/inferred provenance, viewport-positioned help, visible Select supported feedback, live generation, inline and side editing, expandable original/current comparisons, latest-draft HTML/PDF export.
- Spacing controls remain deferred as the owner allowed. Cover letters are outside this pass.

## Live examples

Owner account has two saved connections at Siemens. Published job: https://app.userunr.com/jobs/canonical_job_0cc78e2ea338429b8f8eb3b84ff46277.

Requested PERI role: https://app.userunr.com/jobs/canonical_job_50d523fa82e24665ae093ef36efee3ef. A live DeepSeek call with the owned AhmedKaddahCV-P.docx asset analyzed 18 keywords, inferred a five-year seniority benchmark, and rewrote three sections in approximately 11 seconds. The original baseline includes previously tailored wording; generation removes unrelated target-role framing while retaining underlying facts. No source asset changed. Private output is stored outside Git in tmp/cv-reference/live-generated-v2.json and in restricted VPS operations evidence.

The owner is on Free; the deployment config enables the explicitly requested preview only for that user and that PERI job. Other jobs retain Pro generation gating. This is not a plan upgrade.

## Verification

Backend tests cover exact evidence, source preservation, selected sections, unsupported keyword/number rejection, quick scope, asset ownership, revision conflicts, paid gating and preview scope. Frontend tests cover full-description extraction; browser checks cover desktop/mobile generation, supported selections, side editing, draft recovery, export and expandable connection cards. Final test counts and deployment evidence are recorded after activation.

Browser connector connected, but navigation to Runr was denied because its admin-enforced security policy could not be verified. No bypass was attempted. Signed-in production browser interaction is not claimed; local Playwright tests and direct provider/server verification are separate evidence.
