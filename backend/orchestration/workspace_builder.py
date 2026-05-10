from __future__ import annotations

import re
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4
from urllib.parse import urlparse

from backend.capabilities.tailored_documents.rendering import (
    CV_COLOR_SCHEMES,
    CV_FONT_OPTIONS,
    CV_TEMPLATE_PRESETS,
)
from backend.capabilities.tailored_documents.modes import (
    AGGRESSIVE_CUSTOMIZATION_EXTRA_PROMPT_FIELD,
    AGGRESSIVE_CUSTOMIZATION_PROMPT_OVERRIDE_FIELD,
    DEFAULT_CV_GENERATION_MODE,
    LIGHT_CUSTOMIZATION_EXTRA_PROMPT_FIELD,
    LIGHT_CUSTOMIZATION_PROMPT_OVERRIDE_FIELD,
)
from backend.connectors.company_career_sites import (
    ACADEMIC_CAREER_SITE_FILES,
    REGULAR_COMPANY_SITE_FILES,
    load_discovered_company_site_entries,
)
from backend.domain.phase0_contracts import (
    DEFAULT_MULTI_PORTAL_IDS,
    JOB_FILTERING_MODE_BROADER,
    JOB_FILTERING_MODE_STRICT,
    normalize_job_filtering_mode,
    normalize_workspace_configuration_v2,
)
from backend.domain.models import JobSource, ProfileRef, PromptSetRef, StageDefinition, WorkflowTemplate, WorkspaceDefinition


FLOW_TAILORED_DOCUMENTS = "tailored_documents"
FLOW_REUSABLE_PACKAGES = "reusable_packages"

SOURCE_LINKEDIN_SEARCH = "linkedin_jobs"
SOURCE_CURATED_URLS = "curated_job_urls"
SOURCE_ACADEMIC_CAREER_SITES = "academic_career_sites"
SOURCE_COMPANY_CAREER_SITES = "company_career_sites"
SOURCE_MULTI_PORTAL = "job_board_collection"

MODULE_SCREENING = "screening_filter"
MODULE_PRIORITY = "priority_ranking"
MODULE_ROLE_CLASSIFICATION = "role_classification"
MODULE_REUSABLE_PROFILES = "reusable_profile_builder"
MODULE_TAILORED_DOCUMENTS = "tailored_document_generation"
MODULE_APPLICATION_PACKAGING = "application_packaging"

COUNTRY_OPTIONS = [
    {"value": "DE", "label": "Germany"},
    {"value": "GB", "label": "United Kingdom"},
    {"value": "NL", "label": "Netherlands"},
    {"value": "AT", "label": "Austria"},
    {"value": "CH", "label": "Switzerland"},
    {"value": "BE", "label": "Belgium"},
    {"value": "LU", "label": "Luxembourg"},
    {"value": "FR", "label": "France"},
    {"value": "ES", "label": "Spain"},
    {"value": "HK", "label": "Hong Kong"},
    {"value": "PL", "label": "Poland"},
    {"value": "SE", "label": "Sweden"},
    {"value": "TH", "label": "Thailand"},
]

COUNTRY_TO_LINKEDIN_GEO = {
    "DE": "101282230",
    "NL": "102890719",
    "AT": "103883259",
    "CH": "106693272",
    "BE": "100565514",
    "LU": "104042105",
    "FR": "105015875",
    "ES": "105646813",
    "PL": "105072130",
    "SE": "105117694",
}

COUNTRY_TO_SOURCE_CITIES = {
    "DE": ["Berlin", "Munich", "Hamburg", "Frankfurt", "Cologne"],
    "GB": ["London", "Manchester", "Birmingham", "Leeds"],
    "NL": ["Amsterdam", "Rotterdam", "Utrecht"],
    "AT": ["Vienna", "Graz", "Linz"],
    "CH": ["Zurich", "Basel", "Geneva"],
    "BE": ["Brussels", "Antwerp", "Ghent"],
    "LU": ["Luxembourg"],
    "FR": ["Paris", "Lyon", "Marseille"],
    "ES": ["Madrid", "Barcelona", "Valencia"],
    "HK": ["Hong Kong"],
    "PL": ["Warsaw", "Krakow", "Wroclaw"],
    "SE": ["Stockholm", "Gothenburg", "Malmo"],
    "TH": ["Bangkok", "Chiang Mai", "Phuket"],
}

COUNTRY_LABEL_BY_CODE = {item["value"]: item["label"] for item in COUNTRY_OPTIONS}

PORTAL_OPTION_DEFINITIONS = [
    {
        "value": "indeed",
        "label": "Indeed",
        "category": "generalist",
        "summary": "Largest global aggregator with easy-apply coverage across broad salaried roles.",
    },
    {
        "value": "linkedin",
        "label": "LinkedIn Jobs",
        "category": "generalist",
        "summary": "Networking-led search for white-collar roles from mid-level through senior hiring.",
    },
    {
        "value": "glassdoor",
        "label": "Glassdoor",
        "category": "generalist",
        "summary": "Job listings paired with company reviews and salary context.",
    },
    {
        "value": "ziprecruiter",
        "label": "ZipRecruiter",
        "category": "generalist",
        "summary": "Broad salaried-role distribution across a large partner-board network.",
    },
    {
        "value": "monster",
        "label": "Monster",
        "category": "generalist",
        "summary": "Long-running generalist board for corporate, technical, and mid-level hiring.",
    },
    {
        "value": "careerbuilder",
        "label": "CareerBuilder",
        "category": "generalist",
        "summary": "Large professional hiring board for full-time salaried roles.",
    },
    {
        "value": "careerjet",
        "label": "Careerjet",
        "category": "regional",
        "summary": "Global aggregator that widens coverage with web-sourced salaried openings.",
    },
    {
        "value": "stepstone",
        "label": "StepStone",
        "category": "regional",
        "country_codes": ["DE", "GB"],
        "summary": "Premium skilled-role coverage for Germany and the United Kingdom.",
    },
    {
        "value": "reed",
        "label": "Reed.co.uk",
        "category": "regional",
        "country_codes": ["GB"],
        "summary": "High-volume UK hiring across dozens of salaried sectors.",
    },
    {
        "value": "totaljobs",
        "label": "Totaljobs",
        "category": "regional",
        "country_codes": ["GB"],
        "summary": "Broad UK professional-network job coverage.",
    },
    {
        "value": "jobsdb",
        "label": "JobsDB",
        "category": "regional",
        "country_codes": ["HK", "TH"],
        "summary": "Regional full-time board for Hong Kong and Thailand.",
    },
    {
        "value": "arbeitsagentur",
        "label": "Arbeitsagentur",
        "category": "regional",
        "country_codes": ["DE"],
        "summary": "Official German employment-service listings.",
    },
]

PORTAL_OPTION_BY_ID = {str(item["value"]): item for item in PORTAL_OPTION_DEFINITIONS}
BASE_MULTI_PORTAL_DEFAULT_IDS = ["indeed", "linkedin", "careerjet"]
COUNTRY_TO_RECOMMENDED_PORTALS = {
    "DE": ["stepstone", "arbeitsagentur"],
    "GB": ["stepstone", "reed", "totaljobs"],
    "HK": ["jobsdb"],
    "TH": ["jobsdb"],
}

USER_FACING_FIELD_IDS = {
    "workspace_cv_asset_id",
    "cv_generation_mode",
    "keywords",
    "country_codes",
    "cities",
    "target_roles",
    "job_filtering_mode",
    "time_posted_seconds",
    "experience_levels",
    "manual_url_seed_list",
    "academic_career_sites",
    "company_career_sites",
    "portals",
    "forbidden_title_keywords",
    "max_german_level",
    "french_special_char_threshold",
    "spanish_special_char_threshold",
    "low_applicant_threshold",
    "languages",
    "cv_template",
    "cv_color_scheme",
    "cv_font",
    "include_photo",
    "stage1_model",
    "stage1_extra_prompt",
    "stage1_prompt_override",
    "stage4_model",
    "stage4_fallback_model",
    LIGHT_CUSTOMIZATION_EXTRA_PROMPT_FIELD,
    LIGHT_CUSTOMIZATION_PROMPT_OVERRIDE_FIELD,
    AGGRESSIVE_CUSTOMIZATION_EXTRA_PROMPT_FIELD,
    AGGRESSIVE_CUSTOMIZATION_PROMPT_OVERRIDE_FIELD,
    "stage4_max_jobs",
    "stage4_extra_prompt",
    "stage4_prompt_override",
}

FIELD_SECTION_BY_ID = {
    "workspace_cv_asset_id": "cv_binding",
    "cv_generation_mode": "advanced",
    "keywords": "targeting",
    "country_codes": "targeting",
    "cities": "targeting",
    "target_roles": "targeting",
    "job_filtering_mode": "filters",
    "time_posted_seconds": "filters",
    "experience_levels": "filters",
    "manual_url_seed_list": "sources",
    "academic_career_sites": "sources",
    "company_career_sites": "sources",
    "portals": "sources",
    "forbidden_title_keywords": "filters",
    "max_german_level": "filters",
    "french_special_char_threshold": "filters",
    "spanish_special_char_threshold": "filters",
    "low_applicant_threshold": "filters",
    "languages": "filters",
    "cv_template": "documents",
    "cv_color_scheme": "documents",
    "cv_font": "documents",
    "include_photo": "documents",
    "stage1_model": "prompt_preferences",
    "stage1_extra_prompt": "prompt_preferences",
    "stage1_prompt_override": "prompt_preferences",
    "stage4_model": "prompt_preferences",
    "stage4_fallback_model": "prompt_preferences",
    LIGHT_CUSTOMIZATION_EXTRA_PROMPT_FIELD: "prompt_preferences",
    LIGHT_CUSTOMIZATION_PROMPT_OVERRIDE_FIELD: "prompt_preferences",
    AGGRESSIVE_CUSTOMIZATION_EXTRA_PROMPT_FIELD: "prompt_preferences",
    AGGRESSIVE_CUSTOMIZATION_PROMPT_OVERRIDE_FIELD: "prompt_preferences",
    "stage4_max_jobs": "prompt_preferences",
    "stage4_extra_prompt": "prompt_preferences",
    "stage4_prompt_override": "prompt_preferences",
}

