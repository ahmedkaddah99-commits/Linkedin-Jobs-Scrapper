from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from backend.profiles import job_cv_customization as service
from backend.api.routes import job_cv_customization as routes


CV = service.normalize_cv({"name": "Candidate", "summary": "Analyst using SQL", "competencies": ["SQL"],
    "recent_experience": [{"title": "Analyst", "company": "Actual employer", "period": "2020 - 2024",
                           "bullets": ["Built reports using SQL"]}]})
JOB = {"title": "Senior consultant", "company": "Employer", "description": "Use SQL for planning. Five years of experience."}
REQUIREMENTS = {"keywords": [{"label": "Data analysis", "evidence": "Built reports using SQL"}, {"label": "Investment banking", "evidence": ""}]}


def test_analysis_keeps_only_real_quotes_and_marks_benchmarks():
    answer = {"years": 5, "yearsBasis": "inferred", "industries": ["Consulting"], "roleTerms": ["Consultant"], "priorities": ["SQL"],
              "keywords": [{"label": "SQL", "source": "Use SQL for planning.", "evidence": "Built reports using SQL"},
                           {"label": "Planning", "source": "Use SQL for planning.", "evidence": "Fabricated planning achievements"},
                           {"label": "Banking", "source": "Not in job", "evidence": ""}]}
    with patch.object(service, "ask_json", return_value=answer): result = service.analyze(CV, JOB)
    assert result["yearsBasis"] == "inferred"
    assert len(result["keywords"]) == 2
    assert result["keywords"][0]["evidence"] == "Built reports using SQL"
    assert result["keywords"][1]["evidence"] == ""


def test_rewrite_preserves_identity_titles_dates_unselected_sections_and_source():
    before = deepcopy(CV)
    answer = {"summary": "SQL analyst delivering planning insights.", "name": "Invented name",
              "experience": [{"index": 0, "title": "Director", "company": "Invented", "bullets": ["Used SQL to deliver reporting insights"]}]}
    with patch.object(service, "ask_json", return_value=answer):
        draft, changes = service.generate(CV, JOB, REQUIREMENTS, {"sections": ["experience"], "scope": "full"})
    assert CV == before
    assert draft["summary"] == before["summary"]
    assert draft["name"] == before["name"]
    assert draft["experience"][0]["title"] == "Analyst"
    assert draft["experience"][0]["company"] == "Actual employer"
    assert draft["experience"][0]["period"] == "2020 - 2024"
    assert changes[0]["before"] == CV["experience"]


def test_unconfirmed_keywords_never_added_to_skills():
    with patch.object(service, "ask_json", return_value={"skills": ["Investment banking"]}):
        draft, _ = service.generate(CV, JOB, REQUIREMENTS, {"sections": ["skills"], "keywords": ["Data analysis", "Investment banking"]})
    assert draft["skills"] == ["SQL", "Data analysis"]


def test_unsupported_numbers_fail_without_changing_cv():
    with patch.object(service, "ask_json", return_value={"summary": "Improved results by 73%"}):
        with pytest.raises(service.GenerationUnavailable, match="unsupported figures"):
            service.generate(CV, JOB, REQUIREMENTS, {"sections": ["summary"]})


def test_quick_scope_preserves_other_roles_and_all_bullet_counts():
    cv = {**deepcopy(CV), "experience": [deepcopy(CV["experience"][0]) for _ in range(3)]}
    answer = {"experience": [{"index": i, "bullets": ["Used SQL for report creation"]} for i in range(3)]}
    with patch.object(service, "ask_json", return_value=answer):
        draft, _ = service.generate(cv, JOB, REQUIREMENTS, {"sections": ["experience"], "scope": "quick"})
    assert draft["experience"][2] == cv["experience"][2]
    assert draft["experience"][0] != cv["experience"][0]
    with patch.object(service, "ask_json", return_value={"experience": [{"index": 0, "bullets": []}]}):
        with pytest.raises(service.GenerationUnavailable):
            service.generate(cv, JOB, REQUIREMENTS, {"sections": ["experience"]})


def context(action="analyze", payload=None, plan="runr_pro"):
    ctx = SimpleNamespace(application=SimpleNamespace(get_user_plan_id=lambda uid: plan, get_personalized_job_detail=lambda uid, jid: JOB),
        require_scope=lambda scope: (SimpleNamespace(user_id="cv-test", metadata={}), None),
        read_json_body=lambda: payload or {"asset_id": "mine", "job_id": "job", "revision": 0}, segments=("cv-customization", action))
    ctx.errors = []
    ctx.responses = []
    ctx.send_error = lambda *args: ctx.errors.append(args)
    ctx.send_json = lambda result: ctx.responses.append(result)
    return ctx


def test_cross_account_asset_rejected_before_ai():
    ctx = context()
    with patch("backend.api.server._get_candidate_asset_by_id", side_effect=ValueError("Asset not found")), patch.object(routes, "analyze") as ai:
        routes._handle(ctx)
    assert ctx.errors[0][0] == 422
    ai.assert_not_called()


def test_paid_generation_gate_precedes_provider():
    ctx = context("generate", plan="free")
    with patch.object(routes, "generate") as ai: routes._handle(ctx)
    assert ctx.errors[0][0] == 403
    ai.assert_not_called()


def test_stale_baseline_rejected_before_ai():
    ctx = context(payload={"asset_id": "mine", "job_id": "job", "revision": 99})
    with patch("backend.api.server._get_candidate_asset_by_id", return_value={"asset_kind": "workspace_cv"}), patch("backend.api.routes.documents._editor_source_text", return_value="cv"), patch.object(routes, "build_cv_editor_payload", return_value={"revision": 2, "profile": {}}), patch.object(routes, "analyze") as ai:
        routes._handle(ctx)
    assert ctx.errors[0][0] == 409
    ai.assert_not_called()


def test_preview_is_scoped_to_one_user_and_one_job(monkeypatch):
    monkeypatch.setenv("CV_CUSTOMIZATION_PREVIEW_USER_ID", "cv-test")
    monkeypatch.setenv("CV_CUSTOMIZATION_PREVIEW_JOB_ID", "preview-job")
    wrong = context("generate", plan="free")
    routes._handle(wrong)
    assert wrong.errors[0][0] == 403
    allowed = context("generate", plan="free", payload={"asset_id": "mine", "job_id": "preview-job", "revision": 0})
    with patch("backend.api.server._get_candidate_asset_by_id", side_effect=ValueError("Owned asset required")) as asset:
        routes._handle(allowed)
    asset.assert_called_once()
    assert allowed.errors[0][0] == 422
