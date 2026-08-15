from __future__ import annotations

from types import SimpleNamespace

from backend.api.routes import build_route_registry
from backend.api.routes.registry import ApiRouteContext
from backend.domain.models import UserRecord
from backend.master_cv.service import (
    add_bullet,
    add_entry,
    build_initial_document,
    export_document,
    get_bullet_guidance,
    get_document,
    improve_bullet,
    persist_document,
    select_relevant_bullets,
)


def _user(cv_text: str = "") -> UserRecord:
    return UserRecord.create(
        email="candidate@example.com",
        display_name="Candidate",
        metadata={
            "cv_text": cv_text,
            # The Master CV must not read or transform this legacy namespace.
            "candidate_evidence": [{"value": "legacy content"}],
        },
    )


def test_initial_master_cv_imports_uploaded_cv_into_its_own_document_model():
    user = _user(
        "Candidate\nProduct Manager\n\nExperience\n"
        "Senior Product Manager | Northstar | Berlin | 2023 - Present\n"
        "- Led onboarding redesign, reducing activation time by 34%.\n\n"
        "Projects\nInternal Marketplace\n- Built a matching prototype for hiring teams.\n"
    )

    document = build_initial_document(user)
    sections = {section["id"]: section for section in document["sections"]}

    assert sections["experience"]["entries"][0]["title"] == "Senior Product Manager"
    assert sections["experience"]["entries"][0]["bullets"][0]["extra"] is False
    assert sections["projects"]["entries"][0]["title"] == "Internal Marketplace"
    assert "legacy content" not in str(document)


def test_master_cv_mutations_are_durable_and_return_backend_guidance():
    user = _user()
    document, created = get_document(user)
    assert created is True
    document = add_entry(document, {"section_id": "experience", "title": "New role"})
    entry_id = document["sections"][0]["entries"][0]["id"]
    document = add_bullet(document, entry_id, {"text": "Built a workflow for the customer team."})
    bullet = document["sections"][0]["entries"][0]["bullets"][0]

    guidance = get_bullet_guidance(document, bullet["id"])
    improved = improve_bullet(document, bullet["id"])

    assert bullet["extra"] is True
    assert guidance["guidance"]["checks"][0]["state"] == "pass"
    assert improved["persisted"] is False
    assert improved["suggested_text"].startswith("Built a workflow")

    saved = []
    application = SimpleNamespace(
        repositories=SimpleNamespace(
            auth_repository=SimpleNamespace(upsert_user=lambda value: saved.append(value))
        )
    )
    public = persist_document(application, user, document)
    assert saved and saved[0] is user
    assert user.metadata["master_cv"]["revision"] == document["revision"]
    assert public["status"]["extraEvidenceCount"] == 1


def test_master_cv_exports_json_and_plain_text_without_evidence_fields():
    document = build_initial_document(_user())
    json_export = export_document(document, "json")
    text_export = export_document(document, "text")

    assert json_export["filename"] == "master-cv.json"
    assert '"sections"' in json_export["content"]
    assert text_export["filename"] == "master-cv.txt"
    assert "candidate_evidence" not in text_export["content"]


def test_master_cv_tailoring_ranks_only_grounded_master_cv_bullets():
    user = _user()
    document = build_initial_document(user)
    document = add_entry(document, {"section_id": "experience", "title": "Product role", "bullets": [
        {"text": "Led customer discovery workshops and improved activation by 20%"},
        {"text": "Managed an internal budget review"},
    ]})

    result = select_relevant_bullets(document, "customer discovery and activation", limit=5)

    assert result["grounding"] == "master_cv"
    assert result["generated_claims"] is False
    assert result["matches"][0]["bullet"]["text"].startswith("Led customer discovery")
    assert result["matches"][0]["matched_terms"]


def test_master_cv_api_routes_are_registered_as_a_separate_route_family():
    names = {route.name for route in build_route_registry()._routes}

    assert "master_cv.get" in names
    assert "master_cv.entries.create" in names
    assert "master_cv.bullets.create" in names
    assert not any("evidence" in name for name in names if name.startswith("master_cv"))


def test_master_cv_routes_persist_entry_and_bullet_mutations():
    user = _user()
    stored_users = []
    application = SimpleNamespace(
        repositories=SimpleNamespace(
            auth_repository=SimpleNamespace(upsert_user=lambda value: stored_users.append(value))
        )
    )

    class Handler:
        def __init__(self, body=None):
            self.body = body or {}
            self.response = None

        def _require_identity(self):
            return user, None

        def _read_json_body(self):
            return self.body

        def _send_json(self, payload, status=200, *, headers=None):
            self.response = (status, payload)

        def _send_error(self, status, code, message, *, details=None, headers=None):
            self.response = (status, {"code": code, "message": message})

    registry = build_route_registry()

    def dispatch(method, path, body=None):
        handler = Handler(body)
        context = ApiRouteContext(application, handler, method, tuple(path.strip("/").split("/")), {})
        assert registry.dispatch(context, auth_required=True) is True
        return handler.response

    status, loaded = dispatch("GET", "/master-cv")
    assert status == 200
    assert loaded["status"]["experienceCount"] == 0

    status, created = dispatch("POST", "/master-cv/entries", {"section_id": "experience", "title": "New role"})
    assert status == 201
    entry_id = created["sections"][0]["entries"][0]["id"]

    status, updated = dispatch("POST", f"/master-cv/entries/{entry_id}/bullets", {"text": "Built a customer workflow."})
    assert status == 201
    assert updated["status"]["extraEvidenceCount"] == 1
    assert stored_users[-1].metadata["master_cv"]["sections"][0]["entries"][0]["bullets"][0]["extra"] is True
