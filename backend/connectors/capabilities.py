"""Data-driven source connector capability descriptors."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from backend.connectors.ats_expansions import EXPANSION_CONNECTORS, build_capability_snapshot


# This is backend connector data, not UI policy.  API responses are built from
# these descriptors and the server-owned target manifest.
_CONNECTOR_CAPABILITIES: dict[str, dict[str, Any]] = {
    "greenhouse": {
        "access_method": "direct",
        "reliable_pagination": True,
        "supports_all_available": True,
        "safety_ceiling": 500,
        "max_pages": 20,
        "max_requests": 20,
    },
    "lever": {
        "access_method": "direct",
        "reliable_pagination": True,
        "supports_all_available": True,
        "safety_ceiling": 500,
        "max_pages": 20,
        "max_requests": 20,
    },
    "workday": {
        "access_method": "direct",
        "reliable_pagination": True,
        "supports_all_available": True,
        "safety_ceiling": 500,
        "max_pages": 10,
        "max_requests": 20,
    },
    "personio": {
        "access_method": "direct",
        "reliable_pagination": True,
        "supports_all_available": True,
        "safety_ceiling": 500,
        "max_pages": 10,
        "max_requests": 20,
    },
    "recruitee": {
        "access_method": "direct",
        "reliable_pagination": True,
        "supports_all_available": True,
        "safety_ceiling": 500,
        "max_pages": 10,
        "max_requests": 20,
    },
    "smartrecruiters": {
        "access_method": "direct",
        "reliable_pagination": True,
        "supports_all_available": True,
        "safety_ceiling": 500,
        "max_pages": 10,
        "max_requests": 20,
    },
    "generic_jsonld": {
        "access_method": "direct",
        "reliable_pagination": False,
        "supports_all_available": False,
        "safety_ceiling": 25,
        "max_pages": 1,
        "max_requests": 25,
    },
    "bounded_probe": {
        "access_method": "direct",
        "reliable_pagination": False,
        "supports_all_available": False,
        "safety_ceiling": 1,
        "max_pages": 1,
        "max_requests": 1,
    },
    "company_career_sites": {
        "access_method": "scrapeops",
        "reliable_pagination": False,
        "supports_all_available": False,
        "safety_ceiling": 25,
        "max_pages": 20,
        "max_requests": 100,
    },
}


def get_connector_capabilities(connector: str, *, target: dict[str, Any] | None = None) -> dict[str, Any]:
    normalized = str(connector or "").strip().casefold()
    descriptor = deepcopy(_CONNECTOR_CAPABILITIES.get(normalized, {
        "access_method": "direct",
        "reliable_pagination": False,
        "supports_all_available": False,
        "safety_ceiling": 25,
        "max_pages": 1,
        "max_requests": 1,
    }))
    if normalized in EXPANSION_CONNECTORS:
        expansion = build_capability_snapshot(normalized)
        descriptor["contract"] = expansion.get("capabilities") or {}
        descriptor["retry_policy"] = expansion.get("retry_policy") or {}
    target_capabilities = (target or {}).get("capabilities")
    if isinstance(target_capabilities, dict):
        descriptor.update(deepcopy(target_capabilities))
    descriptor["connector"] = normalized
    descriptor["retrieval_modes"] = [
        "bounded",
        "custom",
        *( ["all_available"] if descriptor.get("supports_all_available") else [] ),
    ]
    descriptor["reliable_pagination"] = bool(descriptor.get("reliable_pagination"))
    descriptor["supports_all_available"] = bool(
        descriptor.get("supports_all_available") and descriptor["reliable_pagination"]
    )
    descriptor["safety_ceiling"] = max(1, int(descriptor.get("safety_ceiling") or 25))
    return descriptor


__all__ = ["get_connector_capabilities"]
