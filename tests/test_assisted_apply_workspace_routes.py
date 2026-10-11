from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from backend.api.routes import assisted_apply_workspace as routes
from backend.api.routes.registry import ApiRouteContext


@contextmanager
def request(payload, *, metadata=None):
    user = SimpleNamespace(user_id="owner", metadata=metadata or {})
    app = SimpleNamespace(get_user=Mock(return_value=user), repositories=SimpleNamespace(
        auth_repository=SimpleNamespace(upsert_user=Mock())))
    handler = SimpleNamespace(_read_json_body=lambda: payload, _send_json=Mock(), _send_error=Mock())
    context = ApiRouteContext(app, handler, "POST", (), {})
    with patch.object(routes, "_authenticate_extension_session", return_value=(user, object())):
        yield context, handler, app, user


def test_unauthenticated_request_never_reads_library():
    with request({}) as (context, _, _, _), patch.object(
        routes, "_authenticate_extension_session", side_effect=PermissionError("expired")
    ), patch("backend.api.server._collect_document_entries") as collect:
        with pytest.raises(PermissionError):
            routes._library(context)
        collect.assert_not_called()


def test_library_excludes_private_assets_and_unusable_files():
    documents = [
        {"document_id": "asset::ok", "display_name": "Resume.pdf", "asset_kind": "workspace_cv"},
        {"document_id": "asset::private", "display_name": "Private.pdf", "asset_kind": "workspace_cv"},
        {"document_id": "asset::text", "display_name": "Resume.txt", "asset_kind": "workspace_cv"},
    ]
    assets = [{"asset_id": "ok", "metadata": {"purposes": ["include_in_applications"]}},
              {"asset_id": "private", "metadata": {"purposes": ["private_never_attach"]}}]
    with request({}) as (context, handler, _, _), patch(
        "backend.api.server._collect_document_entries", return_value=documents
    ), patch("backend.api.server._load_candidate_assets", return_value=assets):
        routes._library(context)
        assert [row["id"] for row in handler._send_json.call_args.args[0]["documents"]] == ["asset::ok"]


def test_download_cannot_bypass_private_asset_filter():
    with request({"document_id": "asset::private"}) as (context, _, _, _), patch(
        "backend.api.server._find_document_entry", return_value={"document_id": "asset::private",
            "display_name": "Private.pdf", "asset_kind": "workspace_cv"}
    ), patch("backend.api.server._load_candidate_assets", return_value=[{
        "asset_id": "private", "metadata": {"purposes": ["include_in_applications", "private_never_attach"]}
    }]), patch("backend.api.server._resolve_document_selection") as resolve:
        with pytest.raises(ValueError):
            routes._document(context)
        resolve.assert_not_called()


def test_download_uses_owned_export_resolver_and_preserves_bytes():
    with TemporaryDirectory() as directory:
        path = Path(directory) / "resume.pdf"
        path.write_bytes(b"%PDF-1.4 test")
        with request({"document_id": "artifact::run::cv"}) as (context, handler, app, user), patch(
            "backend.api.server._find_document_entry", return_value={"document_id": "artifact::run::cv",
                "display_name": "Resume.pdf", "document_type": "Tailored CV"}
        ), patch("backend.api.server._resolve_document_selection", return_value=(str(path), "Resume.pdf")) as resolve:
            routes._document(context)
            resolve.assert_called_once_with(app, user, "artifact::run::cv")
            import base64
            assert base64.b64decode(handler._send_json.call_args.args[0]["base64"]) == path.read_bytes()


def test_generation_gets_server_profile_facts_not_client_supplied_candidate():
    payload = {"kind": "answer", "description": "Platform engineer", "question": "Why this role?", "instructions": "Concise"}
    with request(payload) as (context, handler, _, _), patch(
        "backend.api.routes.assisted_apply_packages._profile_package_sections",
        return_value=({"full_name": "Confirmed Candidate"}, [], [{"company": "Confirmed employer"}], [], [], [], [])
    ), patch.object(routes, "generate_draft", return_value="Draft answer") as generate:
        routes._draft(context)
        assert generate.call_args.kwargs["facts"]["candidate"]["full_name"] == "Confirmed Candidate"
        assert handler._send_json.call_args.args[0] == {"text": "Draft answer"}
    with request({**payload, "candidate": {"name": "Invented"}}) as (context, _, _, _):
        with pytest.raises(ValueError, match="Unsupported"):
            routes._draft(context)


