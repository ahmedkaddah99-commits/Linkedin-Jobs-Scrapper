# Runr corporate description pilot

Date: 2026-10-02. Source: the current published head in the actual Turso database.
Model: `mistralai/mistral-nemo`. Descriptions use the `runr_description_nemo_v2` contract.
The 20 source postings selected for this pilot are in English.

Live status (2026-10-02): published to the actual Turso database. The frontend and API
are live on deployment commit `e402aebca72af50728735b43ac7f6fa81fa3c1bc`.
Turso readback matched all 20 generated descriptions, content hashes, prompt versions,
and current published job versions. All 20 Runr URLs returned HTTP 200. A signed-in
visual review of the job pages remains for the owner; the browser was unavailable
for that check during this run.

Follow-up (2026-10-02): all 20 records were refreshed with source-checked experience values and verified again in Turso. The updated frontend shows posting age in hours or days, appends `experience` to year values, shows seniority and employment type together, renders each description line as a bullet, and removes the application section and Runr notice. The [second 20-job cohort](../corporate_description_followup_2026-10-02/REPORT.md) uses distinct employers.

| # | Company | Job | Runr app | Employer posting | Sections (R/Req/Pref/B/Apply) |
|---:|---|---|---|---|---:|
| 1 | UnitedHealth Group | Principal Data Analyst, Internal Analytics - Remote | [Open in Runr](https://app.userunr.com/jobs/canonical_job_863f93d9c1694bf6be20b989e2e4e72f) | [Original](https://careers.unitedhealthgroup.com/job/eden-prairie/principal-data-analyst-internal-analytics-remote/34088/99981277296) | 14/10/7/1/1 |
| 2 | UnitedHealth Group | Associate Network Contractor | [Open in Runr](https://app.userunr.com/jobs/canonical_job_8c860a2c09e148c7813dce42e8818971) | [Original](https://careers.unitedhealthgroup.com/job/north-charleston/associate-network-contractor/34088/99981277152) | 7/4/1/1/0 |
| 3 | UnitedHealth Group | Sr. AI/ML Engineer - Remote | [Open in Runr](https://app.userunr.com/jobs/canonical_job_b2bde654965c4e759b27372feecb84e3) | [Original](https://careers.unitedhealthgroup.com/job/schaumburg/sr-ai-ml-engineer-remote/34088/99981277232) | 10/5/6/1/0 |
| 4 | Unilever | Process Engineer | [Open in Runr](https://app.userunr.com/jobs/canonical_job_fdc11141d32e43598bff61ebef96b705) | [Original](https://careers.unilever.com/de/stellenbeschreibung/leioa/process-engineer/34155/99975727872) | 12/6/1/0/0 |
| 5 | Intuitive | Senior Payroll Specialist | [Open in Runr](https://app.userunr.com/jobs/canonical_job_9857ab3e53934db0acd1596a9975c875) | [Original](https://linkedin.com/jobs/view/4451542071) | 13/6/8/0/0 |
| 6 | L3Harris Technologies | Senior Specialist, Subcontracts | [Open in Runr](https://app.userunr.com/jobs/canonical_job_21a5a64bada44e8aa4ad9e779390bd6a) | [Original](https://careers.l3harris.com/en/job/united-states/senior-specialist-subcontracts/4832/99780405344) | 12/4/12/1/1 |
| 7 | L3Harris Technologies | Senior Specialist, Cyber Intelligence | [Open in Runr](https://app.userunr.com/jobs/canonical_job_ab0aa155d065448697c4656fc183ab7e) | [Original](https://careers.l3harris.com/en/job/camden/senior-specialist-cyber-intelligence/4832/99756757904) | 6/3/5/0/0 |
| 8 | Intuitive | Ion Clinical Sales Manager | [Open in Runr](https://app.userunr.com/jobs/canonical_job_b295cb8939b04773ab962414b56ed195) | [Original](https://linkedin.com/jobs/view/4460342495) | 6/10/0/0/0 |
| 9 | L3Harris Technologies | Specialist, Electrical Engineering | [Open in Runr](https://app.userunr.com/jobs/canonical_job_d88d2ba2e79e42459d03a1bf2fd15df5) | [Original](https://careers.l3harris.com/en/job/rochester/specialist-electrical-engineering/4832/99761839952) | 6/4/3/0/0 |
| 10 | Luxoft | Core Banking Architect | [Open in Runr](https://app.userunr.com/jobs/canonical_job_78ef0fda356f401685544d3121820911) | [Original](https://career.luxoft.com/jobs/core-banking-architect-27910) | 10/9/4/0/0 |
| 11 | Luxoft | DevOps Engineer | [Open in Runr](https://app.userunr.com/jobs/canonical_job_ebb2a75acc2c4aadad5516faf35b45e6) | [Original](https://career.luxoft.com/jobs/devops-engineer-27908) | 9/10/1/0/0 |
| 12 | Luxoft | Senior QA Engineer - Automation & Manual | [Open in Runr](https://app.userunr.com/jobs/canonical_job_94e2f74cf2e7413c89965ea38ac7540b) | [Original](https://career.luxoft.com/jobs/senior-qa-engineer-automation-manual-27906) | 9/7/3/0/0 |
| 13 | Luxoft | Technical Project Manager | [Open in Runr](https://app.userunr.com/jobs/canonical_job_63c7709540c940d1bacb7c12ef6b1fad) | [Original](https://career.luxoft.com/jobs/technical-project-manager-27911) | 19/9/4/0/0 |
| 14 | Intuitive | Commercial Learning Trainer | [Open in Runr](https://app.userunr.com/jobs/canonical_job_c3991ac4b77d47f2804214604178fcf0) | [Original](https://linkedin.com/jobs/view/4473927677) | 18/10/1/0/0 |
| 15 | Intuitive | Senior Product Portfolio Marketing Manager | [Open in Runr](https://app.userunr.com/jobs/canonical_job_30062c357f874ed88fdb1f5169a9050f) | [Original](https://linkedin.com/jobs/view/4463615427) | 8/4/7/0/0 |
| 16 | Intuitive | Marketing Assistant - 12 months temporary contract | [Open in Runr](https://app.userunr.com/jobs/canonical_job_c7e20a4a014247f498e985f3faf52835) | [Original](https://linkedin.com/jobs/view/4459303825) | 17/10/1/0/0 |
| 17 | Intuitive | Contract Specialist | [Open in Runr](https://app.userunr.com/jobs/canonical_job_5bbfe81963a241a68f73afb7a7e74295) | [Original](https://linkedin.com/jobs/view/4460324958) | 6/7/1/0/0 |
| 18 | Intuitive | Sourcing Manager MRO (EMEA) | [Open in Runr](https://app.userunr.com/jobs/canonical_job_be6dd8fad0134fb5b20d320df17ad63b) | [Original](https://linkedin.com/jobs/view/4451537249) | 26/17/2/0/0 |
| 19 | NXP Semiconductors | Learning Management Systems Specialist | [Open in Runr](https://app.userunr.com/jobs/canonical_job_17fcf1f8f5f54108bdfc68fa23eb31c3) | [Original](https://linkedin.com/jobs/view/4473278031) | 18/5/3/0/0 |
| 20 | SUSE | Premium Support Engineer | [Open in Runr](https://app.userunr.com/jobs/canonical_job_95bf07cfa0554e068faeb05314f19a08) | [Original](https://linkedin.com/jobs/view/4471785521) | 8/10/6/0/0 |

Each Runr URL uses the canonical job ID in the current Turso publication. The source rows, original descriptions, generated output, and pre-pilot record snapshot are saved alongside this report.
Empty Preferred or Benefits sections are hidden in the v2 reading view. Invalid model header values are hidden independently.

Rollback: run `.venv\Scripts\python.exe scripts/run_corporate_description_pilot.py rollback` from the original checkout with its saved `rollback.json`. Revert the deployment commit to restore the earlier frontend and API behavior.
