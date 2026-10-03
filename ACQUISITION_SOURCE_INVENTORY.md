# Acquisition source inventory and canonical mapping

This is the pre-implementation inventory for the acquisition repair work. It
describes what the supported acquisition paths can return, where the raw value
is retained, and which values are currently typed for downstream use. A field
that is not present in a source remains `value: null`, with an explicit state;
it is never filled by inference or by an external enrichment provider.

## Canonical storage contract

| Raw/source observation | Canonical field or projection | Storage | State/provenance rule |
| --- | --- | --- | --- |
| Source response object | `source_raw_payload` | Immutable observation/version payload | Retain the complete connector object; no unknown keys are discarded. |
| Source observation URL | `job_detail_url`, `source_url`, `original_url` | Job payload, source observation | Classified as detail/listing/application; detail URLs are never direct apply URLs. |
| Employer application destination | `application_destination.resolved_url`, `application_url` | Version payload and observation columns | Only a verified employer/ATS application route is direct. |
| ATS/job detail URL | `application_destination.job_detail_url`, `user_facing_url` | Version payload | Retained as the truthful user-facing fallback with a warning when no apply route exists. |
| Description markup/text | `description_raw`, `description_html`, `description_text`, `description_decoding` | Version payload; original payload remains intact | Decode entities once; sanitize only the derived HTML projection. |
| Source metadata | `normalized_source_metadata.fields.<field>` | Version payload and quality annotation | Each field has `value`, `state`, and provenance. Unknown values have null provenance. |
| Source timestamps | `source_timestamps` | Version payload and quality annotation | Creation, publication, update, closure, observation, verification, and age are separate semantics. |
| Source/connector identity | `source_ats`, `source_connector`, `source_token`, `source_display_name` | Observation columns and payload | Connector identity is source metadata, never the canonical employer name. |
| Structured description facts | `description_intelligence` / `extraction_fields` | Quality annotation or async intelligence payload | Each fact records state, observation ID, URL, extraction method, and observed time. |
| Quality result | `quality_warnings`, `quality_completeness`, `acquisition_quality_events` | Version quality, task/events | Report-only; it does not block scrape, import, enrichment, or publication. |

## Connector inventory

