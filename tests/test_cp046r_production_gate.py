from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from backend.api.routes import build_route_registry
from backend.capabilities.source_processing.pipeline import process_sources_and_extract_evidence


def test_deterministic_extraction_uses_the_real_gemini_provider_boundary():
    response = MagicMock()
    response.text = json.dumps({
        "extracted_text": (
            "Operations Analyst at Acme GmbH\n"
            "Automated monthly reporting and reduced preparation time by 40%."
        ),
        "layout_sections": [],
        "experience_details": [],
        "confidence": 0.96,
        "warnings": [],
    })
    with patch("backend.profiles.gemini_extraction._build_client") as build_client:
        build_client.return_value.models.generate_content.return_value = response
        result = process_sources_and_extract_evidence([{
            "asset_id": "asset_prod_001",
            "file_name": "baseline-cv.txt",
            "file_bytes": b"real source bytes for the production-path gate",
        }])

    build_client.return_value.models.generate_content.assert_called_once()
    assert result["status"] == "completed"
    assert result["sources"][0]["provider"] == "gemini"
    assert result["evidence"]


def test_obsolete_fixture_control_routes_are_not_registered_in_production():
    route_names = {route.name for route in build_route_registry()._routes}
    assert not any(name.startswith("career_evidence_fixture.") for name in route_names)


def test_fixed_journey_routes_precede_generic_evidence_id_route():
    registry = build_route_registry()
    for segments, expected_name in (
        (("evidence-items", "journey-state"), "evidence_items.journey_state"),
        (("evidence-items", "next-review"), "evidence_items.next_review"),
        (("evidence-items", "ready-actions"), "evidence_items.ready_actions"),
    ):
        matches = [
            route.name
            for route in registry._routes
            if route.auth_required and route.matches("GET", segments)
        ]
        assert matches
        assert matches[0] == expected_name