FIELD_SORT_ORDER = {
    "workspace_cv_asset_id": 10,
    "cv_generation_mode": 15,
    "keywords": 20,
    "target_roles": 25,
    "country_codes": 30,
    "cities": 32,
    "job_filtering_mode": 35,
    "time_posted_seconds": 40,
    "experience_levels": 50,
    "forbidden_title_keywords": 60,
    "max_german_level": 70,
    "french_special_char_threshold": 80,
    "spanish_special_char_threshold": 90,
    "low_applicant_threshold": 100,
    "languages": 110,
    "manual_url_seed_list": 120,
    "academic_career_sites": 130,
    "company_career_sites": 140,
    "portals": 150,
    "cv_template": 160,
    "cv_color_scheme": 170,
    "cv_font": 180,
    "include_photo": 190,
    "stage1_model": 200,
    "stage1_extra_prompt": 210,
    "stage1_prompt_override": 220,
    "stage4_model": 230,
    "stage4_fallback_model": 240,
    LIGHT_CUSTOMIZATION_EXTRA_PROMPT_FIELD: 245,
    LIGHT_CUSTOMIZATION_PROMPT_OVERRIDE_FIELD: 246,
    AGGRESSIVE_CUSTOMIZATION_EXTRA_PROMPT_FIELD: 247,
    AGGRESSIVE_CUSTOMIZATION_PROMPT_OVERRIDE_FIELD: 248,
    "stage4_max_jobs": 250,
    "stage4_extra_prompt": 260,
    "stage4_prompt_override": 270,
}

BUILDER_SECTIONS = [
    {
        "id": "cv_binding",
        "title": "Baseline CV",
        "description": "Choose the CV this workspace should use as its baseline before any job-specific tailoring happens.",
    },
    {
        "id": "targeting",
        "title": "Targeting",
        "description": "Set the target roles, keywords, and countries that define what this workspace should pursue.",
    },
    {
        "id": "sources",
        "title": "Source Setup",
        "description": "Choose one recurring source type for this workspace and configure it inline.",
    },
    {
        "id": "filters",
        "title": "Filters",
        "description": "Control recency, seniority, language, and filtering behavior for this workspace.",
    },
    {
        "id": "documents",
        "title": "Document Style",
        "description": "Set the workspace-specific CV design choices used when this workspace generates tailored application documents.",
    },
    {
        "id": "prompt_preferences",
        "title": "Prompt Overrides",
        "description": "Review stage-specific prompt behavior and only override it deliberately.",
        "frontend_visible": False,
    },
]


@dataclass(frozen=True, slots=True)
class BuilderCatalog:
    flows: list[dict]
    sources: list[dict]
    modules: list[dict]
    configuration_fields: list[dict]
    starter_profiles: list[dict]
    starter_prompt_families: list[dict]
    builder_sections: list[dict]

    def to_dict(self) -> dict:
        return {
            "flows": list(self.flows),
            "sources": list(self.sources),
            "modules": list(self.modules),
            "configuration_fields": list(self.configuration_fields),
            "starter_profiles": list(self.starter_profiles),
            "starter_prompt_families": list(self.starter_prompt_families),
            "builder_sections": list(self.builder_sections),
        }


def _boolean_options(true_label: str, false_label: str) -> list[dict[str, Any]]:
    return [
        {"value": True, "label": true_label},
        {"value": False, "label": false_label},
    ]


def _document_template_options() -> list[dict[str, str]]:
    return [{"value": item["id"], "label": item["label"]} for item in CV_TEMPLATE_PRESETS.values()]


def _document_color_scheme_options() -> list[dict[str, str]]:
    return [{"value": item["id"], "label": item["label"]} for item in CV_COLOR_SCHEMES.values()]


def _document_font_options() -> list[dict[str, str]]:
    return [{"value": item["id"], "label": item["label"]} for item in CV_FONT_OPTIONS]


