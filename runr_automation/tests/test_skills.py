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