| Connector and raw fields | Current typed mapping | Raw retained / current gap | Recovery rule |
| --- | --- | --- | --- |
| Greenhouse API: `id`, `title`, `absolute_url`, `content`, `location`, `departments`, `offices`, `metadata`, `requisition_id`, `updated_at` | Job ID/title/detail URL/description/location; department/team/office/location collection/requisition; source ATS | `source_raw_payload` retains every API key. `absolute_url` is a job detail page, not an application URL. `updated_at` is an update timestamp, not a posting timestamp. | Preserve `updated_at` as `source_updated_at`; use an explicit source publication field only when supplied. Employer-page Apply links may resolve to a direct destination. |
| Lever API: `id`, `text`, `hostedUrl`, `applyUrl`, `descriptionPlain`, `description`, `categories`, `salaryRange`, `createdAt`, optional update/publication/status fields | Job ID/title/detail URL/direct application URL/description; categories department/team/commitment/location; workplace/salary | `source_raw_payload` retains every API key. `createdAt` is ATS record creation and must not silently become posted time. Categories/custom keys need typed preservation. | Preserve `createdAt` as `source_created_at`; map explicit `postedAt`/`publishedAt` to source posting time and `updatedAt` to source update time. |
| Generic employer career site through ScrapeOps: rendered HTML, JSON-LD `JobPosting`, canonical link, title, hiring organization, `jobLocation`, `datePosted`, description markup, page links/forms | Title/company/location/detail URL/description/posting date; direct Apply links recovered from page HTML; company page/careers URL | The normalized manual record currently keeps description projections and selected fields. The HTML apply-link evidence must be promoted to a reusable destination resolver; raw source payload remains the escape hatch. | Inspect anchors, buttons, forms, JSON-LD, and canonical links. Accept only same official host or known ATS hosts; classify `/apply` as application and job pages as detail. |
| Manual LinkedIn job ingestion: LinkedIn job ID/title/company/location/description/applicant count/easy apply/posted text and any provider `apply_link` | Job identity/title/company/location/description/applicant/easy-apply/source link | LinkedIn/provider payload is retained by the manual record. An absent provider apply URL is unknown, not a LinkedIn URL presented as direct apply. | Keep LinkedIn detail URL separately; use a provider/employer destination only when the source explicitly provides one and it classifies as direct. |
| Job boards: Indeed, Bundesagentur für Arbeit, StepStone strategy outputs `job_id`, `title`, `company`, `location_raw`, `posted_text`, `description`, `snippet`, `link`, `apply_link`, keyword/city, collection time | Common job identity/title/company/location/description/detail/apply candidate | Raw board response is not yet uniformly wrapped as `source_raw_payload`; board-specific fields such as snippet, keyword, city, and collection time must remain available. | Normalize common fields, classify board links as portal/detail unless direct evidence exists, and retain board-specific raw fields. |
| Academic/company discovery: homepage, career candidates, sitemap/crawl/rendered HTML, locality and policy evidence | `careers_page`, source target URL, locality/policy observations, job detail candidates | Discovery evidence belongs to source/target provenance, not to the employer profile as invented facts. | Keep official employer URL and discovery evidence; only promote a career page after same-host validation. |
| Source configuration: canonical employer name, connector, ATS token, official hosts, target URL, policy and provider metadata | Target/source identity and allowed host set | Configuration is provenance, not scraped employer fact. | Use it to safely associate records and classify URLs; never expose the ATS label as the employer. |

## Fields available, typed, or pending

| Field family | Canonical fields | State today / required behavior |
| --- | --- | --- |
| Identity | `job_id`, `external_job_id`, `title`, `company`, `location_raw`, `location_collection`, `job_detail_url` | Supported. Same title with different external IDs remains distinct. |
| Application | `application_url`, `employer_application_url`, `ats_application_url`, `application_destination`, `application_method`, `apply_link` | Supported with conservative URL taxonomy. Detail/listing fallback is retained and warned, never mislabeled direct. |
| Description | Raw, sanitized HTML, plain text, decoding, section extraction | Supported; raw and derived representations are separate. |
| Organization | `department`, `team`, `office`, `categories`, `requisition_id`, `source_status` | Partially typed. `categories`, custom fields, and status need a stable metadata projection. |
| Work terms | `employment_type`, `commitment`, `workplace_arrangement`, `language`, `salary`, `location_collection` | Partially typed; unknown and unsupported-by-source must be distinct. |
| Time | `source_created_at`, `source_posted_at`, `source_updated_at`, `source_closed_at`, `source_reopened_at`, `first_seen_at`, `last_seen_at`, `last_verified_at`, `posted_age_hours` | Current code conflates some source times. Repair will separate source semantics and compute age at read time. |
| Structured intelligence | Responsibilities, requirements, skills, benefits, authorization, compensation, languages, seniority, workplace, employment, education, years | Deterministic extraction exists for several fields. It needs field-level observation provenance and explicit state. |
| Employer profile | Website, careers page, industry, size/headcount, headquarters, founded/stage/funding, logo, description, benefits, sponsorship | Official-source enrichment exists. Unknown records must use null provenance and null verification time. |
| Admin quality | Completeness denominator, source freshness, warnings, conflicts, redundant hashes, repair actions | Report-only quality exists. The denominator needs timestamp, employment, workplace, source-status, and availability semantics. |

## Explicitly not collected by this pipeline

Crunchbase, Apollo, LinkedIn private/member-only data, or any other external
company enrichment is outside this contract. Those sources are not needed to
repair acquisition and must not be used to turn a missing value into an
inferred value.

