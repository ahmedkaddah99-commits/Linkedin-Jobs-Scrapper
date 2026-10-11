"""Compact source projection for filters; source precedence remains unchanged."""
import hashlib
import re

SOURCE_PATHS = ('$.authorization', '$.categories', '$.category', '$.citizenship_required', '$.clearance', '$.company_industry', '$.company_size', '$.company_stage', '$.company_type', '$.country', '$.country_code', '$.date_posted', '$.degree', '$.education', '$.education_level', '$.employment_type', '$.experience_level', '$.experience_years_min', '$.fields.company_size.value', '$.fields.company_type.value', '$.fields.founded_year.value', '$.fields.funding_stage.value', '$.fields.funding_year.value', '$.fields.industry.value', '$.fields.total_funding.value', '$.function', '$.funding_stage', '$.h1b_sponsorship', '$.industry', '$.job_category', '$.job_type', '$.language_requirements', '$.languages', '$.level', '$.lifting', '$.lifting_requirement', '$.location', '$.major', '$.majors', '$.management_role', '$.physical_requirement', '$.posted_at', '$.preferred_major', '$.preferred_majors', '$.published_at', '$.remote_type', '$.required_education', '$.required_experience_years', '$.required_languages', '$.required_skills', '$.role', '$.role_category', '$.role_type', '$.roles', '$.salary.max', '$.salary.min', '$.security_clearance', '$.seniority', '$.size', '$.skills', '$.sponsors_h1b', '$.sponsorship', '$.structured_description.citizenship_required.value', '$.structured_description.experience_years_min.value', '$.structured_description.security_clearance.value', '$.structured_description.skills', '$.type', '$.visa_sponsorship', '$.work_arrangement', '$.work_authorization', '$.work_permit', '$.workplace', '$.workplace_type')
SOURCE_SCHEMA = hashlib.sha256('|'.join(SOURCE_PATHS).encode()).hexdigest()[:16]


def use_cached_source(predicate):
    def substitute(match):
        function,path=match.groups()
        if path not in SOURCE_PATHS:return match.group(0)
        cached_path='$.source_metadata."'+path+'"'
        return "(CASE WHEN json_extract(catalog.filter_json, '$.source_metadata_schema')='"+SOURCE_SCHEMA+"' THEN "+function+"(catalog.filter_json, '"+cached_path+"') ELSE "+match.group(0)+" END)"
    return re.sub(r"(json_extract|json_type)\(catalog\.version_payload_json, '([^']+)'\)",substitute,predicate)
