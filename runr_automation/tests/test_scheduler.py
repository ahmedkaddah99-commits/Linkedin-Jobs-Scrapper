from runr_automation.scheduler import Candidate, Scheduler


def candidate(identifier, paths, **overrides):
    values = dict(
        identifier=identifier, dedup_state="clear", research_state="current", plan_current=True,
        scope_valid=True, dependencies_ready=True, lifecycle_state="Ready", wave=1,
        compatible_with=frozenset(), write_paths=tuple(paths),
    )
    values.update(overrides)
    return Candidate(**values)


def test_scheduler_requires_every_eligibility_gate() -> None:
    blocked = candidate("RUN-5", ("a.py",), research_state="stale")
    assert Scheduler(2).select((blocked,)) == ()


def test_same_wave_resource_conflict_cannot_run_concurrently() -> None:
    first = candidate("RUN-5", ("shared.py",), compatible_with=frozenset({"RUN-6"}))
    second = candidate("RUN-6", ("shared.py",), compatible_with=frozenset({"RUN-5"}))
    assert Scheduler(2).select((first, second)) == (first,)


def test_same_wave_explicitly_compatible_disjoint_work_can_run() -> None:
    first = candidate("RUN-5", ("a.py",), compatible_with=frozenset({"RUN-6"}))
    second = candidate("RUN-6", ("b.py",), compatible_with=frozenset({"RUN-5"}))
    assert Scheduler(2).select((first, second)) == (first, second)
