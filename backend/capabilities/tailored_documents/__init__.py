# Circular-import-safe lazy imports (CP-030)
import importlib

__lazy_modules = {}

def __getattr__(name):
    if name in __lazy_modules:
        mod = importlib.import_module(__lazy_modules[name], __package__)
        attr = getattr(mod, name)
        globals()[name] = attr
        return attr
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = [
    "ExperienceEvidence",
    "MotivationEvidence",
    "MotivationLetterInput",
    "MotivationLetterResult",
    "MotivationLetterSection",
    "assess_evidence_sufficiency",
    "build_evidence_from_profile",
    "build_motivation_prompt",
    "build_structured_motivation_prompt",
    "check_personal_motivation_sufficient",
    "fetch_manual_jobs_from_file",
    "generate_motivation_letter",
    "generate_motivation_letter_for_job",
    "parse_letter_sections",
    "run_stage1_pipeline",
    "run_stage2_pipeline",
    "run_stage3_pipeline",
    "run_stage4_pipeline",
    "validate_letter_claims",
    "validate_section_evidence_refs",
]

__lazy_modules["ExperienceEvidence"] = ".motivation_letters"
__lazy_modules["MotivationEvidence"] = ".motivation_letters"
__lazy_modules["MotivationLetterInput"] = ".motivation_letters"
__lazy_modules["MotivationLetterResult"] = ".motivation_letters"
__lazy_modules["MotivationLetterSection"] = ".motivation_letters"
__lazy_modules["assess_evidence_sufficiency"] = ".motivation_letters"
__lazy_modules["build_evidence_from_profile"] = ".motivation_letters"
__lazy_modules["build_motivation_prompt"] = ".motivation_letters"
__lazy_modules["build_structured_motivation_prompt"] = ".motivation_letters"
__lazy_modules["check_personal_motivation_sufficient"] = ".motivation_letters"
__lazy_modules["generate_motivation_letter"] = ".motivation_letters"
__lazy_modules["generate_motivation_letter_for_job"] = ".motivation_letters"
__lazy_modules["parse_letter_sections"] = ".motivation_letters"
__lazy_modules["validate_letter_claims"] = ".motivation_letters"
__lazy_modules["validate_section_evidence_refs"] = ".motivation_letters"
__lazy_modules["fetch_manual_jobs_from_file"] = ".manual_urls"
__lazy_modules["run_stage1_pipeline"] = ".acquisition"
__lazy_modules["run_stage2_pipeline"] = ".screening"
__lazy_modules["run_stage3_pipeline"] = ".prioritization"
__lazy_modules["run_stage4_pipeline"] = ".documents"