def _configuration_fields() -> list[dict]:
    return [
        {
            "id": "workspace_cv_asset_id",
            "label": "Workspace CV",
            "description": "Select the baseline CV for this workspace. Upload a new one if this search needs a different baseline.",
            "type": "asset_select",
            "compatible_flows": [FLOW_TAILORED_DOCUMENTS],
            "dynamic_source": "workspace_cv_assets",
            "placeholder": "Choose an uploaded CV",
        },
        {
            "id": "cv_generation_mode",
            "label": "CV Generation Mode",
            "description": "Choose whether this workspace should reuse the baseline workspace CV or generate a tailored variant per accepted job.",
            "type": "select",
            "compatible_flows": [FLOW_TAILORED_DOCUMENTS],
            "options": [
                {"value": "standard_cv", "label": "Standard CV"},
                {"value": "light_customization", "label": "Light Customization"},
                {"value": "aggressive_customization", "label": "Aggressive Customization"},
            ],
            "default": DEFAULT_CV_GENERATION_MODE,
            "frontend_visible": False,
        },
        {
            "id": "keywords",
            "label": "Target Keywords",
            "description": "Keywords the system should search for when discovering jobs.",
            "type": "tag_list",
            "compatible_flows": [FLOW_TAILORED_DOCUMENTS, FLOW_REUSABLE_PACKAGES],
            "placeholder": "analyst, consultant, product manager",
        },
        {
            "id": "country_codes",
            "label": "Target Country",
            "description": "Choose the country this workspace should target.",
            "type": "multi_select",
            "compatible_flows": [FLOW_TAILORED_DOCUMENTS],
            "options": list(COUNTRY_OPTIONS),
        },
        {
            "id": "target_roles",
            "label": "Target Roles",
            "description": "Add the roles this workspace should target. They shape search keywords and document emphasis.",
            "type": "multi_select",
            "compatible_flows": [FLOW_TAILORED_DOCUMENTS, FLOW_REUSABLE_PACKAGES],
            "options": [
                {"value": "Product Manager", "label": "Product Manager"},
                {"value": "Business Analyst", "label": "Business Analyst"},
                {"value": "Project Manager", "label": "Project Manager"},
                {"value": "Consultant", "label": "Consultant"},
                {"value": "Product Designer", "label": "Product Designer"},
                {"value": "Frontend Engineer", "label": "Frontend Engineer"},
                {"value": "Data Analyst", "label": "Data Analyst"},
            ],
        },
        {
            "id": "job_filtering_mode",
            "label": "Job Filtering",
            "description": "Choose whether Stage 1 should stay strict to the saved targets or admit broader adjacent role matches.",
            "type": "select",
            "compatible_flows": [FLOW_TAILORED_DOCUMENTS],
            "options": [
                {"value": JOB_FILTERING_MODE_STRICT, "label": JOB_FILTERING_MODE_STRICT},
                {"value": JOB_FILTERING_MODE_BROADER, "label": JOB_FILTERING_MODE_BROADER},
            ],
            "default": JOB_FILTERING_MODE_BROADER,
            "frontend_visible": False,
        },
        {
            "id": "geo_id",
            "label": "LinkedIn Geo ID",
            "description": "LinkedIn geographic target used for listing discovery.",
            "type": "text",
            "compatible_flows": [FLOW_TAILORED_DOCUMENTS],
            "source_ids": [SOURCE_LINKEDIN_SEARCH],
            "placeholder": "101282230",
        },
        {
            "id": "time_posted_seconds",
            "label": "Posting Age Window",
            "description": "How recent a listing must be before it is included.",
            "type": "select",
            "compatible_flows": [FLOW_TAILORED_DOCUMENTS],
            "source_ids": [SOURCE_LINKEDIN_SEARCH],
            "options": [
                {"value": 86400, "label": "Last 24 hours"},
                {"value": 172800, "label": "Last 2 days"},
                {"value": 604800, "label": "Last 7 days"},
                {"value": 1209600, "label": "Last 14 days"},
                {"value": 2592000, "label": "Last 30 days"},
            ],
        },
        {
            "id": "experience_levels",
            "label": "Experience Levels",
            "description": "LinkedIn experience buckets to include in the search.",
            "type": "multi_select",
            "compatible_flows": [FLOW_TAILORED_DOCUMENTS],
            "source_ids": [SOURCE_LINKEDIN_SEARCH],
            "options": [
                {"value": 1, "label": "Internship"},
                {"value": 2, "label": "Entry Level"},
                {"value": 3, "label": "Associate"},
                {"value": 4, "label": "Mid-Senior"},
            ],
        },
        {
            "id": "linkedin_max_pages",
            "label": "LinkedIn Pages Per Keyword",
            "description": "Maximum pages to fetch for each LinkedIn keyword search.",
            "type": "number",
            "compatible_flows": [FLOW_TAILORED_DOCUMENTS],
            "source_ids": [SOURCE_LINKEDIN_SEARCH],
            "placeholder": "5",
        },
        {
            "id": "max_enrich_jobs",
            "label": "Max Jobs To Enrich",
            "description": "Cap how many approved LinkedIn jobs get full detail enrichment.",
            "type": "number",
            "compatible_flows": [FLOW_TAILORED_DOCUMENTS],
            "source_ids": [SOURCE_LINKEDIN_SEARCH],
            "placeholder": "50",
        },
        {
            "id": "ai_batch_size",
            "label": "Stage 1 AI Batch Size",
            "description": "How many job titles to send in one Stage 1 AI filtering request.",
            "type": "number",
            "compatible_flows": [FLOW_TAILORED_DOCUMENTS],
            "source_ids": [SOURCE_LINKEDIN_SEARCH],
            "placeholder": "30",
        },
        {
            "id": "reuse_scrape_snapshot",
            "label": "Reuse LinkedIn Snapshot",
            "description": "Skip a fresh LinkedIn scrape and reuse the saved Stage 1 snapshot.",
            "type": "boolean",
            "compatible_flows": [FLOW_TAILORED_DOCUMENTS],
            "source_ids": [SOURCE_LINKEDIN_SEARCH],
            "options": _boolean_options("Reuse saved snapshot", "Always scrape fresh"),
            "default": False,
        },
        {
            "id": "page_fetch_sleep_seconds",
            "label": "LinkedIn Page Fetch Delay (seconds)",
            "description": "Optional delay between paginated LinkedIn requests.",
            "type": "float",
            "compatible_flows": [FLOW_TAILORED_DOCUMENTS],
            "source_ids": [SOURCE_LINKEDIN_SEARCH],
            "placeholder": "1.0",
        },
        {
            "id": "use_proxy_fallback",
            "label": "Use Proxy Fallback",
            "description": "Allow proxy fallback when direct job detail enrichment fails.",
            "type": "boolean",
            "compatible_flows": [FLOW_TAILORED_DOCUMENTS],
            "source_ids": [
                SOURCE_LINKEDIN_SEARCH,
                SOURCE_CURATED_URLS,
                SOURCE_ACADEMIC_CAREER_SITES,
                SOURCE_COMPANY_CAREER_SITES,
            ],
            "options": _boolean_options("Enable fallback", "Disable fallback"),
            "default": False,
        },
        {
            "id": "manual_url_seed_list",
            "label": "Pasted Job URLs",
            "description": "Paste one job URL per line so this workspace can ingest curated postings without editing any files.",
            "type": "url_list",
            "compatible_flows": [FLOW_TAILORED_DOCUMENTS],
            "source_ids": [SOURCE_CURATED_URLS],
            "placeholder": "https://company.example/jobs/123",
        },
        {
            "id": "manual_request_timeout_seconds",
            "label": "Manual URL Timeout (seconds)",
            "description": "HTTP timeout when loading curated job URLs.",
            "type": "number",
            "compatible_flows": [FLOW_TAILORED_DOCUMENTS],
            "source_ids": [SOURCE_CURATED_URLS],
            "placeholder": "45",
        },
        {
            "id": "academic_career_sites",
            "label": "Academic Websites",
            "description": "Use the saved university and department website list for academic roles, and add up to 50 university, chair, department, institute, or research portal URLs of your own.",
            "type": "company_site_list",
            "compatible_flows": [FLOW_TAILORED_DOCUMENTS],
            "source_ids": [SOURCE_ACADEMIC_CAREER_SITES],
            "placeholder": "https://university.example/careers",
        },
        {
            "id": "academic_site_max_jobs_per_site",
            "label": "Academic Jobs Per Site",
            "description": "Maximum job links to follow from each academic site during one run.",
            "type": "number",
            "compatible_flows": [FLOW_TAILORED_DOCUMENTS],
            "source_ids": [SOURCE_ACADEMIC_CAREER_SITES],
            "placeholder": "10",
        },
        {
            "id": "academic_site_request_timeout_seconds",
            "label": "Academic Site Timeout (seconds)",
            "description": "How long the workspace waits for each academic website to respond.",
            "type": "number",
            "compatible_flows": [FLOW_TAILORED_DOCUMENTS],
            "source_ids": [SOURCE_ACADEMIC_CAREER_SITES],
            "placeholder": "30",
        },
        {
            "id": "company_career_sites",
            "label": "Company Websites",
            "description": "Search major company career sites worldwide, and add up to 50 company or careers URLs of your own. Separate each URL with Enter or a comma.",
            "type": "company_site_list",
            "compatible_flows": [FLOW_TAILORED_DOCUMENTS],
            "source_ids": [SOURCE_COMPANY_CAREER_SITES],
            "placeholder": "https://careers.acme.com/jobs",
        },
        {
            "id": "company_site_max_jobs_per_site",
            "label": "Company Jobs Per Site",
            "description": "Maximum job links to follow from each company career site during one run.",
            "type": "number",
            "compatible_flows": [FLOW_TAILORED_DOCUMENTS],
            "source_ids": [SOURCE_COMPANY_CAREER_SITES],
            "placeholder": "10",
        },
        {
            "id": "company_site_request_timeout_seconds",
            "label": "Company Site Timeout (seconds)",
            "description": "How long the workspace waits for each company website to respond.",
            "type": "number",
            "compatible_flows": [FLOW_TAILORED_DOCUMENTS],
            "source_ids": [SOURCE_COMPANY_CAREER_SITES],
            "placeholder": "30",
        },
        {
            "id": "forbidden_title_keywords",
            "label": "Forbidden Title Keywords",
            "description": "Jobs whose title contains any of these words will be excluded before AI screening.",
            "type": "tag_list",
            "compatible_flows": [FLOW_TAILORED_DOCUMENTS],
            "source_ids": [
                SOURCE_LINKEDIN_SEARCH,
                SOURCE_CURATED_URLS,
                SOURCE_ACADEMIC_CAREER_SITES,
                SOURCE_COMPANY_CAREER_SITES,
            ],
            "placeholder": "senior, director, intern, werkstudent",
        },
        {
            "id": "max_german_level",
            "label": "Max German Language Level",
            "description": "Reject jobs that require German above this level (e.g. B2 rejects C1/C2 jobs).",
            "type": "select",
            "compatible_flows": [FLOW_TAILORED_DOCUMENTS],
            "source_ids": [
                SOURCE_LINKEDIN_SEARCH,
                SOURCE_CURATED_URLS,
                SOURCE_ACADEMIC_CAREER_SITES,
                SOURCE_COMPANY_CAREER_SITES,
            ],
            "options": [
                {"value": "A1", "label": "A1 — Beginner"},
                {"value": "A2", "label": "A2 — Elementary"},
                {"value": "B1", "label": "B1 — Intermediate"},
                {"value": "B2", "label": "B2 — Upper Intermediate"},
                {"value": "C1", "label": "C1 — Advanced"},
                {"value": "C2", "label": "C2 — Proficient"},
                {"value": "any", "label": "Any (no language filter)"},
            ],
            "default": "B2",
        },
        {
            "id": "french_special_char_threshold",
            "label": "Reject French-language Jobs",
            "description": "Enable or disable French-language rejection in local language filtering.",
            "type": "select",
            "compatible_flows": [FLOW_TAILORED_DOCUMENTS],
            "source_ids": [
                SOURCE_LINKEDIN_SEARCH,
                SOURCE_CURATED_URLS,
                SOURCE_ACADEMIC_CAREER_SITES,
                SOURCE_COMPANY_CAREER_SITES,
            ],
            "options": [
                {"value": 0, "label": "Yes - exclude French jobs"},
                {"value": 9999, "label": "No - allow French jobs"},
            ],
            "default": 0,
        },
        {
            "id": "spanish_special_char_threshold",
            "label": "Reject Spanish-language Jobs",
            "description": "Enable or disable Spanish-language rejection in local language filtering.",
            "type": "select",
            "compatible_flows": [FLOW_TAILORED_DOCUMENTS],
            "source_ids": [
                SOURCE_LINKEDIN_SEARCH,
                SOURCE_CURATED_URLS,
                SOURCE_ACADEMIC_CAREER_SITES,
                SOURCE_COMPANY_CAREER_SITES,
            ],
            "options": [
                {"value": 0, "label": "Yes - exclude Spanish jobs"},
                {"value": 9999, "label": "No - allow Spanish jobs"},
            ],
            "default": 0,
        },
        {
            "id": "low_applicant_threshold",
            "label": "Priority Applicant Threshold",
            "description": "Listings below this applicant count get boosted during prioritization.",
            "type": "number",
            "compatible_flows": [FLOW_TAILORED_DOCUMENTS],
            "source_ids": [SOURCE_LINKEDIN_SEARCH],
            "placeholder": "80",
        },
        {
            "id": "stage4_max_jobs",
            "label": "Max Jobs To Generate",
            "description": "Optional cap on how many jobs should reach document generation in one run.",
            "type": "number",
            "compatible_flows": [FLOW_TAILORED_DOCUMENTS],
            "source_ids": [
                SOURCE_LINKEDIN_SEARCH,
                SOURCE_CURATED_URLS,
                SOURCE_ACADEMIC_CAREER_SITES,
                SOURCE_COMPANY_CAREER_SITES,
            ],
            "placeholder": "25",
        },
        {
            "id": "dedupe_against_tracker",
            "label": "Deduplicate Against Tracker",
            "description": "Remove jobs that already exist in the tracker output before continuing.",
            "type": "boolean",
            "compatible_flows": [FLOW_TAILORED_DOCUMENTS],
            "options": _boolean_options("Drop tracked duplicates", "Keep tracked duplicates"),
            "default": True,
        },
        {
            "id": "candidate_name",
            "label": "Candidate Name Override",
            "description": "Optional workspace-specific candidate name used in generated assets.",
            "type": "text",
            "compatible_flows": [FLOW_TAILORED_DOCUMENTS, FLOW_REUSABLE_PACKAGES],
            "placeholder": "Ahmed Kaddah",
        },
        {
            "id": "candidate_email",
            "label": "Candidate Email Override",
            "description": "Optional workspace-specific candidate email used in generated assets.",
            "type": "text",
            "compatible_flows": [FLOW_TAILORED_DOCUMENTS, FLOW_REUSABLE_PACKAGES],
            "placeholder": "name@example.com",
        },
        {
            "id": "languages",
            "label": "Language Lines",
            "description": "Language items used in tailored CVs and reusable role profiles.",
            "type": "tag_list",
            "compatible_flows": [FLOW_TAILORED_DOCUMENTS, FLOW_REUSABLE_PACKAGES],
            "placeholder": "English - C1, German - B1/B2",
            "frontend_visible": False,
        },
        {
            "id": "cv_template",
            "label": "CV Template",
            "description": "Document layout preset for this workspace's tailored CV generation.",
            "type": "select",
            "compatible_flows": [FLOW_TAILORED_DOCUMENTS],
            "options": _document_template_options(),
        },
        {
            "id": "cv_color_scheme",
            "label": "CV Color Scheme",
            "description": "Color palette used for this workspace's tailored CV generation.",
            "type": "select",
            "compatible_flows": [FLOW_TAILORED_DOCUMENTS],
            "options": _document_color_scheme_options(),
        },
        {
            "id": "cv_font",
            "label": "CV Font",
            "description": "Font family used for this workspace's tailored CV generation.",
            "type": "select",
            "compatible_flows": [FLOW_TAILORED_DOCUMENTS],
            "options": _document_font_options(),
        },
        {
            "id": "include_photo",
            "label": "Include Profile Photo",
            "description": "Use the configured profile image in this workspace's tailored CV exports.",
            "type": "boolean",
            "compatible_flows": [FLOW_TAILORED_DOCUMENTS],
            "options": _boolean_options("Include photo", "No photo"),
            "default": True,
        },
        {
            "id": "stage1_model",
            "label": "Stage 1 AI Model",
            "description": "Model name for LinkedIn title filtering.",
            "type": "text",
            "compatible_flows": [FLOW_TAILORED_DOCUMENTS],
            "source_ids": [SOURCE_LINKEDIN_SEARCH],
            "placeholder": "deepseek-chat",
        },
        {
            "id": "stage1_extra_prompt",
            "label": "Stage 1 Extra Prompt",
            "description": "Extra instructions appended to the Stage 1 AI filtering prompt.",
            "type": "textarea",
            "compatible_flows": [FLOW_TAILORED_DOCUMENTS],
            "source_ids": [SOURCE_LINKEDIN_SEARCH],
            "placeholder": "Favor hybrid roles and deprioritize internships.",
        },
        {
            "id": "stage1_prompt_override",
            "label": "Stage 1 Prompt Override",
            "description": "Full prompt override for LinkedIn title filtering.",
            "type": "textarea",
            "compatible_flows": [FLOW_TAILORED_DOCUMENTS],
            "source_ids": [SOURCE_LINKEDIN_SEARCH],
            "placeholder": "Custom full prompt with placeholders.",
        },
        {
            "id": "stage4_model",
            "label": "Stage 4 Primary Model",
            "description": "Primary model used for tailored document generation.",
            "type": "text",
            "compatible_flows": [FLOW_TAILORED_DOCUMENTS],
            "placeholder": "deepseek-chat",
        },
        {
            "id": "stage4_fallback_model",
            "label": "Stage 4 Fallback Model",
            "description": "Fallback model used when the primary model fails.",
            "type": "text",
            "compatible_flows": [FLOW_TAILORED_DOCUMENTS],
            "placeholder": "gemini-2.5-flash",
        },
        {
            "id": LIGHT_CUSTOMIZATION_EXTRA_PROMPT_FIELD,
            "label": "Light Mode Extra Instructions",
            "description": "Extra instructions appended only when Light Customization is selected.",
            "type": "textarea",
            "compatible_flows": [FLOW_TAILORED_DOCUMENTS],
            "placeholder": "Emphasize the strongest domain-fit keywords in the summary and skills only.",
            "frontend_visible": False,
        },
        {
            "id": LIGHT_CUSTOMIZATION_PROMPT_OVERRIDE_FIELD,
            "label": "Light Mode Prompt Override",
            "description": "Full prompt override used only when Light Customization is selected.",
            "type": "textarea",
            "compatible_flows": [FLOW_TAILORED_DOCUMENTS],
            "placeholder": "Custom light-mode prompt with placeholders.",
            "frontend_visible": False,
        },
        {
            "id": AGGRESSIVE_CUSTOMIZATION_EXTRA_PROMPT_FIELD,
            "label": "Aggressive Mode Extra Instructions",
            "description": "Extra instructions appended only when Aggressive Customization is selected.",
            "type": "textarea",
            "compatible_flows": [FLOW_TAILORED_DOCUMENTS],
            "placeholder": "Push harder on role-specific bullet wording and ATS phrasing.",
            "frontend_visible": False,
        },
        {
            "id": AGGRESSIVE_CUSTOMIZATION_PROMPT_OVERRIDE_FIELD,
            "label": "Aggressive Mode Prompt Override",
            "description": "Full prompt override used only when Aggressive Customization is selected.",
            "type": "textarea",
            "compatible_flows": [FLOW_TAILORED_DOCUMENTS],
            "placeholder": "Custom aggressive-mode prompt with placeholders.",
            "frontend_visible": False,
        },
        {
            "id": "stage4_extra_prompt",
            "label": "Stage 4 Extra Prompt",
            "description": "Extra instructions appended to the tailored document generation prompt.",
            "type": "textarea",
            "compatible_flows": [FLOW_TAILORED_DOCUMENTS],
            "placeholder": "Highlight cross-functional delivery and process design experience.",
        },
        {
            "id": "stage4_prompt_override",
            "label": "Stage 4 Prompt Override",
            "description": "Full prompt override for tailored document generation.",
            "type": "textarea",
            "compatible_flows": [FLOW_TAILORED_DOCUMENTS],
            "placeholder": "Custom full prompt with placeholders.",
        },
        {
            "id": "stage4_sleep_seconds",
            "label": "Stage 4 Delay (seconds)",
            "description": "Delay between tailored document generations.",
            "type": "float",
            "compatible_flows": [FLOW_TAILORED_DOCUMENTS],
            "placeholder": "4.0",
        },
        {
            "id": "stage4_retries",
            "label": "Stage 4 Retries",
            "description": "Retry count for tailored document generation failures.",
            "type": "number",
            "compatible_flows": [FLOW_TAILORED_DOCUMENTS],
            "placeholder": "3",
        },
        {
            "id": "stage4_retry_sleep",
            "label": "Stage 4 Retry Delay (seconds)",
            "description": "Delay between Stage 4 retry attempts.",
            "type": "float",
            "compatible_flows": [FLOW_TAILORED_DOCUMENTS],
            "placeholder": "3.0",
        },
        {
            "id": "force_regenerate",
            "label": "Force Regenerate Documents",
            "description": "Ignore the Stage 4 checkpoint and rebuild all selected tailored documents.",
            "type": "boolean",
            "compatible_flows": [FLOW_TAILORED_DOCUMENTS],
            "options": _boolean_options("Always regenerate", "Reuse checkpoint when possible"),
            "default": False,
        },
        {
            "id": "excel_mode",
            "label": "Tracker Export Mode",
            "description": "Create a new sheet per run or append rows into one sheet.",
            "type": "select",
            "compatible_flows": [FLOW_TAILORED_DOCUMENTS],
            "options": [
                {"value": "new-sheet", "label": "Create a new sheet per run"},
                {"value": "append-rows", "label": "Append rows into one sheet"},
            ],
        },
        {
            "id": "sheet_name",
            "label": "Tracker Sheet Name",
            "description": "Optional custom sheet name for the tracker export.",
            "type": "text",
            "compatible_flows": [FLOW_TAILORED_DOCUMENTS],
            "placeholder": "jobs",
        },
        {
            "id": "cities",
            "label": "Target City",
            "description": "",
            "type": "tag_list",
            "compatible_flows": [FLOW_TAILORED_DOCUMENTS, FLOW_REUSABLE_PACKAGES],
            "placeholder": "Berlin",
        },
        {
            "id": "portals",
            "label": "Job Boards",
            "description": "Choose the job boards to search. Global boards are always available. Regional boards appear after you select your target country.",
            "type": "multi_select",
            "compatible_flows": [FLOW_TAILORED_DOCUMENTS, FLOW_REUSABLE_PACKAGES],
            "source_ids": [SOURCE_MULTI_PORTAL],
            "options": list(PORTAL_OPTION_DEFINITIONS),
        },
        {
            "id": "max_pages",
            "label": "Pages Per Source",
            "description": "Maximum pages each job-board connector should scan.",
            "type": "number",
            "compatible_flows": [FLOW_REUSABLE_PACKAGES],
            "source_ids": [SOURCE_MULTI_PORTAL],
            "placeholder": "2",
        },
        {
            "id": "radius_km",
            "label": "Search Radius (km)",
            "description": "Distance around each target city when collecting reusable package jobs.",
            "type": "number",
            "compatible_flows": [FLOW_REUSABLE_PACKAGES],
            "source_ids": [SOURCE_MULTI_PORTAL],
            "placeholder": "35",
        },
        {
            "id": "posted_within_days",
            "label": "Posted Within Days",
            "description": "Age limit for job-board results.",
            "type": "number",
            "compatible_flows": [FLOW_REUSABLE_PACKAGES],
            "source_ids": [SOURCE_MULTI_PORTAL],
            "placeholder": "14",
        },
        {
            "id": "max_jobs_total",
            "label": "Max Jobs Collected",
            "description": "Hard cap on how many collected jobs the workflow should retain.",
            "type": "number",
            "compatible_flows": [FLOW_REUSABLE_PACKAGES],
            "source_ids": [SOURCE_MULTI_PORTAL],
            "placeholder": "1200",
        },
        {
            "id": "timeout_seconds",
            "label": "Portal Request Timeout (seconds)",
            "description": "HTTP timeout for reusable-package source collection.",
            "type": "number",
            "compatible_flows": [FLOW_REUSABLE_PACKAGES],
            "source_ids": [SOURCE_MULTI_PORTAL],
            "placeholder": "25",
        },
        {
            "id": "arbeitsagentur_detail_fetch_limit",
            "label": "Arbeitsagentur Detail Fetch Limit",
            "description": "Cap on detail pages fetched from Arbeitsagentur during one run.",
            "type": "number",
            "compatible_flows": [FLOW_REUSABLE_PACKAGES],
            "source_ids": [SOURCE_MULTI_PORTAL],
            "placeholder": "20",
        },
        {
            "id": "reuse_snapshot",
            "label": "Reuse Portal Snapshot",
            "description": "Skip fresh job-board scraping and reuse the saved snapshot.",
            "type": "boolean",
            "compatible_flows": [FLOW_REUSABLE_PACKAGES],
            "source_ids": [SOURCE_MULTI_PORTAL],
            "options": _boolean_options("Reuse saved snapshot", "Always scrape fresh"),
            "default": False,
        },
        {
            "id": "exclude_driver_license_required",
            "label": "Reject Driver's License Requirements",
            "description": "Exclude jobs that clearly require a driver's license.",
            "type": "boolean",
            "compatible_flows": [FLOW_REUSABLE_PACKAGES],
            "options": _boolean_options("Reject those jobs", "Allow those jobs"),
            "default": True,
        },
        {
            "id": "exclude_special_training_required",
            "label": "Reject Special Training Requirements",
            "description": "Exclude jobs that require certifications or vocational training.",
            "type": "boolean",
            "compatible_flows": [FLOW_REUSABLE_PACKAGES],
            "options": _boolean_options("Reject those jobs", "Allow those jobs"),
            "default": True,
        },
        {
            "id": "model",
            "label": "Role Classifier Model",
            "description": "Model used to classify reusable-package role clusters.",
            "type": "text",
            "compatible_flows": [FLOW_REUSABLE_PACKAGES],
            "placeholder": "deepseek-chat",
        },
        {
            "id": "batch_size",
            "label": "Role Classifier Batch Size",
            "description": "How many role clusters to classify in one AI request.",
            "type": "number",
            "compatible_flows": [FLOW_REUSABLE_PACKAGES],
            "placeholder": "50",
        },
        {
            "id": "retries",
            "label": "Role Classifier Retries",
            "description": "Retry count for reusable role classification batches.",
            "type": "number",
            "compatible_flows": [FLOW_REUSABLE_PACKAGES],
            "placeholder": "3",
        },
        {
            "id": "retry_sleep_seconds",
            "label": "Role Classifier Retry Delay (seconds)",
            "description": "Delay between reusable role classification retries.",
            "type": "float",
            "compatible_flows": [FLOW_REUSABLE_PACKAGES],
            "placeholder": "2.0",
        },
        {
            "id": "extra_prompt",
            "label": "Role Classifier Extra Prompt",
            "description": "Extra instructions appended to the reusable role classification prompt.",
            "type": "textarea",
            "compatible_flows": [FLOW_REUSABLE_PACKAGES],
            "placeholder": "Prefer warehouse and logistics when titles are ambiguous.",
        },
        {
            "id": "prompt_override",
            "label": "Role Classifier Prompt Override",
            "description": "Full prompt override for reusable role classification.",
            "type": "textarea",
            "compatible_flows": [FLOW_REUSABLE_PACKAGES],
            "placeholder": "Custom full prompt with placeholders.",
        },
        {
            "id": "candidate_phone",
            "label": "Candidate Phone",
            "description": "Phone number inserted into reusable package email drafts.",
            "type": "text",
            "compatible_flows": [FLOW_REUSABLE_PACKAGES],
            "placeholder": "+49 ...",
        },
        {
            "id": "candidate_location",
            "label": "Candidate Location",
            "description": "Location line used in reusable role CVs.",
            "type": "text",
            "compatible_flows": [FLOW_REUSABLE_PACKAGES],
            "placeholder": "91052 Erlangen / 90402 Nuremberg",
        },
        {
            "id": "availability",
            "label": "Availability",
            "description": "Availability line used in reusable role CVs and package emails.",
            "type": "text",
            "compatible_flows": [FLOW_REUSABLE_PACKAGES],
            "placeholder": "Ab sofort | Vollzeit | Mini-job",
        },
    ]


