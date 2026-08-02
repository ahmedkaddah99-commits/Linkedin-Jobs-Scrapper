from __future__ import annotations

from http import HTTPStatus
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlparse, urlsplit, urlunsplit

from backend.api.routes.assisted_apply import (
    _authenticate_extension_session,
    _read_strict_object,
)
from backend.api.routes.registry import ApiRouteContext, RouteRegistry
from backend.domain import normalize_candidate_asset_descriptor

_CREATE_PACKAGE_KEYS = {"job", "answers", "documents", "warnings"}
_PREPARE_PACKAGE_KEYS = {"run_id", "job_id", "document_ids", "confirm_standard_profile"}
_BIND_PACKAGE_KEYS = {"binding_id"}
_DOCUMENT_GRANT_KEYS = {"package_id", "document_id", "adapter", "upload_field_intent"}
_CORRECTION_KEYS = {"package_id", "field_intent", "corrected_value", "scope"}
_OUTCOME_KEYS = {
    "package_id", "package_version", "adapter", "adapter_version",
    "evidence_category", "decision", "uploaded_documents",
}


def register_routes(registry: RouteRegistry) -> None:
    # Web (Clerk-authenticated)
    registry.exact(
        "POST",
        ("assisted-apply", "packages"),
        _create_package,
        auth_required=True,
        name="assisted_apply.packages.create",
    )
    registry.exact(
        "POST",
        ("assisted-apply", "packages", "prepare"),
        _prepare_package,
        auth_required=True,
        name="assisted_apply.packages.prepare",
    )
    registry.exact(
        "POST",
        ("assisted-apply", "packages", "launch"),
        _launch_package,
        auth_required=True,
        name="assisted_apply.packages.launch",
    )

    # Extension (session-authenticated)
    registry.exact(
        "POST",
        ("assisted-apply", "extension", "packages", "bind"),
        _bind_package,
        auth_required=False,
        name="assisted_apply.extension.packages.bind",
    )
    registry.exact(
        "GET",
        ("assisted-apply", "extension", "packages"),
        _get_package_for_extension,
        auth_required=False,
        name="assisted_apply.extension.packages.get",
    )
    registry.exact(
        "POST",
        ("assisted-apply", "extension", "packages"),
        _get_package_for_extension_post,
        auth_required=False,
        name="assisted_apply.extension.packages.post",
    )
    registry.exact(
        "POST",
        ("assisted-apply", "extension", "document-grants"),
        _create_document_grant,
        auth_required=False,
        name="assisted_apply.extension.document_grants.create",
    )
    registry.exact(
        "POST",
        ("assisted-apply", "extension", "document-grants", "download"),
        _download_document_grant,
        auth_required=False,
        name="assisted_apply.extension.document_grants.download",
    )
    registry.exact(
        "POST",
        ("assisted-apply", "extension", "corrections"),
        _save_correction,
        auth_required=False,
        name="assisted_apply.extension.corrections.create",
    )
    registry.exact(
        "POST",
        ("assisted-apply", "extension", "application-outcomes"),
        _respond_to_application_outcome,
        auth_required=False,
        name="assisted_apply.extension.application_outcomes.create",
    )


def _create_package(context: ApiRouteContext) -> None:
    user, _ = context.require_clerk_identity()
    payload = _read_strict_object(
        context,
        allowed_keys=_CREATE_PACKAGE_KEYS,
        label="application package",
    )
    package = context.application.create_application_package(
        user_id=user.user_id,
        job=payload.get("job") or {},
        answers=payload.get("answers"),
        documents=payload.get("documents"),
        warnings_items=payload.get("warnings"),
    )
    context.send_json(package.to_extension_payload(), status=HTTPStatus.CREATED)


def _supported_portal(url: str, declared_portal: object) -> str:
    normalized_url = str(url or "").strip()
    parsed = urlparse(normalized_url)
    hostname = (parsed.hostname or "").casefold()
    if parsed.scheme != "https":
        return ""
    # Keep server-side eligibility aligned with the extension's optional
    # host permissions. The declared ATS is not authority to access a URL.
    if hostname == "boards.greenhouse.io":
        return "greenhouse"
    if hostname.endswith(".lever.co"):
        return "lever"
    return ""


