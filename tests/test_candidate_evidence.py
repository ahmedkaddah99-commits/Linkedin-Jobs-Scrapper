"""Tests for candidate evidence extraction (CP-009)."""

import unittest

from backend.domain.candidate_evidence import (
    CandidateEvidence,
    EVIDENCE_STATUS_CONFIRMED,
    EVIDENCE_STATUS_CONFLICT,
    EVIDENCE_STATUS_MERGED,
    EVIDENCE_STATUS_NEEDS_REVIEW,
    EVIDENCE_STATUS_REJECTED,
    EVIDENCE_TYPE_ACHIEVEMENT,
    EVIDENCE_TYPE_CERTIFICATION,
    EVIDENCE_TYPE_EDUCATION,
    EVIDENCE_TYPE_METRIC,
    EVIDENCE_TYPE_RESPONSIBILITY,
    EVIDENCE_TYPE_TOOL,
    classify_evidence_type,
    compute_content_hash,
)

from backend.capabilities.candidate_evidence.extraction import (
    extract_evidence_from_source,
    extract_evidence_from_verified_sources,
    build_evidence_summary,
)

from backend.capabilities.candidate_evidence.deduplication import (
    find_duplicate_groups,
    apply_duplicate_groups,
    deduplicate_evidence,
)

from backend.capabilities.candidate_evidence.conflict_detection import (
    detect_conflicts,
    detect_and_apply_conflicts,
)

from backend.capabilities.candidate_evidence import run_evidence_pipeline



class CandidateEvidenceModelTests(unittest.TestCase):

    def test_create_defaults(self):
        ev = CandidateEvidence.create(text="Managed a team of 5 engineers.")
        self.assertTrue(ev.evidence_id.startswith("ev_"))
        self.assertEqual(ev.status, EVIDENCE_STATUS_NEEDS_REVIEW)
        self.assertTrue(ev.needs_review)
        self.assertFalse(ev.is_confirmed)
        self.assertTrue(ev.content_hash)

    def test_create_with_all_fields(self):
        ev = CandidateEvidence.create(
            profile_id="prof_1",
            evidence_type=EVIDENCE_TYPE_ACHIEVEMENT,
            text="Increased revenue by 30% in Q1.",
            source_asset="resume.pdf",
            source_id="src_1",
            excerpt="Increased revenue by 30% in Q1.",
            location="page 2, line 5",
            confidence=0.95,
            inferred_employer="Acme Corp",
            inferred_role="Senior Product Manager",
            dates=["Jan 2020 – Dec 2022"],
            source_confidence=0.98,
        )
        self.assertEqual(ev.profile_id, "prof_1")
        self.assertEqual(ev.evidence_type, EVIDENCE_TYPE_ACHIEVEMENT)
        self.assertEqual(ev.source_asset, "resume.pdf")
        self.assertEqual(ev.source_id, "src_1")
        self.assertEqual(ev.inferred_employer, "Acme Corp")
        self.assertEqual(ev.inferred_role, "Senior Product Manager")
        self.assertEqual(ev.dates, ["Jan 2020 – Dec 2022"])

    def test_confirm_and_reject(self):
        ev = CandidateEvidence.create(text="Test evidence.")
        ev.confirm()
        self.assertEqual(ev.status, EVIDENCE_STATUS_CONFIRMED)
        self.assertTrue(ev.is_confirmed)
        ev2 = CandidateEvidence.create(text="Bad evidence.")
        ev2.reject()
        self.assertEqual(ev2.status, EVIDENCE_STATUS_REJECTED)

    def test_mark_merged(self):
        ev = CandidateEvidence.create(text="Duplicate text")
        ev.mark_merged("ev_primary")
        self.assertTrue(ev.is_merged)
        self.assertEqual(ev.duplicate_group_id, "ev_primary")

    def test_mark_conflict(self):
        ev = CandidateEvidence.create(text="Conflicting metric")
        ev.mark_conflict(["ev_other_1", "ev_other_2"])
        self.assertTrue(ev.is_conflicting)
        self.assertEqual(ev.conflicting_with, ["ev_other_1", "ev_other_2"])

    def test_roundtrip_to_from_dict(self):
        ev = CandidateEvidence.create(
            profile_id="p1", evidence_type=EVIDENCE_TYPE_METRIC,
            text="Saved $500K annually.", source_asset="cv.pdf",
            source_id="s1", excerpt="Saved $500K annually.",
            location="line 10", confidence=0.88,
            inferred_employer="TechCo", inferred_role="Engineering Manager",
            dates=["2019 – 2021"],
        )
        ev.confirm()
        payload = ev.to_dict()
        restored = CandidateEvidence.from_dict(payload)
        self.assertEqual(restored.evidence_id, ev.evidence_id)
        self.assertEqual(restored.text, "Saved $500K annually.")
        self.assertEqual(restored.status, EVIDENCE_STATUS_CONFIRMED)
        self.assertEqual(restored.inferred_employer, "TechCo")

    def test_content_hash_stable(self):
        ev1 = CandidateEvidence.create(text="  Managed   team  of 5.  ")
        ev2 = CandidateEvidence.create(text="Managed team of 5.")
        self.assertEqual(ev1.content_hash, ev2.content_hash)

    def test_content_hash_different(self):
        ev1 = CandidateEvidence.create(text="Managed team of 5.")
        ev2 = CandidateEvidence.create(text="Led team of 10 engineers.")
        self.assertNotEqual(ev1.content_hash, ev2.content_hash)