def _normalize_country_codes(raw_value: Any) -> list[str]:
    if isinstance(raw_value, str):
        values = [item.strip().upper() for item in raw_value.replace("\n", ",").split(",") if item.strip()]
    elif isinstance(raw_value, (list, tuple, set)):
        values = [str(item).strip().upper() for item in raw_value if str(item).strip()]
    else:
        return []
    normalized: list[str] = []
    seen = set()
    for value in values:
        if len(value) != 2 or not value.isalpha() or value in seen:
            continue
        normalized.append(value)
        seen.add(value)
    return normalized


def _derive_geo_id_from_countries(country_codes: list[str]) -> str:
    for country_code in country_codes:
        geo_id = COUNTRY_TO_LINKEDIN_GEO.get(country_code)
        if geo_id:
            return geo_id
    return ""


def _derive_source_cities(country_codes: list[str]) -> list[str]:
    cities: list[str] = []
    seen = set()
    for country_code in country_codes:
        for city in COUNTRY_TO_SOURCE_CITIES.get(country_code, []):
            if city in seen:
                continue
            cities.append(city)
            seen.add(city)
    return cities[:8]


def _portal_label(portal_id: str) -> str:
    portal_definition = PORTAL_OPTION_BY_ID.get(str(portal_id or "").strip())
    if portal_definition:
        return str(portal_definition.get("label") or portal_id)
    return str(portal_id or "").strip()


