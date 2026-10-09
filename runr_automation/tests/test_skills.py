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


def test_research_skill_hands_current_evidence_to_implementation_ready() -> None:
    text = (ROOT / "skills" / "runr-ticket-research" / "SKILL.md").read_text(encoding="utf-8")
    for phrase in (
        "implementation can start",
        "exact `Ready` Issue Status label",
        "linear_save_issue",
        "remove every other `Issue Status` child",
        "re-read the exact issue",
        "must not move to `Ready`",
    ):
        assert phrase.casefold() in text.casefold(), f"runr-ticket-research is missing {phrase}"


def test_parallelization_skill_treats_parallelism_as_versioned_plan_property() -> None:
    text = (ROOT / "skills" / "runr-parallelization-plan" / "SKILL.md").read_text(encoding="utf-8")
    assert text.startswith("---\nname: runr-parallelization-plan\n")
    assert "plan version" in text
    assert "cycle" in text
    assert "Never remove" in text


def test_existing_lifecycle_skills_keep_scope_contracts_without_controller_gates() -> None:
    required = {
        "runr-ticket-creation": ("Subsystem grouped label", "Allowed paths", "runr-ticket-deduplication"),
        "runr-ticket-start": ("scope manifest", "current plan", "dedicated"),
        "runr-ticket-merge-predeployment": ("tested implementation commit", "dedicated", "Execution independence"),
        "runr-ticket-batch-merge-predeployment": ("tested implementation commit", "dedicated", "Execution independence"),
        "runr-ticket-merge-deployment": ("tested revision", "dedicated", "Execution independence"),
        "runr-ticket-batch-merge-deployment": ("tested revision", "dedicated", "Execution independence"),
        "runr-discard-issue": ("exact Linear issue IDs", "Execution independence"),
    }
    forbidden = (
        "mandatory controller approval",
        "mandatory release approval",
        "mandatory discard approval",
        "require a matching unexpired local approval",
        "require a matching unexpired release approval",
        "require a matching unexpired discard approval",
    )
    for name, phrases in required.items():
        text = (ROOT / "skills" / name / "SKILL.md").read_text(encoding="utf-8")
        for phrase in phrases:
            assert phrase in text, f"{name} is missing {phrase}"
        lowered = text.casefold()
        for phrase in forbidden:
            assert phrase.casefold() not in lowered, f"{name} reintroduced controller gate: {phrase}"


def test_independent_implementation_skill_is_single_issue_and_stops_at_review() -> None:
    text = (ROOT / "skills" / "runr-ticket-implementation" / "SKILL.md").read_text(encoding="utf-8")
    assert text.startswith("---\nname: runr-ticket-implementation\n")
    for phrase in (
        "one exact Linear issue",
        "dedicated worktree",
        "scope manifest",
        "Allowed paths",
        "attempt evidence",
        "In Review",
        "never merge",
        "never deploy",
        "shared checkout",
    ):
        assert phrase in text, f"runr-ticket-implementation is missing {phrase}"


def test_predeployment_integration_is_distinct_from_live_release_readiness() -> None:
    for name in ("runr-ticket-merge-predeployment", "runr-ticket-batch-merge-predeployment"):
        text = (ROOT / "skills" / name / "SKILL.md").read_text(encoding="utf-8")
        for phrase in (
            "Predeployment Integrated",
            "integration_revision",
            "implementation-dependent",
            "Ready for Production",
            "live verification",
            "verification retry",
        ):
            assert phrase.casefold() in text.casefold(), f"{name} is missing {phrase}"


def test_dependency_gate_distinguishes_implementation_and_release_dependencies() -> None:
    for name in ("runr-ticket-start", "runr-ticket-implementation", "runr-parallelization-plan"):
        text = (ROOT / "skills" / name / "SKILL.md").read_text(encoding="utf-8")
        for phrase in ("implementation dependency", "release dependency", "Predeployment Integrated"):
            assert phrase.casefold() in text.casefold(), f"{name} is missing {phrase}"


def test_ticket_template_registers_predeployment_integrated_contract() -> None:
    text = (ROOT.parent / "docs" / "tickets" / "TEMPLATE.md").read_text(encoding="utf-8")
    for phrase in (
        "Predeployment Integrated",
        "dependency-kind",
        "integration_revision",
        "implementation dependency",
        "release dependency",
    ):
        assert phrase.casefold() in text.casefold(), f"ticket template is missing {phrase}"


def test_predeployment_worktrees_and_native_done_are_explicit() -> None:
    for name in (
        "runr-ticket-start",
        "runr-ticket-implementation",
        "runr-ticket-merge-predeployment",
        "runr-ticket-batch-merge-predeployment",
    ):
        text = (ROOT / "skills" / name / "SKILL.md").read_text(encoding="utf-8")
        assert "predeployment/render-turso-r2" in text
    for name in ("runr-ticket-merge-predeployment", "runr-ticket-batch-merge-predeployment"):
        text = (ROOT / "skills" / name / "SKILL.md").read_text(encoding="utf-8")
        for phrase in ("native Linear workflow state to Done", "administrative", "Predeployment Integrated"):
            assert phrase.casefold() in text.casefold(), f"{name} is missing {phrase}"
    discard = (ROOT / "skills" / "runr-discard-issue" / "SKILL.md").read_text(encoding="utf-8")
    assert "Native Linear `Done` paired with the custom `Predeployment Integrated`" in discard