class EvidenceTypeClassificationTests(unittest.TestCase):

    def test_classify_metric(self):
        self.assertEqual(classify_evidence_type("Increased revenue by 30%"), EVIDENCE_TYPE_METRIC)
        self.assertEqual(classify_evidence_type("Saved $500K annually"), EVIDENCE_TYPE_METRIC)

    def test_classify_achievement(self):
        self.assertEqual(classify_evidence_type("Improved delivery speed across teams"), EVIDENCE_TYPE_ACHIEVEMENT)

    def test_classify_certification(self):
        self.assertEqual(classify_evidence_type("AWS Certified Solutions Architect"), EVIDENCE_TYPE_CERTIFICATION)

    def test_classify_education(self):
        self.assertEqual(classify_evidence_type("Master degree in Computer Science"), EVIDENCE_TYPE_EDUCATION)

    def test_classify_tool(self):
        self.assertEqual(classify_evidence_type("Built pipelines with Python and SQL"), EVIDENCE_TYPE_TOOL)



class EvidenceExtractionTests(unittest.TestCase):

    def test_extract_empty_text(self):
        result = extract_evidence_from_source(
            profile_id="p1", source_id="s1", text="",
            source_asset="empty.txt", confidence=1.0,
        )
        self.assertEqual(result, [])

    def test_extract_single_sentence(self):
        result = extract_evidence_from_source(
            profile_id="p1", source_id="s1",
            text="Managed a team of 5 engineers to deliver the platform.",
            source_asset="cv.pdf", confidence=0.95,
        )
        self.assertEqual(len(result), 1)
        ev = result[0]
        self.assertEqual(ev.profile_id, "p1")
        self.assertEqual(ev.source_id, "s1")
        self.assertEqual(ev.source_asset, "cv.pdf")
        self.assertEqual(ev.status, EVIDENCE_STATUS_NEEDS_REVIEW)

    def test_extract_multiple_sentences(self):
        result = extract_evidence_from_source(
            profile_id="p1", source_id="s2",
            text="Led cross-functional team of 10. Increased revenue by 30% in Q1. Used Python and SQL for pipelines.",
            source_asset="resume.pdf", confidence=0.90,
        )
        self.assertEqual(len(result), 3)

    def test_extract_with_headings_and_dates(self):
        result = extract_evidence_from_source(
            profile_id="p1", source_id="s3",
            text="Built reporting dashboard for stakeholders.",
            source_asset="cv.pdf", confidence=0.85,
            headings=["Acme Corp | Senior Developer"],
            dates=["2020 – 2022"],
        )
        ev = result[0]
        self.assertEqual(ev.inferred_employer, "Acme Corp")

    def test_sentences_too_short_excluded(self):
        result = extract_evidence_from_source(
            profile_id="p1", source_id="s4",
            text="Yes. No. Ok.", source_asset="cv.pdf", confidence=0.9,
        )
        self.assertEqual(len(result), 0)

    def test_extract_from_verified_sources(self):
        verified = [
            {"source_id": "src_a", "file_name": "a.pdf",
             "text": "Managed team of 5. Increased revenue 40%.", "confidence": 0.95},
            {"source_id": "src_b", "file_name": "b.pdf",
             "text": "AWS Certified Developer. Led migration project.", "confidence": 0.88},
        ]
        result = extract_evidence_from_verified_sources("prof_1", verified)
        self.assertGreaterEqual(len(result), 4)

    def test_build_evidence_summary(self):
        ev1 = CandidateEvidence.create(text="Managed team", evidence_type=EVIDENCE_TYPE_RESPONSIBILITY)
        ev2 = CandidateEvidence.create(text="Increased revenue 30%", evidence_type=EVIDENCE_TYPE_METRIC)
        ev3 = CandidateEvidence.create(text="Used Python", evidence_type=EVIDENCE_TYPE_TOOL)
        summary = build_evidence_summary([ev1, ev2, ev3])