def _portal_region_labels(portal_id: str) -> list[str]:
    portal_definition = PORTAL_OPTION_BY_ID.get(str(portal_id or "").strip()) or {}
    return [
        COUNTRY_LABEL_BY_CODE.get(country_code, country_code)
        for country_code in portal_definition.get("country_codes") or []
    ]


def _recommended_multi_portal_ids(country_codes: list[str]) -> list[str]:
    recommended: list[str] = []
    seen = set()
    for portal_id in BASE_MULTI_PORTAL_DEFAULT_IDS:
        if portal_id in PORTAL_OPTION_BY_ID and portal_id not in seen:
            recommended.append(portal_id)
            seen.add(portal_id)
    for country_code in country_codes:
        for portal_id in COUNTRY_TO_RECOMMENDED_PORTALS.get(country_code, []):
            if portal_id in PORTAL_OPTION_BY_ID and portal_id not in seen:
                recommended.append(portal_id)
                seen.add(portal_id)
    return recommended or list(DEFAULT_MULTI_PORTAL_IDS)


def _portal_country_mismatch_errors(portals: list[str], country_codes: list[str]) -> list[dict[str, str]]:
    selected_countries = set(country_codes)
    if not selected_countries:
        return []
    errors: list[dict[str, str]] = []
    for portal_id in portals:
        required_countries = set((PORTAL_OPTION_BY_ID.get(str(portal_id or "").strip()) or {}).get("country_codes") or [])
        if required_countries and not required_countries.intersection(selected_countries):
            region_labels = _portal_region_labels(portal_id)
            errors.append(
                _field_error(
                    "portals",
                    "country_mismatch",
                    (
                        f"{_portal_label(portal_id)} only appears for "
                        f"{', '.join(region_labels) or 'the supported target countries'}."
                    ),
                    source_id=SOURCE_MULTI_PORTAL,
                )
            )
    return errors


def _load_discovered_source_sites(paths: tuple[Path, ...]) -> list[dict[str, str]]:
    return load_discovered_company_site_entries(paths)


def derive_runtime_defaults_from_settings(
    settings: dict[str, Any],
    *,
    source_ids: list[str] | None = None,
) -> dict[str, Any]:
    selected_source_ids = set(source_ids or [])
    country_codes = _normalize_country_codes(settings.get("country_codes"))
    derived: dict[str, Any] = {}
    if country_codes and SOURCE_LINKEDIN_SEARCH in selected_source_ids and not settings.get("geo_id"):
        geo_id = _derive_geo_id_from_countries(country_codes)
        if geo_id:
            derived["geo_id"] = geo_id
    if SOURCE_MULTI_PORTAL in selected_source_ids:
        if not settings.get("portals"):
            derived["portals"] = _recommended_multi_portal_ids(country_codes)
        if not settings.get("cities") and country_codes:
            cities = _derive_source_cities(country_codes)
            if cities:
                derived["cities"] = cities
        if not settings.get("posted_within_days") and settings.get("time_posted_seconds"):
            try:
                posted_since_days = max(1, int(int(settings["time_posted_seconds"]) / 86400))
            except (TypeError, ValueError):
                posted_since_days = 0
            if posted_since_days:
                derived["posted_within_days"] = posted_since_days
    return derived


def _annotate_builder_field(field_definition: dict) -> dict:
    field = deepcopy(field_definition)
    field_id = str(field.get("id") or "")
    field["section"] = FIELD_SECTION_BY_ID.get(field_id, "advanced")
    field["user_facing"] = field_id in USER_FACING_FIELD_IDS
    field["sort_order"] = FIELD_SORT_ORDER.get(field_id, 999)
    if field_id in {
        "languages",
        "stage1_prompt_override",
        "stage4_extra_prompt",
        "stage4_prompt_override",
        LIGHT_CUSTOMIZATION_EXTRA_PROMPT_FIELD,
        LIGHT_CUSTOMIZATION_PROMPT_OVERRIDE_FIELD,
        AGGRESSIVE_CUSTOMIZATION_EXTRA_PROMPT_FIELD,
        AGGRESSIVE_CUSTOMIZATION_PROMPT_OVERRIDE_FIELD,
    }:
        field["frontend_visible"] = False
    if field_id == "geo_id":
        field["description"] = "Derived internally from the selected country when possible."
    if field_id == "target_roles":
        field["description"] = (
            "Add the roles this workspace should target so search keywords and document emphasis stay aligned."
        )
    if field_id == "workspace_cv_asset_id":
        field["required"] = True
    return field


def _catalog_configuration_fields() -> list[dict]:
    fields = [_annotate_builder_field(field) for field in _configuration_fields()]
    return sorted(fields, key=lambda item: (int(item.get("sort_order", 999)), str(item.get("label") or "")))


def workspace_builder_catalog() -> BuilderCatalog:
    return BuilderCatalog(
        flows=[
            {
                "id": FLOW_TAILORED_DOCUMENTS,
                "name": "Tailored Application Documents",
                "description": "Build a workflow that searches or ingests jobs, screens them, and generates tailored application documents.",
                "frontend_visible": True,
            },
            {
                "id": FLOW_REUSABLE_PACKAGES,
                "name": "Reusable Application Packages",
                "description": "Build a workflow that collects jobs, groups them into reusable role buckets, and exports packaged application assets.",
                "frontend_visible": False,
            },
        ],
        sources=[
            {
                "id": SOURCE_LINKEDIN_SEARCH,
                "connector_id": "linkedin_jobs",
                "name": "LinkedIn Jobs",
                "description": "Legacy LinkedIn search source kept only for older workspaces that already use it.",
                "compatible_flows": [FLOW_TAILORED_DOCUMENTS],
                "frontend_visible": False,
                "legacy": True,
            },
            {
                "id": SOURCE_CURATED_URLS,
                "connector_id": "curated_job_urls",
                "name": "Exact Job Links",
                "description": "Legacy source for pasting exact job posting links into a workspace.",
                "compatible_flows": [FLOW_TAILORED_DOCUMENTS],
                "frontend_visible": False,
            },
            {
                "id": SOURCE_ACADEMIC_CAREER_SITES,
                "connector_id": "academic_career_sites",
                "name": "Academic Jobs",
                "description": "Search university, department, chair, institute, and research-site openings from the saved academic list, with up to 50 academic URLs of your own.",
                "compatible_flows": [FLOW_TAILORED_DOCUMENTS],
            },
            {
                "id": SOURCE_COMPANY_CAREER_SITES,
                "connector_id": "company_career_sites",
                "name": "Company Websites",
                "description": "Search roles from major company career sites worldwide and add up to 50 company URLs of your own.",
                "compatible_flows": [FLOW_TAILORED_DOCUMENTS],
            },
            {
                "id": SOURCE_MULTI_PORTAL,
                "connector_id": "job_board_collection",
                "name": "Other Job Boards",
                "description": "Search major global job boards, and unlock regional leaders automatically when the selected countries match them.",
                "compatible_flows": [FLOW_TAILORED_DOCUMENTS, FLOW_REUSABLE_PACKAGES],
            },
        ],
        modules=[
            {
                "id": MODULE_SCREENING,
                "name": "Screening Filter",
                "description": "Apply a first-pass fit filter before deeper processing.",
                "compatible_flows": [FLOW_TAILORED_DOCUMENTS, FLOW_REUSABLE_PACKAGES],
                "default_enabled": True,
            },
            {
                "id": MODULE_PRIORITY,
                "name": "Priority Ranking",
                "description": "Rank jobs and keep the strongest matches before document generation.",
                "compatible_flows": [FLOW_TAILORED_DOCUMENTS],
                "default_enabled": True,
            },
            {
                "id": MODULE_ROLE_CLASSIFICATION,
                "name": "Role Classification",
                "description": "Assign jobs into reusable role groups for profile packaging.",
                "compatible_flows": [FLOW_REUSABLE_PACKAGES],
                "default_enabled": True,
            },
            {
                "id": MODULE_REUSABLE_PROFILES,
                "name": "Reusable Profile Builder",
                "description": "Generate reusable role-based profile documents from the classified jobs.",
                "compatible_flows": [FLOW_REUSABLE_PACKAGES],
                "default_enabled": True,
            },
            {
                "id": MODULE_TAILORED_DOCUMENTS,
                "name": "Tailored Document Generation",
                "description": "Generate tailored application documents and tracker exports for each accepted job.",
                "compatible_flows": [FLOW_TAILORED_DOCUMENTS],
                "default_enabled": True,
            },
            {
                "id": MODULE_APPLICATION_PACKAGING,
                "name": "Application Packaging",
                "description": "Export application bundles, email drafts, and reusable package artifacts.",
                "compatible_flows": [FLOW_REUSABLE_PACKAGES],
                "default_enabled": True,
            },
        ],
        configuration_fields=_catalog_configuration_fields(),
        starter_profiles=[
            {"id": "job_seeker_primary", "label": "Primary Job Seeker Profile"},
            {"id": "operations_profile", "label": "Operations-Focused Profile"},
        ],
        starter_prompt_families=[
            {"id": FLOW_TAILORED_DOCUMENTS, "label": "Tailored Documents"},
            {"id": FLOW_REUSABLE_PACKAGES, "label": "Reusable Packages"},
        ],
        builder_sections=list(BUILDER_SECTIONS),
    )


