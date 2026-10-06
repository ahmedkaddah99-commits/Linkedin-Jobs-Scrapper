"""One supplemental extraction for missing customer enrichment fields."""
import json
from copy import deepcopy

from backend.application.catalog_job_filters import classification_prompt, validate_classification
from backend.application.personalized_jobs_intelligence import build_preserved_original_posting
from backend.application.vps_job_descriptions import build_pilot_description

FILTER_FIELDS = ('roles', 'required_experience_years', 'experience_level', 'work_arrangement',
                 'employment_type', 'skills', 'role_type')
SECTIONS = ('responsibilities', 'required_qualifications', 'preferred_qualifications',
            'benefits', 'application_details')
HEADERS = ('location', 'work_arrangement', 'employment_type', 'seniority',
           'experience_years_min', 'experience_years_max', 'salary')


def empty(value):
    if isinstance(value, dict) and 'value' in value:
        return empty(value['value'])
    return value is None or value == '' or value == [] or value == {}


def missing_fields(filters, summary, structured):
    missing = ['filters.' + key for key in FILTER_FIELDS if empty(filters.get(key))]
    if filters.get('employment_defaulted') and 'filters.employment_type' not in missing:
        missing.append('filters.employment_type')
    missing += ['summary.' + key for key in SECTIONS if empty(summary.get(key))]
    missing += ['structured.' + key for key in HEADERS if empty(structured.get(key))]
    return missing


def supplement(row, filters, summary, structured, generate):
    """Make one model request, validate its evidence, and fill empty values only."""
    gaps = missing_fields(filters, summary, structured)
    if not gaps:
        return {}, []
    original = build_preserved_original_posting(row)
    source = str(original.get('description_text') or original.get('description') or '').strip()
    posting = {'id': row['canonical_job_id'], 'title': row['title'],
               'description': source, 'location': row.get('version_location', '')}
    prompts = []
    if source:
        build_pilot_description(row, lambda prompt: prompts.append(prompt) or
                                {'items': [], 'header_candidates': {}}, require_source_quotes=True)
    description_prompt = prompts[0] if prompts else (
        'No original description is available. Return items=[] and header_candidates={}.'
    )
    response = generate(
        'Perform ONE supplemental pass for these missing fields: ' + json.dumps(gaps) + '. '
        'Do not overwrite populated fields. Never invent missing information. Unsupported values must be null or []. '
        'Return exactly {"filters":{"jobs":[...]},"description":{"items":[...],"header_candidates":{...}}. '
        'Apply these filter extraction rules:\n' + classification_prompt([posting]) +
        '\nApply these description extraction rules inside the description object:\n' + description_prompt +
        '\nFINAL RESPONSE CONTRACT: the outer object has ONLY filters and description. '
        'Put jobs inside filters, and items/header_candidates inside description. '
        'Do not return a top-level jobs or items array. Return '
        '{"filters":{"jobs":[{"id":"' + row['canonical_job_id'] +
        '","collar":"white","roles":[],"evidence":""}]},'
        '"description":{"items":[],"header_candidates":{}}}, replacing empty values only when supported.'
    )
    updated_filters, updated_summary, updated_structured = deepcopy(filters), deepcopy(summary), deepcopy(structured)
    output = {}
    jobs = (response.get('filters') or {}).get('jobs') if isinstance(response, dict) else None
    if isinstance(jobs, list) and len(jobs) == 1 and isinstance(jobs[0], dict) and jobs[0].get('id') == posting['id']:
        candidate = validate_classification(jobs[0], row['title'] + ' ' + source, row['title'])
        if candidate:
            for key in FILTER_FIELDS:
                if 'filters.' + key not in gaps or empty(candidate.get(key)):
                    continue
                if key == 'employment_type' and candidate.get('employment_defaulted'):
                    continue
                updated_filters[key] = candidate[key]
                # Preserve source evidence for newly recovered filter values.
                for evidence_key in ('source_evidence', key + '_evidence'):
                    if candidate.get(evidence_key):
                        updated_filters[evidence_key] = candidate[evidence_key]
                if key == 'employment_type':
                    updated_filters['employment_defaulted'] = False
            if empty(filters.get('roles')) and updated_filters.get('roles'):
                updated_filters['collar'] = candidate['collar']
                updated_filters['role'] = updated_filters['roles'][0]
            if updated_filters != filters:
                output['filters'] = updated_filters
    description = response.get('description') if isinstance(response, dict) else None
    if source and isinstance(description, dict):
        try:
            candidate = build_pilot_description(row, lambda _: description, require_source_quotes=True)
        except ValueError:
            candidate = None
        if candidate:
            for key in SECTIONS:
                if empty(updated_summary.get(key)) and not empty(candidate['summary'].get(key)):
                    updated_summary[key] = candidate['summary'][key]
            for key in HEADERS:
                if empty(updated_structured.get(key)) and not empty(candidate['structured_description'].get(key)):
                    updated_structured[key] = candidate['structured_description'][key]
            if updated_summary != summary or updated_structured != structured:
                updated_structured['source_passages'] = candidate['structured_description']['source_passages']
                candidate['summary'], candidate['structured_description'] = updated_summary, updated_structured
                output['description'] = candidate
    return output, missing_fields(updated_filters, updated_summary, updated_structured)
