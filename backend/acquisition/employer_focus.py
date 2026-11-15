"""Explicit source scope for the owner's verified-employer rollout.

Function and geography precede paid enrichment. Required experience is decided
only from validated description evidence, immediately before publication.
"""
from __future__ import annotations

import json
import re
from collections.abc import Mapping
from backend.acquisition.job_role_policy import load_policy, normalize_title

SCOPE_VERSION = 'verified_employers_germany_business_v1'


def review_title_candidate(title: str) -> bool:
    """Admit unfamiliar functions and wording to description-based classification.

    A source title is not a taxonomy label. Only explicit student contracts can
    be rejected here; validated classification decides the business function.
    """
    from backend.application.job_metadata_rules import student_type
    value = str(title or '').strip()
    return bool(value) and not student_type(value) and not re.search(
        r'\b(?:ausbildung|auszubildende\w*|apprentice\w*)\b', value, re.I)


def classification_repair_format(title: str) -> dict:
    """Constrain focus repair labels without altering working description output."""
    from backend.application.catalog_job_filters import ROLES
    return {'type':'json_schema','json_schema':{'name':'runr_focus_function','strict':True,'schema':{
        'type':'object','properties':{'collar':{'type':'string','enum':['white','blue']},
            'roles':{'type':'array','items':{'type':'string','enum':list(ROLES)},'maxItems':5},
            'evidence':{'type':'string','enum':[title]}},
        'required':['collar','roles','evidence'],'additionalProperties':False}}}


def business_title_candidate(title: str) -> bool:
    """Match canonical business labels, never use as a source-title allowlist."""
    from backend.application.job_metadata_rules import student_type
    if student_type(title):return False
    value = normalize_title(title)
    if re.search(r'\b\w*praktik\w*\b|\b(?:working[ -]+student|student[ -]+worker)\b', value):
        return False
    policy = load_policy()
    # This is the existing function/contract scope with seniority deferred.
    excluded = [p for p in policy['excluded_title_patterns']
                if 'head of|director' not in p]
    return bool(value and not any(re.search(p, value) for p in excluded)
                and any(re.search(p, value) for p in policy['included_title_patterns']))


def payload_for(row: Mapping) -> dict:
    value = row.get('version_payload_json') or row.get('payload_json')
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            return {}
    return dict(value) if isinstance(value, Mapping) else dict(row)


def is_focus(payload: Mapping) -> bool:
    marker = payload.get('employer_focus')
    return isinstance(marker, Mapping) and marker.get('scope_version') == SCOPE_VERSION


def scope_reason(row: Mapping) -> str:
    payload = payload_for(row)
    if not is_focus(payload):
        return 'outside_employer_focus'
    if str(payload.get('country') or '').strip().casefold() not in {'de', 'deu', 'germany', 'deutschland'}:
        return 'germany_not_confirmed'
    if not review_title_candidate(str(row.get('title') or payload.get('title') or '')):
        return 'employer_focus_contract_or_title_excluded'
    return ''


def business_classification_confirmed(filters: Mapping) -> bool:
    roles = filters.get('roles') or []
    business_roles = {'Customer Success', 'Partnership', 'Sales Support', 'Sales Support Specialist',
                      'Sales Specialist', 'Sales Engineer', 'Technical Sales Engineer', 'Retail Sales',
                      'Logistics Manager',
                      'Inside Sales Representative', 'Field Sales Representative',
                      'Customer Service Representative', 'Customer Service Manager', 'Customer Support'}
    business_roles.update({'Mergers & Acquisitions (M&A) Consultant',
                           'Administrative Assistant', 'Administrative Specialist',
                           'Property Manager'})
    return (filters.get('collar') == 'white' and isinstance(roles,list)
            and any(isinstance(role,str) and (business_title_candidate(role) or role in business_roles) for role in roles))


def publication_reason(filters: Mapping | None, *, filters_hash: str = '',
                       description_hash: str = '', content_hash: str = '',
                       description_ready: bool = False) -> str:
    if not filters or filters_hash != content_hash:return 'employer_focus_enrichment_pending'
    if not business_classification_confirmed(filters):
        return 'employer_focus_business_classification_unconfirmed'
    if description_hash != content_hash or not description_ready:return 'employer_focus_enrichment_pending'
    if filters.get('unresolved_language_passages'):return 'employer_focus_language_review_required'
    if filters.get('employment_type') in {'internship', 'working_student', 'apprenticeship'}:
        return 'employer_focus_contract_excluded'
    years = filters.get('required_experience_years')
    if type(years) in (int, float) and years > 2:
        return 'employer_focus_required_experience_over_two'
    return ''