def _slugify(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "_", str(value or "").strip().lower())
    normalized = re.sub(r"_+", "_", normalized).strip("_")
    return normalized or f"workspace_{uuid4().hex[:8]}"


def _validate_flow_sources(flow_id: str, source_ids: list[str]) -> None:
    catalog = workspace_builder_catalog().to_dict()
    compatible_sources = {
        item["id"]
        for item in catalog["sources"]
        if flow_id in item["compatible_flows"]
    }
    invalid_sources = [source_id for source_id in source_ids if source_id not in compatible_sources]
    if invalid_sources:
        raise ValueError(
            f"Sources {invalid_sources} are not compatible with flow '{flow_id}'.",
        )


def _validate_modules(flow_id: str, module_ids: list[str]) -> None:
    catalog = workspace_builder_catalog().to_dict()
    compatible_modules = {
        item["id"]
        for item in catalog["modules"]
        if flow_id in item["compatible_flows"]
    }
    invalid_modules = [module_id for module_id in module_ids if module_id not in compatible_modules]
    if invalid_modules:
        raise ValueError(
            f"Modules {invalid_modules} are not compatible with flow '{flow_id}'.",
        )


def _default_modules_for_flow(flow_id: str) -> list[str]:
    catalog = workspace_builder_catalog().to_dict()
    return [
        item["id"]
        for item in catalog["modules"]
        if flow_id in item["compatible_flows"] and bool(item.get("default_enabled"))
    ]


def _normalize_tag_list(raw_value: "Any") -> list[str]:
    if isinstance(raw_value, str):
        values = raw_value.split(",")
    elif isinstance(raw_value, (list, tuple, set)):
        values = list(raw_value)
    else:
        return []
    return [str(item).strip() for item in values if str(item).strip()]


def _normalize_multi_select(raw_value: "Any") -> list["Any"]:
    if isinstance(raw_value, str):
        values = [item.strip() for item in raw_value.split(",") if item.strip()]
    elif isinstance(raw_value, (list, tuple, set)):
        values = [item for item in raw_value if str(item).strip()]
    else:
        return []
    normalized: list[Any] = []
    for item in values:
        text = str(item).strip()
        if not text:
            continue
        if text.isdigit():
            normalized.append(int(text))
        else:
            normalized.append(text)
    return normalized


def _normalize_url_list(raw_value: "Any") -> list[str]:
    if isinstance(raw_value, str):
        values = [line.strip() for line in raw_value.replace(",", "\n").splitlines() if line.strip()]
    elif isinstance(raw_value, (list, tuple, set)):
        values = []
        for item in raw_value:
            text = str(item).strip()
            if not text:
                continue
            values.extend([line.strip() for line in text.replace(",", "\n").splitlines() if line.strip()])
    else:
        return []
    deduped: list[str] = []
    seen = set()
    for value in values:
        parsed = urlparse(value)
        if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc.strip():
            continue
        if value in seen:
            continue
        deduped.append(value)
        seen.add(value)
        if len(deduped) >= 50:
            break
    return deduped


def _normalize_company_site_list(raw_value: "Any") -> list[dict[str, str]]:
    if isinstance(raw_value, str):
        values = [line.strip() for line in raw_value.replace(",", "\n").splitlines() if line.strip()]
    elif isinstance(raw_value, (list, tuple, set)):
        values = []
        for item in raw_value:
            if isinstance(item, str):
                values.extend([line.strip() for line in item.replace(",", "\n").splitlines() if line.strip()])
            else:
                values.append(item)
    else:
        return []

    normalized: list[dict[str, str]] = []
    seen_urls = set()
    for value in values:
        company_name = ""
        url = ""
        if isinstance(value, dict):
            company_name = str(value.get("company_name") or value.get("company") or "").strip()
            url = str(value.get("url") or "").strip()
        else:
            text = str(value or "").strip()
            if not text:
                continue
            if "|" in text:
                left, right = [part.strip() for part in text.split("|", 1)]
                if right.startswith("http://") or right.startswith("https://"):
                    company_name, url = left, right
                elif left.startswith("http://") or left.startswith("https://"):
                    company_name, url = right, left
                else:
                    company_name, url = left, right
            else:
                url = text
        parsed = urlparse(url)
        if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc.strip():
            continue
        if url in seen_urls:
            continue
        seen_urls.add(url)
        normalized.append({"company_name": company_name, "url": url})
        if len(normalized) >= 50:
            break
    return normalized


def _normalize_setting_value(field_definition: dict, raw_value: "Any") -> "Any":
    field_type = str(field_definition.get("type") or "").strip()
    if field_definition.get("id") == "country_codes":
        return _normalize_country_codes(raw_value)
    if field_type == "tag_list":
        return _normalize_tag_list(raw_value)
    if field_type == "multi_select":
        normalized = _normalize_multi_select(raw_value)
        return normalized
    if field_type == "url_list":
        return _normalize_url_list(raw_value)
    if field_type == "company_site_list":
        return _normalize_company_site_list(raw_value)
    if field_type == "number":
        text = str(raw_value or "").strip()
        if not text:
            return None
        return int(float(text))
    if field_type == "float":
        text = str(raw_value or "").strip()
        if not text:
            return None
        return float(text)
    if field_type == "boolean":
        if isinstance(raw_value, bool):
            return raw_value
        text = str(raw_value or "").strip().lower()
        if not text:
            return None
        if text in {"1", "true", "yes", "on"}:
            return True
        if text in {"0", "false", "no", "off"}:
            return False
        return None
    if field_type == "select":
        text = str(raw_value or "").strip()
        if not text:
            return None
        return int(text) if text.isdigit() else text
    text = str(raw_value or "").strip()
    return text or None


def _field_error(
    field: str,
    code: str,
    message: str,
    *,
    source_id: str = "",
) -> dict[str, str]:
    error = {
        "field": str(field or "").strip(),
        "code": str(code or "").strip(),
        "message": str(message or "").strip(),
    }
    if source_id:
        error["source_id"] = str(source_id).strip()
    return error


def _dedupe_field_errors(errors: list[dict[str, Any]]) -> list[dict[str, str]]:
    deduped: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for raw_error in errors:
        if not isinstance(raw_error, dict):
            continue
        field = str(raw_error.get("field") or "").strip()
        code = str(raw_error.get("code") or "").strip()
        message = str(raw_error.get("message") or "").strip()
        source_id = str(raw_error.get("source_id") or "").strip()
        if not field or not code or not message:
            continue
        dedupe_key = (field, code, source_id)
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        deduped.append(_field_error(field, code, message, source_id=source_id))
    return deduped


def _normalize_workspace_settings_base(
    flow_id: str,
    source_ids: list[str],
    payload_settings: dict[str, "Any"],
) -> dict[str, Any]:
    field_map = {field["id"]: field for field in _configuration_fields()}
    selected_source_ids = set(source_ids)
    settings: dict[str, Any] = {}
    for key, raw_value in dict(payload_settings or {}).items():
        field = field_map.get(str(key))
        if field is None:
            continue
        compatible_flows = set(field.get("compatible_flows") or [])
        if compatible_flows and flow_id not in compatible_flows:
            continue
        field_source_ids = set(field.get("source_ids") or [])
        if field_source_ids and not field_source_ids.intersection(selected_source_ids):
            continue
        normalized = _normalize_setting_value(field, raw_value)
        if normalized in (None, "", [], {}):
            continue
        settings[str(key)] = normalized
    return settings


def _build_workspace_settings(flow_id: str, source_ids: list[str], payload_settings: dict[str, "Any"]) -> dict[str, "Any"]:
    selected_source_ids = set(source_ids)
    settings = _normalize_workspace_settings_base(flow_id, source_ids, payload_settings)
    settings.update(
        {
            key: value
            for key, value in derive_runtime_defaults_from_settings(settings, source_ids=list(selected_source_ids)).items()
            if value not in (None, "", [], {})
        }
    )
    if flow_id == FLOW_TAILORED_DOCUMENTS:
        settings["job_filtering_mode"] = normalize_job_filtering_mode(settings.get("job_filtering_mode"))
    return settings


