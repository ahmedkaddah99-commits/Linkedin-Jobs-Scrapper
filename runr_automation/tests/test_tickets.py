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


def test_linear_bold_metadata_ticket_becomes_executable_fields() -> None:
    payload = {
        "title": "Verify live topology",
        "description": """
**Primary subsystem:** WS-07 Deployment Release and CI
**Co-owners:** WS-03 Acquisition; VPS/Render operator
**Exact allowed paths:** deploy/start.sh; render.yaml; tests/test_topology.py
**Required reading:** docs/reverse-engineering/02-deployment/render.md; docs/subsystems.yaml

**Acceptance criteria:**

* Capture the release evidence.
* Capture the database binding evidence.

**Safe verification:**

* .venv\\Scripts\\python.exe -m pytest -q tests/test_topology.py
""",
    }

    normalized = normalize_ticket_payload(payload)

    assert normalized["subsystem"] == "WS-07 Deployment Release and CI"
    assert normalized["co_owners"] == ["WS-03"]
    assert normalized["allowed_paths"] == [
        "deploy/start.sh",
        "render.yaml",
        "tests/test_topology.py",
    ]
    assert normalized["required_reading"] == [
        "docs/reverse-engineering/02-deployment/render.md",
        "docs/subsystems.yaml",
    ]
    assert normalized["acceptance_criteria"] == (
        "Capture the release evidence.\nCapture the database binding evidence."
    )
    assert normalized["required_tests"] == [
        ".venv\\Scripts\\python.exe -m pytest -q tests/test_topology.py"
    ]


def test_verification_commands_strip_markdown_wrapping_and_preserve_external_checks() -> None:
    payload = {
        "title": "Verify service topology",
        "description": """
**Primary subsystem:** WS-07 Deployment Release and CI
**Exact allowed paths:** deploy/systemd/runr.target
**Acceptance criteria:**
* The service topology is verified.
**Safe verification:**
* `.venv\\Scripts\\python.exe -m pytest -q tests/test_topology.py`
* `systemd-analyze verify the acquisition units on the VPS`
""",
    }

    normalized = normalize_ticket_payload(payload)

    assert normalized["required_tests"] == [
        ".venv\\Scripts\\python.exe -m pytest -q tests/test_topology.py"
    ]
    assert normalized["external_verification"] == [
        "systemd-analyze verify the acquisition units on the VPS"
    ]
