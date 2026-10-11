import pytest

from runr_automation.jobs.parallelize import DependencyEdge, DependencyPlanner, PlanCycle


def test_cycle_prevents_wave_assignment() -> None:
    planner = DependencyPlanner()
    with pytest.raises(PlanCycle):
        planner.plan(("A", "B"), (DependencyEdge("A", "B", "e1"), DependencyEdge("B", "A", "e2")), {})


def test_resource_conflicts_never_share_wave_and_unrelated_component_is_unchanged() -> None:
    planner = DependencyPlanner()
    plan = planner.plan(
        ("A", "B", "C"),
        (),
        {"A": ("backend/shared.py",), "B": ("backend/shared.py",), "C": ("frontend/app.ts",)},
    )

    assert plan.wave_of("A") != plan.wave_of("B")
    assert plan.wave_of("C") == 1


def test_user_created_edges_are_never_removed() -> None:
    existing = (DependencyEdge("A", "B", "user", user_created=True),)
    reconciled = DependencyPlanner().reconcile_edges(existing, ())
    assert reconciled == existing
