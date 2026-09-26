from __future__ import annotations

from collections.abc import Mapping
from typing import Any


CV_GENERATION_MODE_STANDARD = "standard_cv"
CV_GENERATION_MODE_LIGHT = "light_customization"
CV_GENERATION_MODE_AGGRESSIVE = "aggressive_customization"

CV_GENERATION_MODE_OPTIONS = (
    CV_GENERATION_MODE_STANDARD,
    CV_GENERATION_MODE_LIGHT,
    CV_GENERATION_MODE_AGGRESSIVE,
)

DEFAULT_CV_GENERATION_MODE = CV_GENERATION_MODE_AGGRESSIVE
APPLIED_CV_ASSET_KIND = "applied_cv"
APPLIED_CV_DOCUMENT_TYPE = "Applied CV"
LIGHT_CUSTOMIZATION_EXTRA_PROMPT_FIELD = "light_customization_extra_prompt"
LIGHT_CUSTOMIZATION_PROMPT_OVERRIDE_FIELD = "light_customization_prompt_override"
AGGRESSIVE_CUSTOMIZATION_EXTRA_PROMPT_FIELD = "aggressive_customization_extra_prompt"
AGGRESSIVE_CUSTOMIZATION_PROMPT_OVERRIDE_FIELD = "aggressive_customization_prompt_override"
LEGACY_STAGE4_EXTRA_PROMPT_FIELD = "stage4_extra_prompt"
LEGACY_STAGE4_PROMPT_OVERRIDE_FIELD = "stage4_prompt_override"


def normalize_cv_generation_mode(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in CV_GENERATION_MODE_OPTIONS:
        return normalized
    return DEFAULT_CV_GENERATION_MODE


def cv_generation_mode_prompt_fields(value: Any) -> tuple[str, str]:
    normalized = normalize_cv_generation_mode(value)
    if normalized == CV_GENERATION_MODE_LIGHT:
        return (
            LIGHT_CUSTOMIZATION_EXTRA_PROMPT_FIELD,
            LIGHT_CUSTOMIZATION_PROMPT_OVERRIDE_FIELD,
        )
    return (
        AGGRESSIVE_CUSTOMIZATION_EXTRA_PROMPT_FIELD,
        AGGRESSIVE_CUSTOMIZATION_PROMPT_OVERRIDE_FIELD,
    )


def resolve_cv_generation_prompt_settings(
    value: Any,
    settings: Mapping[str, Any] | Any,
) -> tuple[str, str]:
    normalized = normalize_cv_generation_mode(value)
    if isinstance(settings, Mapping):
        getter = lambda key: settings.get(key)  # noqa: E731
    else:
        getter = lambda key: getattr(settings, key, "")  # noqa: E731

    extra_field, override_field = cv_generation_mode_prompt_fields(normalized)
    extra_prompt = str(getter(extra_field) or "").strip()
    prompt_override = str(getter(override_field) or "").strip()
    if normalized == CV_GENERATION_MODE_AGGRESSIVE:
        if not extra_prompt:
            extra_prompt = str(getter(LEGACY_STAGE4_EXTRA_PROMPT_FIELD) or "").strip()
        if not prompt_override:
            prompt_override = str(getter(LEGACY_STAGE4_PROMPT_OVERRIDE_FIELD) or "").strip()
    return extra_prompt, prompt_override


__all__ = [
    "AGGRESSIVE_CUSTOMIZATION_EXTRA_PROMPT_FIELD",
    "AGGRESSIVE_CUSTOMIZATION_PROMPT_OVERRIDE_FIELD",
    "APPLIED_CV_ASSET_KIND",
    "APPLIED_CV_DOCUMENT_TYPE",
    "CV_GENERATION_MODE_AGGRESSIVE",
    "CV_GENERATION_MODE_LIGHT",
    "CV_GENERATION_MODE_OPTIONS",
    "CV_GENERATION_MODE_STANDARD",
    "DEFAULT_CV_GENERATION_MODE",
    "LEGACY_STAGE4_EXTRA_PROMPT_FIELD",
    "LEGACY_STAGE4_PROMPT_OVERRIDE_FIELD",
    "LIGHT_CUSTOMIZATION_EXTRA_PROMPT_FIELD",
    "LIGHT_CUSTOMIZATION_PROMPT_OVERRIDE_FIELD",
    "cv_generation_mode_prompt_fields",
    "normalize_cv_generation_mode",
    "resolve_cv_generation_prompt_settings",
]