def _canonical_application_form_url(url: str, portal: str) -> str:
    """Freeze the provider's deterministic application-form URL in the package."""
    normalized_url = str(url or "").strip()
    if portal != "lever":
        return normalized_url
    parsed = urlsplit(normalized_url)
    path = parsed.path.rstrip("/")
    if not path.casefold().endswith("/apply"):
        path = f"{path}/apply"
    return urlunsplit((parsed.scheme, parsed.netloc, path, parsed.query, ""))


def _owned_job_for_package(context: ApiRouteContext, *, user: Any, run_id: str, job_id: str) -> Any:
    run = context.application.get_run(run_id)
    if not context.application.user_can_access_run(user, run):
        raise PermissionError("You do not have access to this application run.")
    for job_set in context.application.list_job_sets(run.id).values():
        for job in job_set:
            if str(getattr(job, "job_id", "")).strip() == job_id:
                return job
    raise ValueError("The requested job was not found in this run.")


def _ready_career_memory(context: ApiRouteContext, user: Any) -> tuple[Any | None, dict[str, Any]]:
    """Return the newest approved Career Memory profile and its source CV profile."""
    profiles = context.application.list_career_profiles(user_id=user.user_id)
    career_profile = next(
        (item for item in profiles if str(getattr(item, "status", "")) == "ready_for_tailoring"),
        None,
    )
    if career_profile is None:
        return None, {}

    profile_metadata = dict(getattr(career_profile, "metadata", {}) or {})
    source_asset_ids = [
        str(item).strip()
        for item in profile_metadata.get("source_asset_ids") or []
        if str(item).strip()
    ]
    baseline_asset_id = str(getattr(career_profile, "baseline_cv_asset_id", "") or "").strip()
    if baseline_asset_id and baseline_asset_id not in source_asset_ids:
        source_asset_ids.insert(0, baseline_asset_id)

    assets = {
        str(item.get("asset_id") or "").strip(): normalize_candidate_asset_descriptor(item)
        for item in dict(getattr(user, "metadata", {}) or {}).get("candidate_assets") or []
        if isinstance(item, Mapping)
    }
    for asset_id in source_asset_ids:
        metadata = dict((assets.get(asset_id) or {}).get("metadata") or {})
        parsed_profile = metadata.get("parsed_profile")
        if isinstance(parsed_profile, Mapping) and parsed_profile:
            return career_profile, dict(parsed_profile)
    return career_profile, {}