def test_reviewed_answer_persistence_preserves_profile_and_replaces_exact_question():
    with request({"question": "Notice?", "text": "One month"}, metadata={"profile": {"name": "Existing"},
        "assisted_apply_reviewed_answers": [{"question": "Notice?", "text": "Old"}]}) as (context, _, app, user):
        routes._save_answer(context)
        assert user.metadata["profile"] == {"name": "Existing"}
        assert user.metadata["assisted_apply_reviewed_answers"] == [{"question": "Notice?", "text": "One month"}]
        app.repositories.auth_repository.upsert_user.assert_called_once()


def test_reviewed_document_is_real_docx_and_not_saved_until_requested():
    from io import BytesIO
    from zipfile import ZipFile
    with request({"kind": "cover_letter", "name": "../Application letter", "text": "Reviewed letter text"}) as (context, handler, _, _), patch(
        "backend.api.server._store_candidate_asset_upload", return_value={"asset_id": "saved"}
    ) as store:
        routes._save_document(context)
        kwargs = store.call_args.kwargs
        assert kwargs["filename"] == "Application letter.docx"
        assert kwargs["asset_kind"] == "cover_letter"
        with ZipFile(BytesIO(kwargs["file_bytes"])) as document:
            assert "Reviewed letter text" in document.read("word/document.xml").decode()
        assert handler._send_json.call_args.args[0]["document"]["id"] == "asset::saved"


def test_report_receipt_is_persisted_and_inbox_requires_admin():
    with request({"description": "Upload missing", "hostname": "example.com", "provider": "avature", "role": "Engineer"}) as (context, handler, app, user):
        routes._report(context)
        receipt = handler._send_json.call_args.args[0]["receipt"]
        assert user.metadata["assisted_apply_support_reports"][0]["id"] == receipt
        handler._require_admin = Mock(side_effect=PermissionError("admin required"))
        app.list_users = Mock(return_value=[user])
        with pytest.raises(PermissionError):
            routes._support_inbox(context)
        app.list_users.assert_not_called()
        handler._require_admin = Mock(return_value=True)
        routes._support_inbox(context)
        assert handler._send_json.call_args.args[0]["reports"][0]["userId"] == "owner"


def test_saved_document_round_trip_through_real_storage_and_owned_library(tmp_path, monkeypatch):
    from backend import create_backend
    monkeypatch.setenv("DATABASE_BACKEND", "sqlite")
    monkeypatch.setenv("RUNR_ENV", "test")
    monkeypatch.setenv("TURSO_DATABASE_URL", "")
    monkeypatch.setenv("TURSO_AUTH_TOKEN", "")
    monkeypatch.setenv("OBJECT_STORAGE_BACKEND", "local")
    monkeypatch.setenv("OBJECT_STORAGE_LOCAL_ROOT", str(tmp_path / "objects"))
    monkeypatch.setenv("RUNR_INTERNAL_OBJECT_STORAGE_LOCAL_ROOT", "")
    app = create_backend(tmp_path, storage_backend="sqlite")
    user = app.upsert_user({"email": "workspace-owner@example.com", "display_name": "Owner"})
    other = app.upsert_user({"email": "workspace-other@example.com", "display_name": "Other"})
    handler = SimpleNamespace(_read_json_body=Mock(), _send_json=Mock())
    context = ApiRouteContext(app, handler, "POST", (), {})
    with patch.object(routes, "_authenticate_extension_session", side_effect=lambda _: (app.get_user(user.user_id), object())), patch(
        "backend.api.routes.assisted_apply_packages._require_runr_pro"
    ):
        handler._read_json_body.return_value = {"kind": "cv", "name": "My reviewed resume", "text": "Owner\nPlatform engineer\nReviewed experience"}
        routes._save_document(context)
        document_id = handler._send_json.call_args.args[0]["document"]["id"]
        handler._read_json_body.return_value = {}
        routes._library(context)
        assert document_id in [row["id"] for row in handler._send_json.call_args.args[0]["documents"]]
        handler._read_json_body.return_value = {"document_id": document_id}
        routes._document(context)
        import base64
        assert base64.b64decode(handler._send_json.call_args.args[0]["base64"]).startswith(b"PK")
    with patch.object(routes, "_authenticate_extension_session", return_value=(other, object())), patch(
        "backend.api.routes.assisted_apply_packages._require_runr_pro"
    ), pytest.raises(KeyError):
        routes._document(context)