class DeduplicationTests(unittest.TestCase):

    def test_exact_duplicate_detection(self):
        ev1 = CandidateEvidence.create(text="Managed team of 5 engineers.")
        ev2 = CandidateEvidence.create(text="Managed team of 5 engineers.")
        ev3 = CandidateEvidence.create(text="Completely different content here yes.")
        items = [ev1, ev2, ev3]
        groups = find_duplicate_groups(items)
        self.assertGreaterEqual(len(groups), 1)

    def test_no_duplicates_for_unique_texts(self):
        ev1 = CandidateEvidence.create(text="Managed team of 5 engineers for cloud migration.")
        ev2 = CandidateEvidence.create(text="Designed new product features using React and Node.")
        ev3 = CandidateEvidence.create(text="Automated CI/CD pipeline deployment process end to end.")
        groups = find_duplicate_groups([ev1, ev2, ev3])
        self.assertEqual(len(groups), 0)

    def test_apply_duplicate_groups_marks_merged(self):
        ev1 = CandidateEvidence.create(text="Managed team of 5 engineers.")
        ev2 = CandidateEvidence.create(text="Managed team of 5 engineers.")
        items = [ev1, ev2]
        groups = find_duplicate_groups(items)
        apply_duplicate_groups(items, groups)
        merged = [ev for ev in items if ev.is_merged]
        self.assertGreaterEqual(len(merged), 1)

    def test_deduplicate_evidence_summary(self):
        ev1 = CandidateEvidence.create(text="Managed team of 5 engineers.")
        ev2 = CandidateEvidence.create(text="Managed team of 5 engineers.")
        ev3 = CandidateEvidence.create(text="Unique content here yes indeed.")
        result = deduplicate_evidence([ev1, ev2, ev3])
        self.assertIn("duplicate_groups", result)
        self.assertIn("merged_items", result)

        self.assertEqual(summary["total_evidence"], 3)
        self.assertEqual(summary["by_type"]["metric"], 1)
        self.assertEqual(summary["needs_review_count"], 3)

    def test_classify_default_responsibility(self):
        self.assertEqual(classify_evidence_type("Responsible for daily operations"), EVIDENCE_TYPE_RESPONSIBILITY)

        ev1 = CandidateEvidence.create(text="Managed team of 5.")
        ev2 = CandidateEvidence.create(text="Led team of 10 engineers.")


