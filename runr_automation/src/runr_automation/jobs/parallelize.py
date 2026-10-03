"""Evidence-backed dependency DAG and conflict-safe wave planning."""

from __future__ import annotations

from dataclasses import dataclass


class PlanCycle(ValueError):
    pass


@dataclass(frozen=True)
class DependencyEdge:
    predecessor: str
    successor: str
    evidence: str
    user_created: bool = False


@dataclass(frozen=True)
class ExecutionPlan:
    waves: tuple[tuple[str, ...], ...]

    def wave_of(self, issue: str) -> int:
        return next(index for index, wave in enumerate(self.waves, 1) if issue in wave)


class DependencyPlanner:
    def reconcile_edges(
        self, existing: tuple[DependencyEdge, ...], inferred: tuple[DependencyEdge, ...]
    ) -> tuple[DependencyEdge, ...]:
        by_pair = {(edge.predecessor, edge.successor): edge for edge in existing}
        for edge in inferred:
            by_pair.setdefault((edge.predecessor, edge.successor), edge)
        return tuple(by_pair.values())

    def plan(
        self,
        issues: tuple[str, ...],
        edges: tuple[DependencyEdge, ...],
        resources: dict[str, tuple[str, ...]],
    ) -> ExecutionPlan:
        predecessors = {issue: set() for issue in issues}
        successors = {issue: set() for issue in issues}
        for edge in edges:
            if edge.predecessor in predecessors and edge.successor in predecessors:
                predecessors[edge.successor].add(edge.predecessor)
                successors[edge.predecessor].add(edge.successor)
        ready = sorted(issue for issue in issues if not predecessors[issue])
        order = []
        remaining = {key: set(value) for key, value in predecessors.items()}
        while ready:
            issue = ready.pop(0)
            order.append(issue)
            for successor in sorted(successors[issue]):
                remaining[successor].discard(issue)
                if not remaining[successor] and successor not in order and successor not in ready:
                    ready.append(successor)
            ready.sort()
        if len(order) != len(issues):
            raise PlanCycle("dependency cycle prevents wave assignment")
        assigned: dict[str, int] = {}
        waves: list[list[str]] = []
        for issue in order:
            earliest = max((assigned[item] + 1 for item in predecessors[issue]), default=1)
            wave_number = earliest
            issue_resources = set(resources.get(issue, ()))
            while wave_number <= len(waves) and any(
                issue_resources & set(resources.get(member, ())) for member in waves[wave_number - 1]
            ):
                wave_number += 1
            while len(waves) < wave_number:
                waves.append([])
            waves[wave_number - 1].append(issue)
            assigned[issue] = wave_number
        return ExecutionPlan(tuple(tuple(wave) for wave in waves))
