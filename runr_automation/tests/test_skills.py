from pathlib import Path


ROOT = Path(__file__).parents[1]


def test_deduplication_skill_closes_ambiguous_and_invalid_output_loopholes() -> None:
    text = (ROOT / "skills" / "runr-ticket-deduplication" / "SKILL.md").read_text(encoding="utf-8")
    assert text.startswith("---\nname: runr-ticket-deduplication\n")
    assert "Never close" in text
    assert "strict schema" in text
    assert "bounded candidate" in text


def test_research_skill_enforces_manifest_and_evidence_freshness() -> None:
    text = (ROOT / "skills" / "runr-ticket-research" / "SKILL.md").read_text(encoding="utf-8")
    assert text.startswith("---\nname: runr-ticket-research\n")
    assert "scope manifest" in text
    assert "primary sources" in text
    assert "not merely" in text


def test_parallelization_skill_treats_parallelism_as_versioned_plan_property() -> None:
    text = (ROOT / "skills" / "runr-parallelization-plan" / "SKILL.md").read_text(encoding="utf-8")
    assert text.startswith("---\nname: runr-parallelization-plan\n")
    assert "plan version" in text
    assert "cycle" in text
    assert "Never remove" in text


def test_existing_lifecycle_skills_use_controller_scope_plan_and_approvals() -> None:
    required = {
        "runr-ticket-creation": ("Subsystem grouped label", "Allowed paths", "runr-ticket-deduplication"),
        "runr-ticket-start": ("scope manifest", "current plan", "dedicated"),
        "runr-ticket-merge-predeployment": ("local approval", "tested commit SHA", "serialized"),
        "runr-ticket-batch-merge-predeployment": ("local approval", "tested commit SHA", "serialized"),
        "runr-ticket-merge-deployment": ("release approval", "tested commit SHA"),
        "runr-ticket-batch-merge-deployment": ("release approval", "tested commit SHA"),
        "runr-discard-issue": ("discard approval", "action fingerprint"),
    }
    for name, phrases in required.items():
        text = (ROOT / "skills" / name / "SKILL.md").read_text(encoding="utf-8")
        for phrase in phrases:
            assert phrase in text, f"{name} is missing {phrase}"
