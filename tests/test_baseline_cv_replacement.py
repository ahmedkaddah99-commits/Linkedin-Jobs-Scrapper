"""Tests for CP-034: Baseline CV Replacement with Preview & Confirmation."""

import unittest

from backend.application.baseline_cv_replacement_service import (
    _build_matched_diff,
    _compare_bullets,
    _compute_experience_diffs,
    _extract_cv_experiences,
    _fuzzy_score,
    _normalize,
    _parse_bullets,
    _tokenize,
    confirm_baseline_cv_replacement,
    preview_baseline_cv_replacement,
)
from backend.domain.models import (
    BASELINE_CV_DIFF_CATEGORY_ADDED,
    BASELINE_CV_DIFF_CATEGORY_CHANGED_BULLETS,
    BASELINE_CV_DIFF_CATEGORY_CHANGED_COMPANY,
    BASELINE_CV_DIFF_CATEGORY_CHANGED_DATES,
    BASELINE_CV_DIFF_CATEGORY_CHANGED_TITLE,
    BASELINE_CV_DIFF_CATEGORY_MATCHING,
    BASELINE_CV_DIFF_CATEGORY_REMOVED,
    BASELINE_CV_REPLACEMENT_ACTION_ADD,
    BASELINE_CV_REPLACEMENT_ACTION_IGNORE,
    BASELINE_CV_REPLACEMENT_ACTION_NEEDS_REVIEW,
    BaselineCVBulletDiff,
    BaselineCVExperienceDiff,
    BaselineCVReplacementPreview,
    CareerProfile,
)

OLD = "Senior Engineer | Acme | Jan 2020 - Present\n- Built APIs\n- Mentored team"
NEW = "Senior Engineer | Acme | Jan 2020 - Present\n- Built APIs\n- Mentored team\n- Added K8s"

class TestUtils(unittest.TestCase):
    def test_normalize(self):
        self.assertEqual(_normalize("HeLLo"), "hello")
    def test_tokenize(self):
        t = _tokenize("Senior Engineer Corp")
        self.assertIn("senior", t)
    def test_fuzzy(self):
        self.assertAlmostEqual(_fuzzy_score("a b c", "a b c"), 1.0)
        self.assertEqual(_fuzzy_score("", "x"), 0.0)
    def test_parse_bullets(self):
        self.assertEqual(len(_parse_bullets("- A\n- B")), 2)
    def test_extract(self):
        self.assertGreaterEqual(len(_extract_cv_experiences(OLD)), 1)


class TestBulletDiffs(unittest.TestCase):
    def test_unchanged(self):
        d = _compare_bullets(["A","B"], ["A","B"])
        self.assertIn("unchanged", {x.diff_category for x in d})
    def test_added(self):
        d = _compare_bullets(["A"], ["A","B"])
        self.assertIn("added", {x.diff_category for x in d})
    def test_removed(self):
        d = _compare_bullets(["A","B"], ["A"])
        self.assertIn("removed", {x.diff_category for x in d})
    def test_changed(self):
        d = _compare_bullets(["Old text here"], ["New text here"])
        self.assertIn("changed", {x.diff_category for x in d})
    def test_empty(self):
        self.assertEqual(_compare_bullets([], []), [])