class ConflictDetectionTests(unittest.TestCase):

    def test_metric_conflict_different_numbers(self):
        ev1 = CandidateEvidence.create(text="Increased revenue by 30%", evidence_type=EVIDENCE_TYPE_METRIC)
        ev2 = CandidateEvidence.create(text="Increased revenue by 50%", evidence_type=EVIDENCE_TYPE_METRIC)
        conflicts = detect_conflicts([ev1, ev2])
        self.assertIn(ev1.evidence_id, conflicts)

    def test_employer_conflict(self):
        ev1 = CandidateEvidence.create(text="Managed engineering team", evidence_type=EVIDENCE_TYPE_RESPONSIBILITY, inferred_employer="Acme Corp")
        ev2 = CandidateEvidence.create(text="Led technical operations", evidence_type=EVIDENCE_TYPE_RESPONSIBILITY, inferred_employer="Beta Inc")
        conflicts = detect_conflicts([ev1, ev2])
        self.assertIn(ev1.evidence_id, conflicts)

    def test_no_conflict_different_types(self):
        ev1 = CandidateEvidence.create(text="Used Python for data pipelines", evidence_type=EVIDENCE_TYPE_TOOL, inferred_employer="Acme")
        ev2 = CandidateEvidence.create(text="Managed stakeholder communications", evidence_type=EVIDENCE_TYPE_RESPONSIBILITY, inferred_employer="Beta")
        conflicts = detect_conflicts([ev1, ev2])
        self.assertNotIn(ev1.evidence_id, conflicts)

    def test_apply_conflicts_marks_status(self):
        ev1 = CandidateEvidence.create(text="Revenue up 25%", evidence_type=EVIDENCE_TYPE_METRIC)
        ev2 = CandidateEvidence.create(text="Revenue up 45%", evidence_type=EVIDENCE_TYPE_METRIC)
        detect_and_apply_conflicts([ev1, ev2])
        self.assertTrue(ev1.is_conflicting or ev2.is_conflicting)

    def test_merged_items_excluded_from_conflicts(self):
        ev1 = CandidateEvidence.create(text="Revenue up 25%", evidence_type=EVIDENCE_TYPE_METRIC)
        ev2 = CandidateEvidence.create(text="Revenue up 25%", evidence_type=EVIDENCE_TYPE_METRIC)
        ev2.mark_merged(ev1.evidence_id)
        conflicts = detect_conflicts([ev1, ev2])
        self.assertNotIn(ev2.evidence_id, conflicts)


class EvidencePipelineIntegrationTests(unittest.TestCase):

    def test_empty_verified_texts(self):
        result = run_evidence_pipeline("prof_1", [])
        self.assertEqual(result["profile_id"], "prof_1")
        self.assertEqual(result["extraction"]["total_evidence"], 0)

    def test_full_pipeline_single_source(self):
        verified = [{"source_id": "src_cv", "file_name": "my_cv.pdf",
                     "text": "Managed team of 5. Increased revenue 30%. Used Python and SQL.",
                     "confidence": 0.95}]
        result = run_evidence_pipeline("prof_test", verified)
        self.assertGreaterEqual(result["extraction"]["total_evidence"], 3)
        self.assertIn("by_type", result["extraction"])

    def test_full_pipeline_multi_source_dedupes(self):
        verified = [
            {"source_id": "src_a", "file_name": "cv_a.pdf",
             "text": "Managed team of 5 engineers for cloud platform.",
             "confidence": 0.95},
            {"source_id": "src_b", "file_name": "cover_letter.pdf",
             "text": "Managed team of 5 engineers for cloud platform. Also increased revenue.",
             "confidence": 0.90},
        ]
        result = run_evidence_pipeline("prof_multi", verified)
        self.assertGreaterEqual(result["extraction"]["total_evidence"], 1)

    def test_pipeline_evidence_has_provenance(self):
        verified = [{"source_id": "src_z", "file_name": "z.pdf",
                     "text": "Managed global operations team.", "confidence": 0.92}]
        result = run_evidence_pipeline("prof_prov", verified)
        for ev_dict in result["evidence"]:
            self.assertEqual(ev_dict["source_id"], "src_z")
            self.assertEqual(ev_dict["source_asset"], "z.pdf")
            self.assertGreater(ev_dict["source_confidence"], 0)

    def test_pipeline_initial_status_needs_review(self):
        verified = [{"source_id": "src_r", "file_name": "r.pdf",
                     "text": "Delivered complex system migration on time and budget.",
                     "confidence": 0.88}]
        result = run_evidence_pipeline("prof_review", verified)
        needs_review = [ev for ev in result["evidence"]
                        if ev["status"] == EVIDENCE_STATUS_NEEDS_REVIEW
                        and not ev.get("duplicate_group_id")]
        self.assertGreaterEqual(len(needs_review), 1)


if __name__ == "__main__":
    unittest.main()