def validate_workspace_source_configuration(payload: dict[str, Any]) -> dict[str, Any]:
    flow_id = str(payload.get("flow_id") or FLOW_TAILORED_DOCUMENTS).strip()
    source_ids = [str(item).strip() for item in payload.get("source_ids") or [] if str(item).strip()]
    settings = _normalize_workspace_settings_base(flow_id, source_ids, dict(payload.get("settings") or {}))
    derived_runtime_defaults = derive_runtime_defaults_from_settings(settings, source_ids=source_ids)
    effective_settings = {**settings, **derived_runtime_defaults}
    results: list[dict[str, Any]] = []
    field_errors: list[dict[str, str]] = []

    def add_result(
        source_id: str,
        *,
        status: str,
        summary: str,
        details: list[str] | None = None,
        source_field_errors: list[dict[str, str]] | None = None,
    ) -> None:
        normalized_field_errors = _dedupe_field_errors(list(source_field_errors or []))
        results.append(
            {
                "source_id": source_id,
                "status": status,
                "summary": summary,
                "details": list(details or []),
                "field_errors": normalized_field_errors,
            }
        )
        field_errors.extend(normalized_field_errors)

    if SOURCE_LINKEDIN_SEARCH in source_ids:
        linkedin_details: list[str] = []
        linkedin_field_errors: list[dict[str, str]] = []
        status = "valid"
        if not effective_settings.get("keywords"):
            status = "invalid"
            linkedin_details.append("Add at least one target keyword.")
            linkedin_field_errors.append(
                _field_error(
                    "keywords",
                    "required",
                    "Add at least one target keyword before enabling LinkedIn search.",
                    source_id=SOURCE_LINKEDIN_SEARCH,
                )
            )
        derived_geo_id = str(effective_settings.get("geo_id") or "")
        if derived_geo_id:
            linkedin_details.append(f"LinkedIn geo id resolved to {derived_geo_id}.")
        else:
            status = "invalid"
            linkedin_details.append("Select at least one target country so LinkedIn location can be derived.")
            linkedin_field_errors.append(
                _field_error(
                    "country_codes",
                    "required",
                    "Select at least one target country so LinkedIn location can be derived.",
                    source_id=SOURCE_LINKEDIN_SEARCH,
                )
            )
        add_result(
            SOURCE_LINKEDIN_SEARCH,
            status=status,
            summary="LinkedIn search is ready." if status == "valid" else "LinkedIn search is missing required setup.",
            details=linkedin_details,
            source_field_errors=linkedin_field_errors,
        )

    if SOURCE_CURATED_URLS in source_ids:
        urls = effective_settings.get("manual_url_seed_list") or []
        details = [f"{len(urls)} curated URL(s) supplied."] if urls else ["Paste one or more job URLs."]
        add_result(
            SOURCE_CURATED_URLS,
            status="valid" if urls else "invalid",
            summary="Curated URLs look usable." if urls else "Curated URLs are required for this source.",
            details=details,
            source_field_errors=(
                []
                if urls
                else [
                    _field_error(
                        "manual_url_seed_list",
                        "required",
                        "Paste one or more job URLs before enabling exact job links.",
                        source_id=SOURCE_CURATED_URLS,
                    )
                ]
            ),
        )

    if SOURCE_COMPANY_CAREER_SITES in source_ids:
        companies = effective_settings.get("company_career_sites") or []
        discovered_companies = [] if companies else _load_discovered_source_sites(REGULAR_COMPANY_SITE_FILES)
        effective_companies = companies or discovered_companies
        details = (
            [f"{len(companies)} pasted career site(s) configured."]
            if companies
            else (
                [f"{len(discovered_companies)} saved career site(s) are ready to use."]
                if discovered_companies
                else ["Add one or more company URLs, or use the saved company-site list."]
            )
        )
        add_result(
            SOURCE_COMPANY_CAREER_SITES,
            status="valid" if effective_companies else "invalid",
            summary=(
                "Company career sites look usable."
                if effective_companies
                else "Company career sites are required for this source."
            ),
            details=details,
            source_field_errors=(
                []
                if effective_companies
                else [
                    _field_error(
                        "company_career_sites",
                        "required",
                        "Add at least one company website or use the saved company-site list first.",
                        source_id=SOURCE_COMPANY_CAREER_SITES,
                    )
                ]
            ),
        )

    if SOURCE_ACADEMIC_CAREER_SITES in source_ids:
        academic_sites = effective_settings.get("academic_career_sites") or []
        discovered_academic_sites = [] if academic_sites else _load_discovered_source_sites(ACADEMIC_CAREER_SITE_FILES)
        effective_academic_sites = academic_sites or discovered_academic_sites
        details = (
            [f"{len(academic_sites)} pasted academic site(s) configured."]
            if academic_sites
            else (
                [f"{len(discovered_academic_sites)} saved academic site(s) are ready to use."]
                if discovered_academic_sites
                else ["Add one or more academic URLs, or use the saved academic-site list."]
            )
        )
        add_result(
            SOURCE_ACADEMIC_CAREER_SITES,
            status="valid" if effective_academic_sites else "invalid",
            summary=(
                "Academic sites look usable."
                if effective_academic_sites
                else "Academic sites are required for this source."
            ),
            details=details,
            source_field_errors=(
                []
                if effective_academic_sites
                else [
                    _field_error(
                        "academic_career_sites",
                        "required",
                        "Add at least one academic website or use the saved academic-site list first.",
                        source_id=SOURCE_ACADEMIC_CAREER_SITES,
                    )
                ]
            ),
        )

    if SOURCE_MULTI_PORTAL in source_ids:
        portals = [str(item).strip() for item in (effective_settings.get("portals") or []) if str(item).strip()]
        country_codes = _normalize_country_codes(effective_settings.get("country_codes"))
        cities = effective_settings.get("cities") or []
        status = "valid"
        details: list[str] = []
        multi_portal_field_errors: list[dict[str, str]] = []
        if not effective_settings.get("keywords"):
            status = "invalid"
            details.append("Add at least one target keyword before enabling job boards.")
            multi_portal_field_errors.append(
                _field_error(
                    "keywords",
                    "required",
                    "Add at least one target keyword before enabling job boards.",
                    source_id=SOURCE_MULTI_PORTAL,
                )
            )
        if not portals:
            status = "invalid"
            details.append("Choose at least one job board.")
            multi_portal_field_errors.append(
                _field_error(
                    "portals",
                    "required",
                    "Choose at least one job board before enabling other job boards.",
                    source_id=SOURCE_MULTI_PORTAL,
                )
            )
        else:
            details.append(f"Boards: {', '.join(_portal_label(item) for item in portals)}")
            country_mismatch_errors = _portal_country_mismatch_errors(portals, country_codes)
            if country_mismatch_errors:
                status = "invalid"
                multi_portal_field_errors.extend(country_mismatch_errors)
                details.extend(item["message"] for item in country_mismatch_errors)
        if not cities:
            status = "invalid"
            details.append("Select a target country so representative source cities can be derived.")
            multi_portal_field_errors.append(
                _field_error(
                    "country_codes",
                    "required",
                    "Select at least one target country so job-board source cities can be derived.",
                    source_id=SOURCE_MULTI_PORTAL,
                )
            )
        else:
            details.append(f"Representative source cities: {', '.join(str(item) for item in cities[:4])}")
        add_result(
            SOURCE_MULTI_PORTAL,
            status=status,
            summary="Job board sourcing is ready." if status == "valid" else "Job board sourcing is missing required setup.",
            details=details,
            source_field_errors=multi_portal_field_errors,
        )

    return {
        "flow_id": flow_id,
        "source_ids": list(source_ids),
        "valid": all(item["status"] == "valid" for item in results) if results else True,
        "field_errors": _dedupe_field_errors(field_errors),
        "source_results": results,
        "derived_runtime_defaults": derived_runtime_defaults,
    }


def _default_prompt_family(flow_id: str) -> str:
    return flow_id


def _default_profile_label(flow_id: str) -> str:
    if flow_id == FLOW_REUSABLE_PACKAGES:
        return "Operations Profile"
    return "Primary Job Seeker Profile"


def _build_source_stages(source_ids: list[str]) -> tuple[list[StageDefinition], list[str], list[JobSource]]:
    stages: list[StageDefinition] = []
    output_keys: list[str] = []
    sources: list[JobSource] = []

    if SOURCE_LINKEDIN_SEARCH in source_ids:
        stages.append(
            StageDefinition(
                stage_id="source_linkedin_search",
                stage_type="jobs.acquire.search_listings",
                name="Acquire Search Listings",
                description="Acquire and enrich jobs from the LinkedIn search connector.",
                output_key="source_linkedin_jobs",
                config={"connector_id": "linkedin_jobs"},
            )
        )
        output_keys.append("source_linkedin_jobs")
        sources.append(JobSource(id="source_linkedin_search", connector_id="linkedin_jobs"))

    if SOURCE_CURATED_URLS in source_ids:
        stages.append(
            StageDefinition(
                stage_id="source_curated_urls",
                stage_type="jobs.ingest.curated_urls",
                name="Ingest Curated Job URLs",
                description="Load manually selected job URLs into the shared job schema.",
                output_key="source_curated_jobs",
                config={"connector_id": "curated_job_urls"},
            )
        )
        output_keys.append("source_curated_jobs")
        sources.append(JobSource(id="source_curated_urls", connector_id="curated_job_urls"))

    if SOURCE_COMPANY_CAREER_SITES in source_ids:
        stages.append(
            StageDefinition(
                stage_id="source_company_career_sites",
                stage_type="jobs.acquire.company_sites",
                name="Acquire Company Career Site Jobs",
                description="Scrape backend-prepared company career pages for matching open roles.",
                output_key="source_company_career_jobs",
                config={
                    "connector_id": "company_career_sites",
                    "site_settings_key": "company_career_sites",
                    "request_timeout_setting_key": "company_site_request_timeout_seconds",
                    "max_jobs_setting_key": "company_site_max_jobs_per_site",
                    "discovered_site_paths": [str(path) for path in REGULAR_COMPANY_SITE_FILES],
                },
            )
        )
        output_keys.append("source_company_career_jobs")
        sources.append(JobSource(id="source_company_career_sites", connector_id="company_career_sites"))

    if SOURCE_ACADEMIC_CAREER_SITES in source_ids:
        stages.append(
            StageDefinition(
                stage_id="source_academic_career_sites",
                stage_type="jobs.acquire.company_sites",
                name="Acquire Academic Site Jobs",
                description="Collect matching jobs from saved university, department, chair, and institute pages.",
                output_key="source_academic_career_jobs",
                config={
                    "connector_id": "academic_career_sites",
                    "site_settings_key": "academic_career_sites",
                    "request_timeout_setting_key": "academic_site_request_timeout_seconds",
                    "max_jobs_setting_key": "academic_site_max_jobs_per_site",
                    "discovered_site_paths": [str(path) for path in ACADEMIC_CAREER_SITE_FILES],
                },
            )
        )
        output_keys.append("source_academic_career_jobs")
        sources.append(JobSource(id="source_academic_career_sites", connector_id="academic_career_sites"))

    if SOURCE_MULTI_PORTAL in source_ids:
        stages.append(
            StageDefinition(
                stage_id="source_job_boards",
                stage_type="jobs.acquire.job_boards",
                name="Collect Job Boards",
                description="Collect jobs from the shared job-board connector layer.",
                output_key="source_board_jobs",
                config={"connector_id": "job_board_collection"},
            )
        )
        output_keys.append("source_board_jobs")
        sources.append(JobSource(id="source_job_boards", connector_id="job_board_collection"))

    return stages, output_keys, sources


