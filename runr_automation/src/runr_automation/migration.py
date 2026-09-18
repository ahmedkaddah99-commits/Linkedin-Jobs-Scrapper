"""Safe, repeatable migration from subsystem projects to grouped labels."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from .linear_client import LinearGraphQLClient


SUBSYSTEM_PROJECTS = {
    "ff1a8c34-e944-45a0-ab77-0c9cce017fb8": "WS-01 HTTP API and CLI",
    "27105e14-5301-427b-b54d-c094a9533fcd": "WS-02 Workers and Orchestration",
    "2c7e09bb-4a77-42d6-b4f7-9d8d7ecd289d": "WS-03 Acquisition and Collectors",
    "a901ce3d-852f-43fc-b807-089694d2a82c": "WS-04 Application Services",
    "c375dcb2-3130-4ba9-8b81-c601f6475360": "WS-05 Data and Domain Model",
    "2872a707-59a9-4b83-9ce4-786d46a66063": "WS-06 Integrations and Security",
    "aabd8557-e1f1-480f-8d56-f0abad12f64e": "WS-07 Deployment Release and CI",
    "9607c102-9352-4585-8ebe-bf93ebd4ddcd": "WS-08 Frontend",
    "da9e7a64-2c96-4f93-adea-b501140ee806": "WS-09 Assisted Apply Extension",
    "23ddabd9-bd5b-4d6c-a920-80200f0ce22b": "WS-10 Backend Test Suite",
    "2966ced5-b0d7-463e-8273-a3e176427e56": "WS-11 Docs and Repository Artifacts",
    "263695bc-47fc-482d-901f-6697a9329d0a": "WS-12 Cross-subsystem Synthesis",
}
SUBSYSTEM_LABEL_GROUP = "Subsystem"


@dataclass(frozen=True)
class MigrationTeam:
    team_id: str
    name: str


@dataclass(frozen=True)
class MigrationProject:
    project_id: str
    name: str
    description: str
    archived: bool = False


@dataclass(frozen=True)
class MigrationLabelGroup:
    group_id: str
    name: str


@dataclass(frozen=True)
class MigrationLabel:
    label_id: str
    name: str
    group_name: str


@dataclass(frozen=True)
class MigrationIssue:
    linear_id: str
    identifier: str
    project_id: str | None
    label_ids: tuple[str, ...] = ()


class MigrationAdapter(Protocol):
    def get_team(self) -> MigrationTeam: ...

    def list_projects(self, project_ids: tuple[str, ...]) -> tuple[MigrationProject, ...]: ...

    def list_issues_for_projects(self, project_ids: tuple[str, ...]) -> tuple[MigrationIssue, ...]: ...

    def list_labels(self) -> tuple[MigrationLabel, ...]: ...

    def ensure_label_group(self, name: str) -> MigrationLabelGroup: ...

    def ensure_label(self, group: MigrationLabelGroup, name: str) -> MigrationLabel: ...

    def add_issue_label(self, issue_id: str, label_id: str) -> None: ...

    def remove_issue_label(self, issue_id: str, label_id: str) -> None: ...

    def get_issue(self, issue_id: str) -> MigrationIssue: ...

    def clear_issue_project(self, issue_id: str) -> None: ...

    def archive_project(self, project_id: str) -> None: ...


@dataclass(frozen=True)
class MigrationResult:
    success: bool
    dry_run: bool
    mapped_issue_count: int
    archived_project_ids: tuple[str, ...]
    snapshot_path: str | None
    repair_report: str | None = None
    manual_steps: tuple[str, ...] = ()


class MigrationCapabilityError(RuntimeError):
    def __init__(self, capability: str) -> None:
        self.capability = capability
        super().__init__(f"Linear client does not support {capability}")


class LinearMigrationClient:
    """Linear migration reads plus deliberately capability-gated mutations."""

    def __init__(self, token: str, team_id: str) -> None:
        self.client = LinearGraphQLClient(token, team_id)
        self.team_id = team_id

    def get_team(self) -> MigrationTeam:
        data = self._query("query Team($id: String!) { team(id: $id) { id name } }", {"id": self.team_id})
        return MigrationTeam(**{"team_id": data["team"]["id"], "name": data["team"]["name"]})

    def list_projects(self, project_ids: tuple[str, ...]) -> tuple[MigrationProject, ...]:
        data = self._query(
            "query Projects($ids: [ID!]) { projects(filter: {id: {in: $ids}}, first: 50) "
            "{ nodes { id name description archivedAt } } }",
            {"ids": list(project_ids)},
        )
        return tuple(
            MigrationProject(node["id"], node["name"], node.get("description") or "", bool(node.get("archivedAt")))
            for node in data["projects"]["nodes"]
        )

    def list_issues_for_projects(self, project_ids: tuple[str, ...]) -> tuple[MigrationIssue, ...]:
        data = self._query(
            "query Issues($ids: [ID!]) { issues(filter: {project: {id: {in: $ids}}}, first: 250) "
            "{ nodes { id identifier project { id } labels { nodes { id } } } } }",
            {"ids": list(project_ids)},
        )
        return tuple(self._issue(node) for node in data["issues"]["nodes"])

    def list_labels(self) -> tuple[MigrationLabel, ...]:
        data = self._query(
            "query Labels($team: ID!) { issueLabels(filter: {team: {id: {eq: $team}}}, first: 250) "
            "{ nodes { id name group { name } } } }",
            {"team": self.team_id},
        )
        return tuple(
            MigrationLabel(node["id"], node["name"], (node.get("group") or {}).get("name") or "")
            for node in data["issueLabels"]["nodes"]
        )

    def ensure_label_group(self, name: str) -> MigrationLabelGroup:
        raise MigrationCapabilityError("grouped label creation")

    def ensure_label(self, group: MigrationLabelGroup, name: str) -> MigrationLabel:
        raise MigrationCapabilityError("grouped label creation")

    def add_issue_label(self, issue_id: str, label_id: str) -> None:
        raise MigrationCapabilityError("grouped label creation")

    def remove_issue_label(self, issue_id: str, label_id: str) -> None:
        raise MigrationCapabilityError("grouped label creation")

    def get_issue(self, issue_id: str) -> MigrationIssue:
        data = self._query(
            "query Issue($id: String!) { issue(id: $id) { id identifier project { id } labels { nodes { id } } } }",
            {"id": issue_id},
        )
        return self._issue(data["issue"])

    def clear_issue_project(self, issue_id: str) -> None:
        raise MigrationCapabilityError("project clearing")

    def archive_project(self, project_id: str) -> None:
        raise MigrationCapabilityError("project archiving")

    def _query(self, query: str, variables: dict[str, Any]) -> dict[str, Any]:
        return self.client._post({"query": query, "variables": variables})["data"]

    @staticmethod
    def _issue(node: dict[str, Any]) -> MigrationIssue:
        return MigrationIssue(
            node["id"],
            node["identifier"],
            (node.get("project") or {}).get("id"),
            tuple(label["id"] for label in (node.get("labels") or {}).get("nodes", ())),
        )


class SubsystemMigrator:
    def __init__(
        self,
        client: MigrationAdapter,
        *,
        snapshot_dir: str | Path,
        team_id: str = "a6a93ab8-96eb-4ada-84e0-d4942d64db09",
    ) -> None:
        self.client = client
        self.snapshot_dir = Path(snapshot_dir)
        self.team_id = team_id

    def run(self, *, dry_run: bool) -> MigrationResult:
        snapshot, projects, issues = self._collect_snapshot()
        snapshot_path = self._write_snapshot(snapshot)
        mapped_issues = tuple(issue for issue in issues if issue.project_id in SUBSYSTEM_PROJECTS)
        if dry_run:
            return MigrationResult(True, True, len(mapped_issues), (), str(snapshot_path))
        protected = tuple(
            issue.identifier
            for issue in mapped_issues
            if issue.identifier in {"RUN-1", "RUN-2", "RUN-3", "RUN-4"}
        )
        if protected:
            return MigrationResult(
                False,
                False,
                len(mapped_issues),
                (),
                str(snapshot_path),
                repair_report=(
                    "Protected Linear onboarding issues were found in subsystem projects: "
                    + ", ".join(protected)
                    + ". Move them manually before applying this migration."
                ),
            )

        try:
            group = self.client.ensure_label_group(SUBSYSTEM_LABEL_GROUP)
            labels = {
                project_id: self.client.ensure_label(group, label_name)
                for project_id, label_name in SUBSYSTEM_PROJECTS.items()
            }
        except MigrationCapabilityError as exc:
            return MigrationResult(
                False,
                False,
                len(mapped_issues),
                (),
                str(snapshot_path),
                manual_steps=_manual_steps(exc.capability),
            )

        label_by_id = {label.label_id: label for label in self.client.list_labels()}
        for issue in mapped_issues:
            expected_label = labels[issue.project_id].label_id
            current = self.client.get_issue(issue.linear_id)
            if expected_label not in current.label_ids:
                self.client.add_issue_label(issue.linear_id, expected_label)
                current = self.client.get_issue(issue.linear_id)
            conflicting_labels = [
                label_id
                for label_id in current.label_ids
                if label_id != expected_label
                and label_by_id.get(label_id, MigrationLabel("", "", "")).group_name == SUBSYSTEM_LABEL_GROUP
            ]
            for label_id in conflicting_labels:
                self.client.remove_issue_label(issue.linear_id, label_id)
            if conflicting_labels:
                current = self.client.get_issue(issue.linear_id)
            subsystem_label_count = sum(
                label_by_id.get(label_id, MigrationLabel("", "", "")).group_name == SUBSYSTEM_LABEL_GROUP
                for label_id in current.label_ids
            )
            if (
                current.project_id != issue.project_id
                or current.label_ids.count(expected_label) != 1
                or subsystem_label_count != 1
            ):
                return MigrationResult(
                    False,
                    False,
                    len(mapped_issues),
                    (),
                    str(snapshot_path),
                    repair_report=(
                        f"Issue {issue.identifier} failed label verification before project clearing; "
                        f"expected label {expected_label}"
                    ),
                )
            if current.project_id is not None:
                self.client.clear_issue_project(issue.linear_id)
            verified = self.client.get_issue(issue.linear_id)
            verified_subsystem_label_count = sum(
                label_by_id.get(label_id, MigrationLabel("", "", "")).group_name == SUBSYSTEM_LABEL_GROUP
                for label_id in verified.label_ids
            )
            if (
                verified.project_id is not None
                or verified.label_ids.count(expected_label) != 1
                or verified_subsystem_label_count != 1
            ):
                return MigrationResult(
                    False,
                    False,
                    len(mapped_issues),
                    (),
                    str(snapshot_path),
                    repair_report=f"Issue {issue.identifier} failed final migration verification",
                )

        archived: list[str] = []
        try:
            for project in projects:
                if not project.archived:
                    self.client.archive_project(project.project_id)
                    archived.append(project.project_id)
        except MigrationCapabilityError as exc:
            return MigrationResult(
                False,
                False,
                len(mapped_issues),
                tuple(archived),
                str(snapshot_path),
                manual_steps=_manual_steps(exc.capability),
            )
        return MigrationResult(True, False, len(mapped_issues), tuple(archived), str(snapshot_path))

    def _collect_snapshot(self):
        project_ids = tuple(SUBSYSTEM_PROJECTS)
        team = self.client.get_team()
        if team.team_id != self.team_id:
            raise ValueError(f"Linear team mismatch: expected {self.team_id}, got {team.team_id}")
        projects = self.client.list_projects(project_ids)
        if {project.project_id for project in projects} != set(project_ids):
            raise ValueError("Linear project query did not return the exact 12 subsystem projects")
        issues = self.client.list_issues_for_projects(project_ids)
        labels = self.client.list_labels()
        snapshot = {
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "team": asdict(team),
            "projects": [asdict(project) for project in projects],
            "issues": [asdict(issue) for issue in issues],
            "labels": [asdict(label) for label in labels],
        }
        return snapshot, projects, issues

    def _write_snapshot(self, snapshot: dict[str, Any]) -> Path:
        self.snapshot_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        path = self.snapshot_dir / f"subsystem-migration-{timestamp}.json"
        if path.exists():
            digest = hashlib.sha256(json.dumps(snapshot, sort_keys=True).encode()).hexdigest()[:8]
            path = self.snapshot_dir / f"subsystem-migration-{timestamp}-{digest}.json"
        path.write_text(json.dumps(snapshot, indent=2, sort_keys=True), encoding="utf-8")
        return path


def _manual_steps(capability: str) -> tuple[str, ...]:
    if capability == "grouped label creation":
        return (
            "Create or confirm the grouped Linear label group named Subsystem.",
            "Create exactly one child label for each WS-01 through WS-12 name under Subsystem.",
            "Re-run runr-auto migrate-subsystems --apply after grouped labels exist.",
        )
    if capability == "project archiving":
        return (
            "Confirm all issue label/project verification passed.",
            "Archive only the exact 12 subsystem projects in Linear's project settings.",
            "Re-run runr-auto migrate-subsystems --dry-run and then --apply after archive capability is available.",
        )
    return (f"Provide the missing Linear capability: {capability}.",)


class FakeMigrationClient:
    """Deterministic migration adapter with observable mutations."""

    def __init__(
        self,
        projects: tuple[MigrationProject, ...],
        issues: tuple[MigrationIssue, ...],
        labels: tuple[MigrationLabel, ...] = (),
        *,
        team: MigrationTeam | None = None,
        fail_verification_for: set[str] | None = None,
    ) -> None:
        self.team = team or MigrationTeam(
            "a6a93ab8-96eb-4ada-84e0-d4942d64db09", "Runr"
        )
        self.projects = {project.project_id: project for project in projects}
        self.issues = {issue.linear_id: issue for issue in issues}
        self.labels = list(labels)
        self.mutations: list[tuple[str, str, str | None]] = []
        self.fail_verification_for = fail_verification_for or set()
        self.label_groups: dict[str, MigrationLabelGroup] = {}

    def get_team(self) -> MigrationTeam:
        return self.team

    def list_projects(self, project_ids: tuple[str, ...]) -> tuple[MigrationProject, ...]:
        return tuple(self.projects[project_id] for project_id in project_ids)

    def list_issues_for_projects(self, project_ids: tuple[str, ...]) -> tuple[MigrationIssue, ...]:
        return tuple(issue for issue in self.issues.values() if issue.project_id in project_ids)

    def list_labels(self) -> tuple[MigrationLabel, ...]:
        return tuple(self.labels)

    def ensure_label_group(self, name: str) -> MigrationLabelGroup:
        if name not in self.label_groups:
            self.label_groups[name] = MigrationLabelGroup("group-subsystem", name)
            self.mutations.append(("create_group", name, None))
        return self.label_groups[name]

    def ensure_label(self, group: MigrationLabelGroup, name: str) -> MigrationLabel:
        for label in self.labels:
            if label.group_name == group.name and label.name == name:
                return label
        label = MigrationLabel(f"label-{hashlib.sha1(name.encode()).hexdigest()[:12]}", name, group.name)
        self.labels.append(label)
        self.mutations.append(("create_label", name, label.label_id))
        return label

    def add_issue_label(self, issue_id: str, label_id: str) -> None:
        issue = self.issues[issue_id]
        if label_id not in issue.label_ids:
            self.issues[issue_id] = MigrationIssue(
                issue.linear_id, issue.identifier, issue.project_id, (*issue.label_ids, label_id)
            )
        self.mutations.append(("add_label", issue_id, label_id))

    def remove_issue_label(self, issue_id: str, label_id: str) -> None:
        issue = self.issues[issue_id]
        self.issues[issue_id] = MigrationIssue(
            issue.linear_id,
            issue.identifier,
            issue.project_id,
            tuple(existing for existing in issue.label_ids if existing != label_id),
        )
        self.mutations.append(("remove_label", issue_id, label_id))

    def get_issue(self, issue_id: str) -> MigrationIssue:
        issue = self.issues[issue_id]
        if issue_id in self.fail_verification_for:
            return MigrationIssue(issue.linear_id, issue.identifier, issue.project_id, ())
        return issue

    def clear_issue_project(self, issue_id: str) -> None:
        issue = self.issues[issue_id]
        self.issues[issue_id] = MigrationIssue(issue.linear_id, issue.identifier, None, issue.label_ids)
        self.mutations.append(("clear_project", issue_id, issue.project_id))

    def archive_project(self, project_id: str) -> None:
        project = self.projects[project_id]
        self.projects[project_id] = MigrationProject(
            project.project_id, project.name, project.description, True
        )
        self.mutations.append(("archive_project", project_id, None))