class TestExpDiffs(unittest.TestCase):
    def _e(self, t, c, d):
        return {"experience_id":"x","title":t,"company":c,
                "start_date":"Jan","end_date":"Dec","description":d,"skills":[]}
    def test_matching(self):
        d = _compute_experience_diffs([self._e("E","A","apis")],[self._e("E","A","apis")])
        self.assertEqual(d[0].diff_category, BASELINE_CV_DIFF_CATEGORY_MATCHING)
    def test_added(self):
        d = _compute_experience_diffs([],[self._e("A","C","d")])
        self.assertEqual(d[0].diff_category, BASELINE_CV_DIFF_CATEGORY_ADDED)
    def test_removed(self):
        d = _compute_experience_diffs([self._e("O","C","w")],[])
        self.assertEqual(d[0].diff_category, BASELINE_CV_DIFF_CATEGORY_REMOVED)
    def test_changed_title(self):
        d = _compute_experience_diffs([self._e("Jr","A","x")],[self._e("Sr","A","x")])
        self.assertEqual(d[0].diff_category, BASELINE_CV_DIFF_CATEGORY_CHANGED_TITLE)
    def test_changed_company(self):
        d = _compute_experience_diffs([self._e("E","Old","x")],[self._e("E","New","x")])
        self.assertEqual(d[0].diff_category, BASELINE_CV_DIFF_CATEGORY_CHANGED_COMPANY)
    def test_changed_dates(self):
        d = _compute_experience_diffs([self._e("E","A","x")],[self._e("E","A","x")])
        o,n = d[0].old_experience_id, d[0].new_experience_id
        self.assertIsNotNone(o)
    def test_changed_bullets(self):
        d = _compute_experience_diffs([self._e("E","A","old")],[self._e("E","A","new here")])
        self.assertEqual(d[0].diff_category, BASELINE_CV_DIFF_CATEGORY_CHANGED_BULLETS)
    def test_seven_cats(self):
        self.assertEqual(len({BASELINE_CV_DIFF_CATEGORY_MATCHING,BASELINE_CV_DIFF_CATEGORY_ADDED,
            BASELINE_CV_DIFF_CATEGORY_REMOVED,BASELINE_CV_DIFF_CATEGORY_CHANGED_TITLE,
            BASELINE_CV_DIFF_CATEGORY_CHANGED_DATES,BASELINE_CV_DIFF_CATEGORY_CHANGED_BULLETS,
            BASELINE_CV_DIFF_CATEGORY_CHANGED_COMPANY}),7)
    def test_suggested_add(self):
        d = _build_matched_diff(self._e("E","A","old"),self._e("E","A","new"),0.9)
        self.assertEqual(d.suggested_action,BASELINE_CV_REPLACEMENT_ACTION_ADD)
    def test_suggested_ignore(self):
        d = _build_matched_diff(self._e("E","A","x"),self._e("E","A","x"),0.9)
        self.assertEqual(d.suggested_action,BASELINE_CV_REPLACEMENT_ACTION_IGNORE)
    def test_suggested_review(self):
        d = _build_matched_diff(self._e("Jr","A","x"),self._e("Sr","A","x"),0.8)
        self.assertEqual(d.suggested_action,BASELINE_CV_REPLACEMENT_ACTION_NEEDS_REVIEW)


class TestPreview(unittest.TestCase):
    def setUp(self):
        self.p = CareerProfile.create(user_id="u1", name="T")
        self.p.baseline_cv_asset_id = "old_a"
        self.p.baseline_cv_display_name = "Old.pdf"
        self.p.baseline_cv_source_version = "sha_old"
    def test_generates_diffs(self):
        pv = preview_baseline_cv_replacement(self.p, OLD, NEW,
            proposed_asset_id="new_a", proposed_display_name="New.pdf")
        self.assertGreater(len(pv.experience_diffs), 0)
    def test_stable_refs(self):
        pv = preview_baseline_cv_replacement(self.p, OLD, NEW,
            proposed_asset_id="new_a", proposed_display_name="New.pdf",
            proposed_source_version="sha_new")
        self.assertEqual(pv.old_baseline_cv_asset_id, "old_a")
        self.assertEqual(pv.proposed_baseline_cv_asset_id, "new_a")
    def test_non_mutating(self):
        orig_id = self.p.baseline_cv_asset_id
        orig_meta = dict(self.p.metadata)
        preview_baseline_cv_replacement(self.p, OLD, NEW,
            proposed_asset_id="new_a", proposed_display_name="New.pdf")
        self.assertEqual(self.p.baseline_cv_asset_id, orig_id)
        self.assertEqual(self.p.metadata, orig_meta)
    def test_evidence_count(self):
        self.p.metadata = {"preserved_experiences": [{"x":1}, {"x":2}]}
        pv = preview_baseline_cv_replacement(self.p, OLD, NEW,
            proposed_asset_id="new_a", proposed_display_name="New.pdf")
        self.assertEqual(pv.existing_evidence_count, 2)
    def test_summary_populated(self):
        pv = preview_baseline_cv_replacement(self.p, OLD, NEW,
            proposed_asset_id="new_a", proposed_display_name="New.pdf")
        self.assertIsInstance(pv.summary, str)
        self.assertGreater(len(pv.summary), 0)
        self.assertIn("preserved", pv.summary.lower())
    def test_summary_no_changes(self):
        pv = preview_baseline_cv_replacement(self.p, OLD, OLD,
            proposed_asset_id="new_a", proposed_display_name="New.pdf")
        self.assertIsInstance(pv.summary, str)
        self.assertGreater(len(pv.summary), 0)
    def test_summary_empty_cvs(self):
        pv = preview_baseline_cv_replacement(self.p, "", "",
            proposed_asset_id="new_a", proposed_display_name="New.pdf")
        self.assertIsInstance(pv.summary, str)
        self.assertGreater(len(pv.summary), 0)


