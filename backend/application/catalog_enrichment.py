"""Version-bound Nemo enrichment; storage and scheduling stay in the VPS worker."""
from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from backend.application.catalog_job_filters import classification_prompt, function_prompt, profession_override, validate_classification
from backend.application.personalized_jobs_intelligence import build_preserved_original_posting
from backend.application.vps_job_descriptions import build_pilot_description
from backend.domain.job_filter_source_cache import SOURCE_PATHS, SOURCE_SCHEMA


class EnrichmentStageError(ValueError):
    """Retain valid independent stages when a later stage fails validation."""
    def __init__(self, code, partial):
        super().__init__(code)
        self.partial = partial


def repair(generate, stage, prompt):
    # Production attaches a durable, separately budgeted request per stage.
    # Callers without that capability retain strict single-request behavior.
    if not hasattr(generate, 'for_stage'):
        return None
    return generate.for_stage(stage, prompt)


def enrich_version(row: Mapping[str, Any], generate: Callable) -> dict[str, Any]:
    if row.get("filters_ready") and row.get("description_ready"):
        return {}
    original = build_preserved_original_posting(row)
    source = str(original.get("description_text") or original.get("description") or "").strip()
    if not source and not str(row.get("title") or "").strip():
        raise ValueError("source_missing")
    result: dict[str, Any] = {}
    if not row.get("filters_ready") and profession_override(row.get('title'), source) == ('blue', []):
        result['filters'] = validate_classification(
            {'collar': 'blue', 'roles': [], 'evidence': row['title']}, row['title'] + ' ' + source, row['title'])
        result['filters']['classification_method'] = 'rules'
        return result
    # Build the grounded extraction prompt locally, then make one combined request.
    description_prompt = []
    if not row.get('description_ready'):
        if not source:
            raise ValueError('source_missing')
        if len(source) < 80:
            raise ValueError('source_incomplete')
        def capture(prompt):
            description_prompt.append(prompt)
            return {'items': [], 'header_candidates': {}}
        row = {key: value for key, value in row.items()
               if key not in ('_translate_before_nemo', '_translation_generate')}
        build_pilot_description(row, capture, require_source_quotes=True)
    response = None
    if not row.get("filters_ready"):
        inputs = [{"id": row["canonical_job_id"], "title": row["title"],
                   "location": row.get("version_location", ""), "description": source}]
        prompt = classification_prompt(inputs)
        if description_prompt:
            extraction = description_prompt[0].replace(
                'Return one JSON object only with keys items and header_candidates.',
                'Add items and header_candidates to the SAME classification JSON object.')
            prompt += '\n' + extraction + (
                '\nReturn ONE JSON object with jobs, items, and header_candidates. '
                'Use ONLY exact allowed role labels. Classification evidence must be an original '
                'quote; use the exact posting title when it supports the classification. '
                'Every item.text MUST be English; every source_quote MUST remain in its original language. '
                'One short fact and one contiguous quotation from ONE passage per item. '
                'Never copy example text such as One fact into the output.')
        response = generate(prompt)
        jobs = response.get("jobs") if isinstance(response, Mapping) else None
        if not isinstance(jobs, list) or len(jobs) != 1 or jobs[0].get("id") != row["canonical_job_id"]:
            raise ValueError("filter_response_identity_mismatch")
        filters = validate_classification(jobs[0], str(row["title"]) + " " + source, row["title"])
        if filters is None:
            fixed = repair(generate, 'classification_v1', function_prompt({
                'title': row['title'], 'description': source}) +
                '\nUse the exact title as evidence when supported. Do not translate evidence. '
                'Return only exact allowed labels; omit invented or approximate labels.')
            filters = validate_classification({**jobs[0], **fixed} if isinstance(fixed, Mapping) else fixed,
                                              str(row['title']) + ' ' + source, row['title'])
            if filters is None:
                raise ValueError("filter_validation_failed")
        result["filters"] = filters
        if filters['collar'] == 'blue':
            return result
    if not row.get("description_ready"):
        if not source:
            raise ValueError("source_missing")
        if len(source) < 80:
            raise ValueError("source_incomplete")
        if response is None:
            response = generate(description_prompt[0])
        def validated(value):
            description = build_pilot_description(row, lambda _: value, require_source_quotes=True)
            from backend.application.description_translation import source_language
            rendered = ' '.join(item['text'] for items in description['summary'].values() for item in items)
            if len(rendered) >= 80 and source_language(rendered) != 'en':
                raise ValueError('description_output_not_english')
            if not any(description['summary'].values()):
                raise ValueError('description_has_no_supported_facts')
            return description
        try:
            description = validated(response)
        except ValueError as error:
            try:
                fixed = repair(generate, 'description_v1', description_prompt[0] +
                    '\nALL item.text values must be ENGLISH translations. source_quote must be copied '
                    'unchanged from ONE cited original passage. Write short separate facts; do not '
                    'combine quotations from separate passages. Return real job facts, never example placeholders.')
                if fixed is None:
                    raise error
                description = validated(fixed)
            except ValueError as final_error:
                raise EnrichmentStageError(str(final_error), result) from final_error
            except Exception as transient:
                transient.partial = result
                raise
        result["description"] = description
    return result


def attach_source_metadata(filters: dict, payload: dict) -> dict:
    projection = {}
    for path in SOURCE_PATHS:
        value: Any = payload
        for segment in path[2:].split("."):
            value = value.get(segment) if isinstance(value, Mapping) else None
        projection[path] = value
    return {**filters, "source_metadata": projection, "source_metadata_schema": SOURCE_SCHEMA}
