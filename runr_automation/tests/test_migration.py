from pathlib import Path

from runr_automation.migration import (
    SUBSYSTEM_PROJECTS,
    FakeMigrationClient,
    MigrationIssue,
    MigrationLabel,
    MigrationProject,
    SubsystemMigrator,
)


def test_migration_dry_run_writes_snapshot_without_mutations(tmp_path: Path) -> None:
    projects = tuple(
        MigrationProject(project_id, name, f"Description for {name}")
        for project_id, name in SUBSYSTEM_PROJECTS.items()
    )
    issues = (MigrationIssue("linear-5", "RUN-5", next(iter(SUBSYSTEM_PROJECTS))),)
    client = FakeMigrationClient(projects, issues)

    result = SubsystemMigrator(client, snapshot_dir=tmp_path).run(dry_run=True)

    assert result.success is True
    assert result.dry_run is True
    assert result.mapped_issue_count == 1
    assert result.archived_project_ids == ()
    assert client.mutations == []
    assert result.snapshot_path is not None
    assert Path(result.snapshot_path).exists()


def test_apply_leaves_exactly_one_expected_subsystem_label(tmp_path: Path) -> None:
    projects = tuple(
        MigrationProject(project_id, name, f"Description for {name}")
        for project_id, name in SUBSYSTEM_PROJECTS.items()
    )
    old_label = MigrationLabel("legacy-ws-02", "WS-02 Workers and Orchestration", "Subsystem")
    issue = MigrationIssue(
        "linear-5",
        "RUN-5",
        next(iter(SUBSYSTEM_PROJECTS)),
        (old_label.label_id,),
    )
    client = FakeMigrationClient(projects, (issue,), labels=(old_label,))

    result = SubsystemMigrator(client, snapshot_dir=tmp_path).run(dry_run=False)

    assert result.success is True
    final_issue = client.get_issue("linear-5")
    assert len(final_issue.label_ids) == 1
    assert final_issue.label_ids[0] != old_label.label_id


def _projects() -> tuple[MigrationProject, ...]:
    return tuple(
        MigrationProject(project_id, name, f"Description for {name}")
        for project_id, name in SUBSYSTEM_PROJECTS.items()
    )


def test_partial_migration_failure_archives_no_projects(tmp_path: Path) -> None:
    project_ids = tuple(SUBSYSTEM_PROJECTS)
    issues = (
        MigrationIssue("linear-5", "RUN-5", project_ids[0]),
        MigrationIssue("linear-6", "RUN-6", project_ids[1]),
    )
    client = FakeMigrationClient(_projects(), issues, fail_verification_for={"linear-6"})

    result = SubsystemMigrator(client, snapshot_dir=tmp_path).run(dry_run=False)

    assert result.success is False
    assert result.repair_report
    assert not any(action == "archive_project" for action, _, _ in client.mutations)


def test_successful_apply_rerun_has_no_duplicate_or_destructive_mutations(tmp_path: Path) -> None:
    issue = MigrationIssue("linear-5", "RUN-5", next(iter(SUBSYSTEM_PROJECTS)))
    client = FakeMigrationClient(_projects(), (issue,))
    migrator = SubsystemMigrator(client, snapshot_dir=tmp_path)
    assert migrator.run(dry_run=False).success is True
    first_mutation_count = len(client.mutations)

    second = migrator.run(dry_run=False)

    assert second.success is True
    assert client.mutations[first_mutation_count:] == []


def test_onboarding_issue_blocks_apply_without_any_linear_mutation(tmp_path: Path) -> None:
    protected = MigrationIssue("linear-1", "RUN-1", next(iter(SUBSYSTEM_PROJECTS)))
    client = FakeMigrationClient(_projects(), (protected,))

    result = SubsystemMigrator(client, snapshot_dir=tmp_path).run(dry_run=False)

    assert result.success is False
    assert "RUN-1" in (result.repair_report or "")
    assert client.mutations == []


def test_unrelated_projects_and_issues_are_untouched(tmp_path: Path) -> None:
    unrelated_project = MigrationProject("other-project", "Other", "Unrelated")
    unrelated_issue = MigrationIssue("other-issue", "RUN-99", unrelated_project.project_id)
    client = FakeMigrationClient((*_projects(), unrelated_project), (unrelated_issue,))

    result = SubsystemMigrator(client, snapshot_dir=tmp_path).run(dry_run=False)

    assert result.success is True
    assert client.get_issue(unrelated_issue.linear_id) == unrelated_issue
    assert not any(target == unrelated_project.project_id for _, target, _ in client.mutations)
