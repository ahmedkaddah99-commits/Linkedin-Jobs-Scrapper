from runr_automation.jobs.research import ResearchRequest, Researcher


def test_internal_research_reads_only_manifest_and_external_is_opt_in() -> None:
    seen = []
    request = ResearchRequest("RUN-5", ("backend/a.py", "docs/a.md"), (), False, "fingerprint")
    result = Researcher(lambda path: seen.append(path) or f"content:{path}").run(request)

    assert tuple(seen) == request.allowed_reads
    assert result.external_sources == ()
    assert result.input_fingerprint == "fingerprint"


def test_research_freshness_depends_on_inputs_not_elapsed_time() -> None:
    researcher = Researcher(lambda _: "content")
    request = ResearchRequest("RUN-5", ("backend/a.py",), (), False, "same")
    result = researcher.run(request)

    assert researcher.is_current(result, request) is True
    changed = ResearchRequest("RUN-5", ("backend/a.py",), (), False, "changed")
    assert researcher.is_current(result, changed) is False