def _build_tailored_stages(source_output_key: str, module_ids: list[str]) -> list[StageDefinition]:
    stages: list[StageDefinition] = []
    current_key = source_output_key

    if MODULE_SCREENING in module_ids:
        stages.append(
            StageDefinition(
                stage_id="screen_jobs",
                stage_type="jobs.screen.filter",
                name="Screen Jobs",
                description="Apply the shared screening filter to the sourced jobs.",
                input_keys=[current_key],
                output_key="screened_jobs",
                config={"screening_strategy": FLOW_TAILORED_DOCUMENTS},
            )
        )
        current_key = "screened_jobs"

    if MODULE_PRIORITY in module_ids:
        stages.append(
            StageDefinition(
                stage_id="prioritize_jobs",
                stage_type="jobs.prioritize.rank",
                name="Prioritize Jobs",
                description="Rank jobs and keep the best matches for production output.",
                input_keys=[current_key],
                output_key="production_jobs",
            )
        )
        current_key = "production_jobs"

    if MODULE_TAILORED_DOCUMENTS in module_ids:
        stages.append(
            StageDefinition(
                stage_id="generate_application_documents",
                stage_type="applications.generate.documents",
                name="Generate Application Documents",
                description="Create tailored application files and export tracking records.",
                input_keys=[current_key],
                output_key="generated_jobs",
                config={
                    "generation_id": "tailored_application_documents",
                    "renderer_id": "application_document_export",
                },
            )
        )

    return stages


def build_quick_apply_workflow_template() -> WorkflowTemplate:
    return WorkflowTemplate(
        id="quick_apply_tailored_documents",
        name="Quick Apply Workflow",
        description="Ingest exact job links and generate application documents without creating a dedicated workspace.",
        stages=[
            StageDefinition(
                stage_id="source_exact_job_links",
                stage_type="jobs.ingest.curated_urls",
                name="Ingest Exact Job Links",
                description="Load exact job posting URLs into the shared job schema.",
                output_key="source_exact_job_links",
                config={"connector_id": "curated_job_urls"},
            ),
            StageDefinition(
                stage_id="merge_exact_job_links",
                stage_type="jobs.merge.dedupe",
                name="Merge Exact Job Links",
                description="Remove duplicate job links before document generation.",
                input_keys=["source_exact_job_links"],
                output_key="quick_apply_jobs",
                config={"dedupe_against_tracker": True},
            ),
            StageDefinition(
                stage_id="generate_quick_apply_documents",
                stage_type="applications.generate.documents",
                name="Generate Application Documents",
                description="Create application documents for the pasted job links.",
                input_keys=["quick_apply_jobs"],
                output_key="generated_jobs",
                config={
                    "generation_id": "tailored_application_documents",
                    "renderer_id": "application_document_export",
                },
            ),
        ],
        default_run_settings={
            "builder_mode": "quick_apply",
            "automation_flow": FLOW_TAILORED_DOCUMENTS,
        },
    )


def _build_reusable_package_stages(source_output_key: str, module_ids: list[str]) -> list[StageDefinition]:
    stages: list[StageDefinition] = []
    current_key = source_output_key

    if MODULE_SCREENING in module_ids:
        stages.append(
            StageDefinition(
                stage_id="screen_jobs",
                stage_type="jobs.screen.filter",
                name="Screen Jobs",
                description="Apply the shared screening filter to the sourced jobs.",
                input_keys=[current_key],
                output_key="screened_jobs",
                config={"screening_strategy": FLOW_REUSABLE_PACKAGES},
            )
        )
        current_key = "screened_jobs"

    if MODULE_ROLE_CLASSIFICATION in module_ids:
        stages.append(
            StageDefinition(
                stage_id="classify_roles",
                stage_type="jobs.classify.roles",
                name="Classify Roles",
                description="Assign jobs to reusable role groups.",
                input_keys=[current_key],
                output_key="classified_jobs",
            )
        )
        current_key = "classified_jobs"

    if MODULE_REUSABLE_PROFILES in module_ids:
        stages.append(
            StageDefinition(
                stage_id="build_reusable_profiles",
                stage_type="profiles.generate.reusable",
                name="Build Reusable Profiles",
                description="Build reusable role-based profile documents.",
                input_keys=[current_key],
                output_key="role_profile_index",
                config={"generation_id": "reusable_role_profiles"},
            )
        )

    if MODULE_APPLICATION_PACKAGING in module_ids:
        stages.append(
            StageDefinition(
                stage_id="package_applications",
                stage_type="applications.package.export",
                name="Package Applications",
                description="Create packaged application assets for the generated role profiles.",
                input_keys=[current_key, "role_profile_index"],
                output_key="packaged_jobs",
                config={"renderer_id": "application_package_export"},
            )
        )

    return stages


def build_workspace_from_scratch(payload: dict) -> tuple[WorkflowTemplate, WorkspaceDefinition]:
    name = str(payload.get("name") or "").strip()
    if not name:
        raise ValueError("workspace name is required")

    flow_id = str(payload.get("flow_id") or FLOW_TAILORED_DOCUMENTS).strip()
    if flow_id not in {FLOW_TAILORED_DOCUMENTS, FLOW_REUSABLE_PACKAGES}:
        raise ValueError(f"Unsupported flow_id: {flow_id}")

    source_ids = [str(item).strip() for item in payload.get("source_ids") or [] if str(item).strip()]
    if not source_ids:
        raise ValueError("At least one source is required.")
    _validate_flow_sources(flow_id, source_ids)

    module_ids = [str(item).strip() for item in payload.get("module_ids") or [] if str(item).strip()]
    if not module_ids:
        module_ids = _default_modules_for_flow(flow_id)
    _validate_modules(flow_id, module_ids)

    if flow_id == FLOW_REUSABLE_PACKAGES and MODULE_APPLICATION_PACKAGING in module_ids and MODULE_REUSABLE_PROFILES not in module_ids:
        raise ValueError("Application packaging requires the reusable profile builder module.")
    if flow_id == FLOW_REUSABLE_PACKAGES and MODULE_REUSABLE_PROFILES in module_ids and MODULE_ROLE_CLASSIFICATION not in module_ids:
        raise ValueError("Reusable profile builder requires the role classification module.")

    workspace_slug = str(payload.get("workspace_id") or "").strip() or _slugify(name)
    template_id = str(payload.get("workflow_template_id") or "").strip() or f"{workspace_slug}_workflow"
    description = str(payload.get("description") or "").strip()
    prompt_family = str(payload.get("prompt_family") or _default_prompt_family(flow_id)).strip()
    profile_label = str(payload.get("profile_label") or _default_profile_label(flow_id)).strip()
    prompt_set_id = f"{workspace_slug}_prompt"
    profile_id = f"{workspace_slug}_profile"
    workspace_settings = _build_workspace_settings(
        flow_id,
        source_ids,
        dict(payload.get("settings") or {}),
    )
    workspace_cv_asset = deepcopy(payload.get("workspace_cv_asset") or {})
    normalized_workspace_contract = normalize_workspace_configuration_v2(
        {
            "flow_id": flow_id,
            "source_ids": list(source_ids),
            "profile_label": profile_label,
            "settings": dict(workspace_settings),
        }
    )

    source_stages, source_output_keys, sources = _build_source_stages(source_ids)
    if len(source_output_keys) > 1:
        merge_stage_config = {"dedupe_against_tracker": True}
        if "dedupe_against_tracker" in workspace_settings:
            merge_stage_config["dedupe_against_tracker"] = bool(workspace_settings["dedupe_against_tracker"])
        source_stages.append(
            StageDefinition(
                stage_id="merge_source_jobs",
                stage_type="jobs.merge.dedupe",
                name="Merge Source Jobs",
                description="Combine jobs from all enabled sources and remove duplicates.",
                input_keys=source_output_keys,
                output_key="merged_source_jobs",
                config=merge_stage_config,
            )
        )
        source_output_key = "merged_source_jobs"
    else:
        source_output_key = source_output_keys[0]

    if flow_id == FLOW_REUSABLE_PACKAGES:
        flow_stages = _build_reusable_package_stages(source_output_key, module_ids)
        settings = {
            "config_loader": "reusable_packages",
            "automation_flow": FLOW_REUSABLE_PACKAGES,
        }
    else:
        flow_stages = _build_tailored_stages(source_output_key, module_ids)
        settings = {
            "config_loader": "tailored_documents",
            "automation_flow": FLOW_TAILORED_DOCUMENTS,
            "manual_sources_are_preapproved": bool(payload.get("manual_sources_are_preapproved", True)),
        }

    workflow_template = WorkflowTemplate(
        id=template_id,
        name=f"{name} Workflow",
        description=description or f"Custom workflow for {name}.",
        stages=[*source_stages, *flow_stages],
        default_run_settings={
            "builder_mode": "scratch",
            "automation_flow": flow_id,
        },
    )

    feature_flags = {
        "screening_filter": MODULE_SCREENING in module_ids,
        "priority_ranking": MODULE_PRIORITY in module_ids,
        "role_classification": MODULE_ROLE_CLASSIFICATION in module_ids,
        "reusable_profile_builder": MODULE_REUSABLE_PROFILES in module_ids,
        "tailored_document_generation": MODULE_TAILORED_DOCUMENTS in module_ids,
        "application_packaging": MODULE_APPLICATION_PACKAGING in module_ids,
    }

    workspace = WorkspaceDefinition(
        id=workspace_slug,
        name=name,
        workflow_template_id=workflow_template.id,
        description=description,
        workspace_type="custom",
        settings={**settings, **workspace_settings},
        feature_flags=feature_flags,
        profiles=[
            ProfileRef(
                id=profile_id,
                label=profile_label,
                settings={"automation_flow": flow_id},
            )
        ],
        prompt_sets=[
            PromptSetRef(
                id=prompt_set_id,
                family=prompt_family,
                settings={"automation_flow": flow_id},
            )
        ],
        sources=sources,
        metadata={
            "builder_mode": "scratch",
            "automation_flow": flow_id,
            "modules": list(module_ids),
            "source_ids": list(source_ids),
            "workspace_cv_asset": workspace_cv_asset,
            "workspace_configuration_v2": normalized_workspace_contract,
        },
    )
    return workflow_template, workspace