def _profile_package_sections(
    context: ApiRouteContext,
    user: Any,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    """Build approved package sections from explicit profile facts and ready Career Memory."""
    profile = dict(getattr(user, "metadata", {}) or {}).get("profile") or {}
    profile = dict(profile) if isinstance(profile, Mapping) else {}
    career_profile, parsed_profile = _ready_career_memory(context, user)
    career_metadata = dict(getattr(career_profile, "metadata", {}) or {}) if career_profile else {}
    provenance = (
        f"career_profile:{career_profile.profile_id}"
        if career_profile is not None
        else "user_profile"
    )

    full_name = str(
        profile.get("legal_name")
        or profile.get("full_name")
        or profile.get("name")
        or parsed_profile.get("name")
        or getattr(user, "display_name", "")
        or ""
    ).strip()
    name_parts = full_name.split(maxsplit=1)
    first_name = str(profile.get("first_name") or (name_parts[0] if name_parts else "")).strip()
    last_name = str(profile.get("last_name") or (name_parts[1] if len(name_parts) > 1 else "")).strip()
    email = str(profile.get("email") or parsed_profile.get("email") or getattr(user, "email", "") or "").strip()
    phone = str(profile.get("phone") or profile.get("phone_number") or "").strip()
    location = str(profile.get("location") or parsed_profile.get("location") or "").strip()
    linkedin_url = str(profile.get("linkedin_url") or parsed_profile.get("linkedin_url") or "").strip()
    github_url = str(profile.get("github_url") or parsed_profile.get("github_url") or "").strip()
    website = str(profile.get("website") or parsed_profile.get("website") or "").strip()
    summary = str(profile.get("summary") or parsed_profile.get("summary") or "").strip()
    def string_values(value: object) -> list[str]:
        raw_values = value if isinstance(value, (list, tuple, set)) else [value]
        return [str(item).strip() for item in raw_values if str(item or "").strip()]

    skills_values = string_values(profile.get("competencies") or profile.get("skills") or parsed_profile.get("competencies") or [])
    language_values = string_values(profile.get("languages") or parsed_profile.get("languages") or [])
    skills_text = ", ".join(str(item).strip() for item in skills_values if str(item).strip())
    languages_text = ", ".join(str(item).strip() for item in language_values if str(item).strip())

    raw_experiences = [
        dict(item)
        for item in career_metadata.get("work_experiences") or []
        if isinstance(item, Mapping) and str(item.get("status") or "active") == "active"
    ]
    current_experience = next(
        (
            item for item in raw_experiences
            if str(item.get("end_date") or "").strip().casefold() in {"", "current", "present", "now"}
        ),
        None,
    )
    current_company = str((current_experience or {}).get("employer") or "").strip()
    current_title = str((current_experience or {}).get("job_title") or "").strip()

    values = [
        ("candidate.first_name", "First name", first_name, "standard"),
        ("candidate.last_name", "Last name", last_name, "standard"),
        ("candidate.full_name", "Full name", full_name, "standard"),
        ("candidate.email", "Email", email, "standard"),
        ("candidate.phone", "Phone", phone, "personal"),
        ("candidate.location", "Current location", location, "standard"),
        ("candidate.current_company", "Current company", current_company, "standard"),
        ("candidate.current_title", "Current title", current_title, "standard"),
        ("candidate.linkedin_url", "LinkedIn URL", linkedin_url, "standard"),
        ("candidate.github_url", "GitHub URL", github_url, "standard"),
        ("candidate.website", "Website", website, "standard"),
        ("candidate.professional_summary", "Professional summary", summary, "standard"),
        ("candidate.skills", "Skills", skills_text, "standard"),
        ("candidate.languages", "Languages", languages_text, "standard"),
    ]
    answers = [
        {
            "field_intent": field_intent,
            "label": label,
            "proposed_value": value,
            "source": "profile_verified",
            "sensitivity": sensitivity,
            "scope": "global",
            "confidence": 1.0,
            "requires_review": False,
            "provenance": provenance,
            "reasons": ["Confirmed by the candidate in Runr before launch."],
        }
        for field_intent, label, value, sensitivity in values
        if value
    ]
    candidate = {
        "first_name": first_name,
        "last_name": last_name,
        "full_name": full_name,
        "email": email,
        "phone": phone,
        "source": "confirmed_career_memory" if career_profile else "confirmed_user_profile",
        "approved": True,
        "provenance": provenance,
    }
    experiences: list[dict[str, Any]] = []
    for item in raw_experiences:
        experience_id = str(item.get("experience_id") or "").strip()
        description = str(item.get("description") or "").strip()
        bullets = []
        if description:
            bullets.append(
                {
                    "bullet_id": f"{experience_id}:description" if experience_id else "",
                    "text": description,
                    "approved_text": description,
                    "source_experience_id": experience_id,
                    "provenance_id": f"{provenance}:{experience_id}" if experience_id else provenance,
                    "approved": True,
                }
            )
        period = " - ".join(
            part for part in (
                str(item.get("start_date") or "").strip(),
                str(item.get("end_date") or "Present").strip(),
            ) if part
        )
        experiences.append(
            {
                "source_experience_id": experience_id,
                "role_title": str(item.get("job_title") or "").strip(),
                "company": str(item.get("employer") or "").strip(),
                "period": period,
                "location": str(item.get("location") or "").strip(),
                "bullets": bullets,
                "generation_provenance": {"source": "career_memory", "profile_id": str(getattr(career_profile, "profile_id", ""))},
                "provenance_confidence": "full" if experience_id else "reduced",
            }
        )
    education = [
        {
            "institution": str(item.get("institution") or "").strip(),
            "degree": str(item.get("degree") or item.get("degree_title") or "").strip(),
            "period": str(item.get("period") or "").strip(),
            "provenance": provenance,
            "confirmed": True,
        }
        for item in parsed_profile.get("education") or []
        if isinstance(item, Mapping) and (str(item.get("institution") or "").strip() or str(item.get("degree") or item.get("degree_title") or "").strip())
    ]
    skills = [
        {"value": str(item).strip(), "provenance": provenance, "confirmed": True}
        for item in skills_values if str(item).strip()
    ]
    languages = [
        {"value": str(item).strip(), "provenance": provenance, "confirmed": True}
        for item in language_values if str(item).strip()
    ]

    warnings = []
    if not answers:
        warnings.append("No confirmed standard profile facts are available; complete the fields manually.")
    if not email:
        warnings.append("No email is saved in your Runr profile.")
    return candidate, answers, experiences, education, skills, languages, warnings


def _selected_candidate_documents(user: Any, document_ids: object) -> list[dict[str, Any]]:
    requested = [str(item).strip() for item in document_ids or [] if str(item).strip()]
    if len(requested) != len(set(requested)):
        raise ValueError("Each selected document may be used only once.")
    if not requested:
        return []
    if not all(item.startswith("asset::") for item in requested):
        raise ValueError("Only documents from your Runr document library may be selected.")
    raw_assets = dict(getattr(user, "metadata", {}) or {}).get("candidate_assets") or []
    assets = {
        str(asset.get("asset_id") or "").strip(): normalize_candidate_asset_descriptor(asset)
        for asset in raw_assets
        if isinstance(asset, Mapping)
    }
    selected: list[dict[str, Any]] = []
    role_by_kind = {
        "workspace_cv": "cv",
        "cover_letter": "cover_letter",
        "motivation_letter": "cover_letter",
        "uploaded_document": "supporting_document",
        "certification": "supporting_document",
        "recommendation_letter": "supporting_document",
        "degree_diploma": "supporting_document",
        "academic_transcript": "supporting_document",
        "language_certificate": "supporting_document",
        "employment_certificate": "supporting_document",
        "portfolio_work_sample": "supporting_document",
        "other_supporting_document": "supporting_document",
    }
    for document_id in requested:
        asset_id = document_id.removeprefix("asset::")
        asset = assets.get(asset_id)
        if asset is None:
            raise PermissionError("A selected document is not available in your Runr library.")
        if str(asset.get("asset_kind") or "").strip().casefold() == "identity_work_authorization":
            raise ValueError("Identity / Work Authorization documents cannot be attached automatically.")
        purposes = set(dict(asset.get("metadata") or {}).get("purposes") or [])
        if "private_never_attach" in purposes or "include_in_applications" not in purposes:
            raise ValueError("This Career Asset is not approved for application inclusion.")
        file_payload = dict(asset.get("file") or {})
        metadata = dict(asset.get("metadata") or {})
        object_key = str(file_payload.get("object_key") or "").strip()
        mime_type = str(file_payload.get("mime_type") or "").strip().casefold()
        path_filename = Path(str(file_payload.get("path") or "")).name
        display_name = str(asset.get("display_name") or "").strip()
        filename = display_name if Path(display_name).suffix.casefold() in {".pdf", ".docx"} else path_filename
        filename = str(filename or display_name).strip()
        document_kind = role_by_kind.get(str(asset.get("asset_kind") or "").strip().casefold(), "")
        asset_status = str(metadata.get("status") or "ready").strip().casefold()
        if (
            document_kind == "cv"
            and asset_status == "ready"
            and mime_type in {"", "application/octet-stream"}
            and filename.casefold().endswith(".docx")
        ):
            mime_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        extension = ".pdf" if mime_type == "application/pdf" else ".docx" if mime_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document" else ""
        if not object_key or not document_kind or not extension or not filename.casefold().endswith(extension):
            raise ValueError("A selected document is not a supported PDF or DOCX application document.")
        selected.append(
            {
                "document_id": document_id,
                "document_version": max(1, int(metadata.get("version") or 1)),
                "document_kind": document_kind,
                "asset_id": asset_id,
                "object_key": object_key,
                "mime_type": mime_type,
                "file_name": filename,
                "sha256_hex": str(metadata.get("content_sha256") or "").strip(),
            }
        )
    return selected


def _prepare_package(context: ApiRouteContext) -> None:
    user, _ = context.require_clerk_identity()
    payload = _read_strict_object(
        context,
        allowed_keys=_PREPARE_PACKAGE_KEYS,
        label="prepared application package",
    )
    if payload.get("confirm_standard_profile") is not True:
        raise ValueError("Confirm your standard profile facts before launching Assisted Apply.")
    run_id = str(payload.get("run_id") or "").strip()
    job_id = str(payload.get("job_id") or "").strip()
    if not run_id or not job_id:
        raise ValueError("run_id and job_id are required.")
    job = _owned_job_for_package(context, user=user, run_id=run_id, job_id=job_id)
    application_url = str(
        getattr(job, "apply_link", "") or getattr(job, "link", "") or getattr(job, "source_url", "") or ""
    ).strip()
    portal = _supported_portal(application_url, getattr(job, "portal", ""))
    if not portal:
        raise ValueError("Assisted Apply currently supports Greenhouse and Lever application links only.")
    application_url = _canonical_application_form_url(application_url, portal)
    candidate, answers, experiences, education, skills, languages, warnings = _profile_package_sections(context, user)
    documents = _selected_candidate_documents(user, payload.get("document_ids") or [])
    package = context.application.create_application_package(
        user_id=user.user_id,
        job={
            "job_id": job_id,
            "title": str(getattr(job, "title", "") or ""),
            "company": str(getattr(job, "company", "") or ""),
            "portal": portal,
            "url": application_url,
            "location": str(getattr(job, "location_raw", "") or ""),
        },
        answers=answers,
        documents=documents,
        warnings_items=warnings,
        candidate=candidate,
        experiences=experiences,
        education=education,
        skills=skills,
        languages=languages,
    )
    context.send_json(
        {
            "package_id": package.package_id,
            "application_url": application_url,
            "portal": portal,
            "document_count": len(documents),
            "warning_count": len(warnings),
        },
        status=HTTPStatus.CREATED,
    )


def _launch_package(context: ApiRouteContext) -> None:
    user, _ = context.require_clerk_identity()
    payload = _read_strict_object(
        context,
        allowed_keys={"package_id"},
        label="package launch",
    )
    package = context.application.launch_application_package(
        user_id=user.user_id,
        package_id=str(payload.get("package_id") or "").strip(),
    )
    context.send_json(
        {
            "package_id": package.package_id,
            "binding_id": package.launch_tab_binding_id,
            "binding_expires_at": package.launch_tab_binding_expires_at,
            "status": package.status,
        },
        status=HTTPStatus.OK,
    )


def _bind_package(context: ApiRouteContext) -> None:
    payload = _read_strict_object(
        context,
        allowed_keys=_BIND_PACKAGE_KEYS,
        label="package bind",
    )
    package = context.application.bind_application_package(
        binding_id=str(payload.get("binding_id") or "").strip(),
        extension_origin=context.request_client_origin(),
    )
    context.send_json(package.to_extension_payload(), status=HTTPStatus.OK)


def _get_package_for_extension(context: ApiRouteContext) -> None:
    user, _connection = _authenticate_extension_session(context)
    package_id = str(
        list(context.query.get("package_id") or [""])[0]
    ).strip()
    if not package_id:
        raise ValueError("package_id query parameter is required.")
    _send_package_for_extension(context, package_id)


def _get_package_for_extension_post(context: ApiRouteContext) -> None:
    _authenticate_extension_session(context)
    payload = _read_strict_object(
        context,
        allowed_keys={"package_id"},
        label="application package lookup",
    )
    package_id = str(payload.get("package_id") or "").strip()
    if not package_id:
        raise ValueError("package_id is required.")
    _send_package_for_extension(context, package_id, bind_launched=True)


def _send_package_for_extension(
    context: ApiRouteContext,
    package_id: str,
    *,
    bind_launched: bool = False,
) -> None:
    get_package = (
        context.application.get_or_bind_application_package_for_extension
        if bind_launched
        else context.application.get_application_package_for_extension
    )
    payload = get_package(
        package_id=package_id,
        raw_session=context.bearer_token(),
        extension_origin=context.request_client_origin(),
    )
    context.send_json(payload, status=HTTPStatus.OK)


def _create_document_grant(context: ApiRouteContext) -> None:
    payload = _read_strict_object(
        context,
        allowed_keys=_DOCUMENT_GRANT_KEYS,
        label="document grant",
    )
    result = context.application.create_assisted_apply_document_grant(
        package_id=str(payload.get("package_id") or "").strip(),
        document_id=str(payload.get("document_id") or "").strip(),
        adapter=str(payload.get("adapter") or "").strip(),
        upload_field_intent=str(payload.get("upload_field_intent") or "").strip(),
        raw_session=context.bearer_token(),
        extension_origin=context.request_client_origin(),
    )
    context.send_json(result, status=HTTPStatus.CREATED)


def _download_document_grant(context: ApiRouteContext) -> None:
    _read_strict_object(context, allowed_keys=set(), label="document download")
    file_bytes, metadata = context.application.consume_assisted_apply_document_grant(
        raw_grant=str(context.handler.headers.get("X-Runr-Document-Grant") or "").strip(),
        raw_session=context.bearer_token(),
        extension_origin=context.request_client_origin(),
    )
    context.send_bytes(
        file_bytes,
        content_type=metadata["mimeType"],
        download_name=metadata["fileName"],
    )


def _save_correction(context: ApiRouteContext) -> None:
    payload = _read_strict_object(
        context,
        allowed_keys=_CORRECTION_KEYS,
        label="application correction",
    )
    result = context.application.save_assisted_apply_correction(
        package_id=str(payload.get("package_id") or "").strip(),
        field_intent=str(payload.get("field_intent") or "").strip(),
        corrected_value=str(payload.get("corrected_value") or "").strip(),
        scope=str(payload.get("scope") or "").strip(),
        raw_session=context.bearer_token(),
        extension_origin=context.request_client_origin(),
    )
    context.send_json(result, status=HTTPStatus.CREATED if result["persisted"] else HTTPStatus.OK)


def _respond_to_application_outcome(context: ApiRouteContext) -> None:
    payload = _read_strict_object(
        context,
        allowed_keys=_OUTCOME_KEYS,
        label="application outcome",
    )
    raw_documents = payload.get("uploaded_documents") or []
    if not isinstance(raw_documents, list) or not all(
        isinstance(item, dict) and set(item) == {"document_id", "document_version"}
        for item in raw_documents
    ):
        raise ValueError("uploaded_documents must be an array of document references.")
    result = context.application.respond_to_assisted_apply_outcome(
        package_id=str(payload.get("package_id") or "").strip(),
        package_version=int(payload.get("package_version") or 0),
        adapter=str(payload.get("adapter") or "").strip(),
        adapter_version=str(payload.get("adapter_version") or "").strip(),
        evidence_category=str(payload.get("evidence_category") or "").strip(),
        decision=str(payload.get("decision") or "").strip(),
        uploaded_documents=raw_documents,
        raw_session=context.bearer_token(),
        extension_origin=context.request_client_origin(),
    )
    context.send_json(result, status=HTTPStatus.CREATED if result["created"] else HTTPStatus.OK)
