from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping


DOCUMENT_TEXT_KEYS = {"cv_text", "document_text", "source_text", "workspace_cv_text"}
AGGREGATE_ASSET_KEYS = {"candidate_assets", "workspace_cv_asset"}


def candidate_document_id(*, asset_id: str = "", owner_kind: str = "", owner_id: str = "") -> str:
    normalized_asset_id = str(asset_id or "").strip()
    if normalized_asset_id:
        return f"asset:{normalized_asset_id}"
    return f"{str(owner_kind or 'document').strip()}:{str(owner_id or '').strip()}:cv"


def _asset_object_key(asset: Mapping[str, Any]) -> str:
    file_payload = dict(asset.get("file") or {})
    return str(file_payload.get("object_key") or asset.get("object_key") or "").strip()


def prepare_user_payload(payload: Mapping[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]] | None, list[dict[str, Any]]]:
    clean = deepcopy(dict(payload))
    metadata = dict(clean.get("metadata") or {})
    raw_assets = metadata.pop("candidate_assets", None)
    raw_cv_text = metadata.pop("cv_text", None)
    user_id = str(clean.get("user_id") or "").strip()
    assets: list[dict[str, Any]] | None = None
    documents: list[dict[str, Any]] = []

    if isinstance(raw_assets, list):
        assets = []
        for raw_asset in raw_assets:
            if not isinstance(raw_asset, Mapping):
                continue
            asset = deepcopy(dict(raw_asset))
            asset_metadata = dict(asset.get("metadata") or {})
            source_text = str(asset_metadata.pop("source_text", "") or "")
            asset["metadata"] = asset_metadata
            assets.append(asset)
            asset_id = str(asset.get("asset_id") or "").strip()
            if source_text and asset_id:
                documents.append(
                    {
                        "document_id": candidate_document_id(asset_id=asset_id),
                        "user_id": user_id,
                        "asset_id": asset_id,
                        "workspace_id": str(asset.get("workspace_id") or "").strip(),
                        "document_kind": str(asset.get("asset_kind") or "candidate_asset").strip(),
                        "object_key": _asset_object_key(asset),
                        "source_text": source_text,
                    }
                )
        metadata["candidate_asset_count"] = len(assets)

    cv_text = str(raw_cv_text or "")
    if cv_text:
        workspace_cv_assets = [
            asset
            for asset in assets or []
            if str(asset.get("asset_kind") or "").strip().lower() == "workspace_cv"
        ]
        matching_asset = next(
            (
                asset
                for asset in workspace_cv_assets
                if any(
                    document["asset_id"] == str(asset.get("asset_id") or "").strip()
                    and document["source_text"] == cv_text
                    for document in documents
                )
            ),
            workspace_cv_assets[-1] if workspace_cv_assets else None,
        )
        asset_id = str((matching_asset or {}).get("asset_id") or "").strip()
        document_id = candidate_document_id(asset_id=asset_id, owner_kind="user", owner_id=user_id)
        metadata["cv_document_id"] = document_id
        if not any(document["document_id"] == document_id for document in documents):
            documents.append(
                {
                    "document_id": document_id,
                    "user_id": user_id,
                    "asset_id": asset_id,
                    "workspace_id": "",
                    "document_kind": "workspace_cv",
                    "object_key": _asset_object_key(matching_asset or {}),
                    "source_text": cv_text,
                }
            )

    clean["metadata"] = metadata
    return clean, assets, documents


def prepare_workspace_payload(payload: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any] | None]:
    clean = deepcopy(dict(payload))
    settings = dict(clean.get("settings") or {})
    for key in AGGREGATE_ASSET_KEYS:
        settings.pop(key, None)
    metadata = dict(clean.get("metadata") or {})
    for key in AGGREGATE_ASSET_KEYS:
        metadata.pop(key, None)
    clean["metadata"] = metadata
    source_text = str(settings.pop("workspace_cv_text", "") or "")
    workspace_id = str(clean.get("id") or "").strip()
    asset_id = str(settings.get("workspace_cv_asset_id") or "").strip()
    document_id = candidate_document_id(asset_id=asset_id, owner_kind="workspace", owner_id=workspace_id)
    if source_text:
        settings["workspace_cv_document_id"] = document_id
    clean["settings"] = settings
    if not source_text:
        return clean, None
    return clean, {
        "workspace_id": workspace_id,
        "asset_id": asset_id,
        "document_id": document_id,
        "object_key": str(settings.get("workspace_cv_asset_object_key") or "").strip(),
        "source_text": source_text,
    }


def _strip_document_text_fields(value: Any, collected: list[str]) -> Any:
    if isinstance(value, Mapping):
        cleaned: dict[str, Any] = {}
        for key, item in value.items():
            normalized_key = str(key).strip().lower()
            if normalized_key in DOCUMENT_TEXT_KEYS:
                text = str(item or "")
                if text:
                    collected.append(text)
                continue
            if normalized_key in AGGREGATE_ASSET_KEYS:
                continue
            cleaned[str(key)] = _strip_document_text_fields(item, collected)
        return cleaned
    if isinstance(value, list):
        return [_strip_document_text_fields(item, collected) for item in value]
    if isinstance(value, tuple):
        return [_strip_document_text_fields(item, collected) for item in value]
    return deepcopy(value)


def prepare_run_payload(payload: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any] | None]:
    collected: list[str] = []
    clean = _strip_document_text_fields(payload, collected)
    if not collected:
        return clean, None
    run_plan = dict(clean.get("run_plan") or {})
    resolved = dict(run_plan.get("resolved_run_settings") or {})
    snapshot = dict(run_plan.get("workspace_snapshot") or {})
    snapshot_settings = dict(snapshot.get("settings") or {})
    asset_id = str(
        resolved.get("workspace_cv_asset_id")
        or snapshot_settings.get("workspace_cv_asset_id")
        or ""
    ).strip()
    run_id = str(clean.get("id") or "").strip()
    document_id = candidate_document_id(asset_id=asset_id, owner_kind="run", owner_id=run_id)
    resolved["workspace_cv_document_id"] = document_id
    run_plan["resolved_run_settings"] = resolved
    if snapshot:
        snapshot_settings["workspace_cv_document_id"] = document_id
        snapshot["settings"] = snapshot_settings
        run_plan["workspace_snapshot"] = snapshot
    clean["run_plan"] = run_plan
    return clean, {
        "run_id": run_id,
        "workspace_id": str(clean.get("workspace_id") or "").strip(),
        "asset_id": asset_id,
        "document_id": document_id,
        "object_key": str(
            resolved.get("workspace_cv_asset_object_key")
            or snapshot_settings.get("workspace_cv_asset_object_key")
            or ""
        ).strip(),
        "source_text": collected[0],
    }


__all__ = [
    "DOCUMENT_TEXT_KEYS",
    "candidate_document_id",
    "prepare_run_payload",
    "prepare_user_payload",
    "prepare_workspace_payload",
]
