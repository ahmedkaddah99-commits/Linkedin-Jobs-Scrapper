from runr_automation.tickets import normalize_ticket_payload


def test_canonical_markdown_ticket_becomes_executable_fields() -> None:
    payload = {
        "title": "Write bounded artifact",
        "description": """
## Primary subsystem
smoke

## Allowed paths
- allowed/result.txt

## Minimal required reading
- README.md

## Acceptance criteria
- The result file exists.
- The focused test passes.

## Safe local verification commands
- .venv\\Scripts\\python.exe -m pytest -q tests/test_result.py
""",
        "labels": {"nodes": [{"name": "WS-01 Smoke", "parent": {"name": "Subsystem"}}]},
    }

    normalized = normalize_ticket_payload(payload)

    assert normalized["title"] == "Write bounded artifact"
    assert normalized["subsystem"] == "smoke"
    assert normalized["allowed_paths"] == ["allowed/result.txt"]
    assert normalized["required_reading"] == ["README.md"]
    assert normalized["required_tests"] == [
        ".venv\\Scripts\\python.exe -m pytest -q tests/test_result.py"
    ]
    assert normalized["acceptance_criteria"] == "The result file exists.\nThe focused test passes."


def test_structured_fields_override_markdown_and_subsystem_label_fills_missing_value() -> None:
    payload = {
        "title": "Structured",
        "description": "## Allowed paths\n- wrong.txt",
        "allowed_paths": ["right.txt"],
        "acceptance_criteria": "Right result",
        "labels": {"nodes": [{"name": "smoke", "parent": {"name": "Subsystem"}}]},
    }

    normalized = normalize_ticket_payload(payload)

    assert normalized["allowed_paths"] == ["right.txt"]
    assert normalized["acceptance_criteria"] == "Right result"
    assert normalized["subsystem"] == "smoke"