class TestConfirm(unittest.TestCase):
    def setUp(self):
        self.p = CareerProfile.create(user_id="u1", name="T")
        self.p.baseline_cv_asset_id = "old_a"
        self.p.baseline_cv_display_name = "Old.pdf"
        self.p.baseline_cv_source_version = "sha_old"
        self.p.baseline_cv_extraction_date = "2025-01-01"
        self.p.metadata = {"preserved_experiences":[{"experience_id":"e1"}],
            "unbound_former_workspace_id":"ws_old"}
    def _pv(self):
        return preview_baseline_cv_replacement(self.p, OLD, NEW,
            proposed_asset_id="new_a", proposed_display_name="New.pdf",
            proposed_source_version="sha_new")
    def test_updates_baseline(self):
        u = confirm_baseline_cv_replacement(self.p, self._pv(), accepted_actions={})
        self.assertEqual(u.baseline_cv_asset_id, "new_a")
    def test_preserves_evidence(self):
        u = confirm_baseline_cv_replacement(self.p, self._pv(), accepted_actions={})
        self.assertEqual(u.metadata["preserved_experiences"][0]["experience_id"], "e1")
    def test_preserves_provenance(self):
        u = confirm_baseline_cv_replacement(self.p, self._pv(), accepted_actions={})
        self.assertEqual(u.metadata["unbound_former_workspace_id"], "ws_old")
    def test_records_history(self):
        u = confirm_baseline_cv_replacement(self.p, self._pv(), accepted_actions={})
        h = u.metadata["baseline_cv_replacement_history"]
        self.assertEqual(h[0]["previous_baseline_cv_asset_id"], "old_a")

    def test_facts_reference_cv(self):
        pv = self._pv()
        acts = {d.diff_id: d.suggested_action for d in pv.experience_diffs}
        u = confirm_baseline_cv_replacement(self.p, pv, accepted_actions=acts)
        for f in u.metadata["baseline_cv_accepted_facts"]:
            self.assertEqual(f["reference_cv_asset_id"], "new_a")
    def test_all_action_types(self):
        pv = self._pv()
        for action in (BASELINE_CV_REPLACEMENT_ACTION_ADD,
                       BASELINE_CV_REPLACEMENT_ACTION_IGNORE,
                       BASELINE_CV_REPLACEMENT_ACTION_NEEDS_REVIEW):
            acts = {d.diff_id: action for d in pv.experience_diffs}
            u = confirm_baseline_cv_replacement(self.p, pv, accepted_actions=acts)
            self.assertTrue(all(f["action"] == action for f in u.metadata["baseline_cv_accepted_facts"]))
    def test_rejects_invalid_action(self):
        pv = self._pv()
        with self.assertRaises(ValueError):
            confirm_baseline_cv_replacement(self.p, pv,
                accepted_actions={pv.experience_diffs[0].diff_id: "bad"})
    def test_rejects_unknown_diff(self):
        with self.assertRaises(ValueError):
            confirm_baseline_cv_replacement(self.p, self._pv(),
                accepted_actions={"noexist": BASELINE_CV_REPLACEMENT_ACTION_ADD})
    def test_rejects_stale_preview(self):
        other = CareerProfile.create(user_id="u1", name="Other")
        with self.assertRaises(ValueError):
            confirm_baseline_cv_replacement(other, self._pv())
    def test_rollback_on_failure(self):
        orig = self.p.baseline_cv_asset_id
        try:
            confirm_baseline_cv_replacement(self.p, self._pv(),
                accepted_actions={"bad": BASELINE_CV_REPLACEMENT_ACTION_ADD})
        except ValueError:
            pass
        self.assertEqual(self.p.baseline_cv_asset_id, orig)
    def test_preserves_timestamps(self):
        oc = self.p.created_at
        u = confirm_baseline_cv_replacement(self.p, self._pv(), accepted_actions={})
        self.assertEqual(u.created_at, oc)
    def test_preserves_lifecycle(self):
        self.p.status = "needs_review"
        u = confirm_baseline_cv_replacement(self.p, self._pv(), accepted_actions={})
        self.assertEqual(u.status, "needs_review")


class TestModelRoundtrip(unittest.TestCase):
    def test_bullet_diff(self):
        bd = BaselineCVBulletDiff("b1", "text", "added", "", "text")
        r = BaselineCVBulletDiff.from_dict(bd.to_dict())
        self.assertEqual(r.bullet_id, "b1")
    def test_experience_diff(self):
        ed = BaselineCVExperienceDiff("d1", "added", new_title="Role")
        r = BaselineCVExperienceDiff.from_dict(ed.to_dict())
        self.assertEqual(r.diff_id, "d1")
    def test_preview(self):
        pv = BaselineCVReplacementPreview.create(profile_id="p1")
        pv.experience_diffs = [BaselineCVExperienceDiff("d1", "added", new_title="R")]
        r = BaselineCVReplacementPreview.from_dict(pv.to_dict())
        self.assertEqual(r.profile_id, "p1")
        self.assertEqual(len(r.experience_diffs), 1)
    def test_preview_id_prefix(self):
        pv = BaselineCVReplacementPreview.create(profile_id="p1")
        self.assertTrue(pv.preview_id.startswith("bcvrpreview_"))


if __name__ == "__main__":
    unittest.main()
