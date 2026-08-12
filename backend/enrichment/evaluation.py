"""Offline deterministic evaluation for the inactive enrichment foundation.

This module is deliberately a pure trial runner.  It reads sanitized checked-in
fixtures, calls only the local fixture/Null providers, and returns immutable
trial records.  It has no persistence, network, AI, publication, or production
activation boundary.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
import hashlib
import json
import re
from types import MappingProxyType
from typing import Any

from .boundaries import (
    build_company_request,
    build_occupation_request,
    build_place_requests,
    company_identity_can_auto_link,
    extract_language_evidence,
    language_state,
    normalize_text,
)
from .cache import input_fingerprint
from .contracts import EnrichmentProvider, ProviderExecutionContext, ProviderResultState
from .fixture import load_evaluation_fixture, load_golden_labels, validate_fixture_privacy
from .providers import FixtureCompanyProvider, FixtureOccupationProvider, FixturePlaceProvider, NullProvider


PARTITIONS = ("development", "calibration", "blind_holdout")
DIMENSIONS = ("place_normalization", "company_profile", "occupation_function", "language_evidence")
ALLOWED_PROMOTION_RECOMMENDATIONS = frozenset(
    {"reject", "continue shadow evaluation", "eligible for human-review trial"}
)
DEFAULT_RULE_VERSION = "deterministic_trial_rules_v1"
ALTERNATE_RULE_VERSION = "deterministic_trial_rules_v2"
ADVERSARIAL_CATEGORIES = {
    "ambiguous Paris": ("cal_unqualified_paris",),
    "Lowell employer plus Leeds": ("dev_lowell_employer_leeds", "blind_lowell_leeds_name_order"),
    "Lowell, Massachusetts": ("dev_lowell_massachusetts",),
    "multiple locations": ("dev_multiple_locations",),
    "Remote Germany/EU/unrestricted": (
        "dev_remote_germany",
        "dev_remote_eu",
        "cal_remote_without_scope",
        "dev_remote_unrestricted",
        "blind_remote_scope_missing",
    ),
    "department/title conflict": ("cal_contradictory_department_title",),
    "internship and working-student separation": ("dev_internship_title", "dev_german_title", "blind_working_student_professional_duties"),
    "posting language without language requirement": (
        "dev_posting_written_in_language_only",
        "blind_language_in_boilerplate",
    ),
}


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, set):
        return frozenset(_freeze(item) for item in value)
    return value


def _jsonable(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list, frozenset)):
        return [_jsonable(item) for item in value]
    return value


def _stable_json(value: Any) -> str:
    return json.dumps(_jsonable(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha256(value: Any) -> str:
    return hashlib.sha256(_stable_json(value).encode("utf-8")).hexdigest()


def _now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


@dataclass(frozen=True, slots=True)
class AdjudicationMetadata:
    status: str
    annotator_count: int
    adjudicator: str
    reviewed_at: str
    rationale: str = ""

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "AdjudicationMetadata":
        return cls(
            status=str(payload.get("status") or ""),
            annotator_count=int(payload.get("annotator_count") or 0),
            adjudicator=str(payload.get("adjudicator") or ""),
            reviewed_at=str(payload.get("reviewed_at") or ""),
            rationale=str(payload.get("rationale") or ""),
        )


@dataclass(frozen=True, slots=True)
class GoldenLabel:
    fixture_id: str
    split: str
    labels: Mapping[str, Any]
    adjudication: AdjudicationMetadata

    def __post_init__(self) -> None:
        object.__setattr__(self, "labels", _freeze(self.labels))

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "GoldenLabel":
        return cls(
            fixture_id=str(payload["fixture_id"]),
            split=str(payload["split"]),
            labels=payload["labels"],
            adjudication=AdjudicationMetadata.from_mapping(payload["adjudication"]),
        )


@dataclass(frozen=True, slots=True)
class TrialConfig:
    trial_id: str = "offline_deterministic_enrichment_trial"
    fixture_version: str = "runr_fixture_v1"
    rule_versions: tuple[str, ...] = (DEFAULT_RULE_VERSION,)
    partitions: tuple[str, ...] = PARTITIONS
    provider_mode: str = "offline_fixture_only"
    allow_network: bool = False
    allow_ai: bool = False
    allow_production_writes: bool = False
    publication_active: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "rule_versions", tuple(self.rule_versions))
        object.__setattr__(self, "partitions", tuple(self.partitions))
        invalid = set(self.partitions) - set(PARTITIONS)
        if invalid:
            raise ValueError(f"Unsupported trial partitions: {sorted(invalid)}")
        if not self.rule_versions:
            raise ValueError("At least one rule version is required")
        if self.provider_mode != "offline_fixture_only" or self.allow_network or self.allow_ai:
            raise ValueError("Offline trial configuration cannot enable network or AI")
        if self.allow_production_writes or self.publication_active:
            raise ValueError("Offline trial configuration cannot write production data or publish")

    @property
    def fingerprint(self) -> str:
        return _sha256(
            {
                "trial_id": self.trial_id,
                "fixture_version": self.fixture_version,
                "rule_versions": self.rule_versions,
                "partitions": self.partitions,
                "provider_mode": self.provider_mode,
                "allow_network": self.allow_network,
                "allow_ai": self.allow_ai,
                "allow_production_writes": self.allow_production_writes,
                "publication_active": self.publication_active,
            }
        )


@dataclass(frozen=True, slots=True)
class TrialOutput:
    fixture_id: str
    split: str
    connector: str
    dimension: str
    target_id: str
    result_state: str
    predicted: Mapping[str, Any]
    candidate_ids: tuple[str, ...] = ()
    confidence: float | None = None
    ambiguous: bool = False
    input_fingerprint: str = ""
    warnings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.dimension not in DIMENSIONS:
            raise ValueError(f"Unsupported trial dimension: {self.dimension}")
        object.__setattr__(self, "predicted", _freeze(self.predicted))
        object.__setattr__(self, "candidate_ids", tuple(self.candidate_ids))
        object.__setattr__(self, "warnings", tuple(self.warnings))
        if self.confidence is not None and not 0 <= self.confidence <= 1:
            raise ValueError("Trial confidence must be between 0 and 1")


@dataclass(frozen=True, slots=True)
class TrialRun:
    run_id: str
    config: TrialConfig
    rule_version: str
    fixture_fingerprint: str
    observation_ids: tuple[str, ...]
    outputs: tuple[TrialOutput, ...]
    report: Mapping[str, Any]
    created_at: str = field(default_factory=_now_iso)

    def __post_init__(self) -> None:
        object.__setattr__(self, "observation_ids", tuple(self.observation_ids))
        object.__setattr__(self, "outputs", tuple(self.outputs))
        object.__setattr__(self, "report", _freeze(self.report))


@dataclass(frozen=True, slots=True)
class ReplayComparison:
    baseline_run_id: str
    candidate_run_id: str
    baseline_rule_version: str
    candidate_rule_version: str
    compared_outputs: int
    changed_outputs: int
    changes_by_dimension: Mapping[str, int]
    changed_fixture_ids: tuple[str, ...]
    regression_candidates: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "changes_by_dimension", _freeze(self.changes_by_dimension))
        object.__setattr__(self, "changed_fixture_ids", tuple(self.changed_fixture_ids))
        object.__setattr__(self, "regression_candidates", tuple(self.regression_candidates))


def _normalise_label(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, bool):
        return value
    if isinstance(value, Mapping):
        return _stable_json(value)
    return str(value)


def _safe_div(numerator: float, denominator: float) -> float | None:
    return round(numerator / denominator, 6) if denominator else None


def _classification_metrics(pairs: Sequence[tuple[Any, Any]]) -> dict[str, Any]:
    if not pairs:
        return {
            "evaluated": 0,
            "precision": None,
            "recall": None,
            "f1": None,
            "macro_f1": None,
            "false_positive_rate": None,
        }
    normalised = [(_normalise_label(gold), _normalise_label(pred)) for gold, pred in pairs]
    labels = sorted({item for pair in normalised for item in pair}, key=str)
    per_class: list[dict[str, float]] = []
    total_tp = total_fp = total_fn = 0
    for label in labels:
        tp = sum(gold == label and pred == label for gold, pred in normalised)
        fp = sum(gold != label and pred == label for gold, pred in normalised)
        fn = sum(gold == label and pred != label for gold, pred in normalised)
        total_tp += tp
        total_fp += fp
        total_fn += fn
        precision = _safe_div(tp, tp + fp) or 0.0
        recall = _safe_div(tp, tp + fn) or 0.0
        per_class.append({"precision": precision, "recall": recall, "f1": _safe_div(2 * precision * recall, precision + recall) or 0.0})
    negative = {"", "none", "unknown", "not_established", "not_applicable", "no_match", "unrestricted"}
    false_positives = sum(pred not in negative and gold in negative for gold, pred in normalised)
    actual_negatives = sum(gold in negative for gold, _ in normalised)
    return {
        "evaluated": len(normalised),
        "precision": _safe_div(total_tp, total_tp + total_fp),
        "recall": _safe_div(total_tp, total_tp + total_fn),
        "f1": _safe_div(2 * total_tp, 2 * total_tp + total_fp + total_fn),
        "macro_f1": round(sum(item["f1"] for item in per_class) / len(per_class), 6),
        "false_positive_rate": _safe_div(false_positives, actual_negatives),
    }


def _calibration_metrics(pairs: Sequence[tuple[float, bool]]) -> dict[str, Any]:
    if not pairs:
        return {
            "available": False,
            "confidence_count": 0,
            "expected_calibration_error": None,
            "brier_score": None,
            "data_gap": "fixture providers did not supply confidence scores",
        }
    bins: dict[int, list[tuple[float, bool]]] = defaultdict(list)
    for confidence, correct in pairs:
        bins[min(9, int(confidence * 10))].append((confidence, correct))
    ece = 0.0
    for values in bins.values():
        ece += len(values) / len(pairs) * abs(sum(item[0] for item in values) / len(values) - sum(item[1] for item in values) / len(values))
    return {
        "available": True,
        "confidence_count": len(pairs),
        "expected_calibration_error": round(ece, 6),
        "brier_score": round(sum((confidence - int(correct)) ** 2 for confidence, correct in pairs) / len(pairs), 6),
        "data_gap": None,
    }


def _scope_state(case: Mapping[str, Any]) -> str:
    if normalize_text(case.get("workplace_arrangement")) != "remote":
        return "not_remote"
    return "bounded" if str(case.get("remote_scope") or "").strip() else "unrestricted"


def _employment_type(title: str) -> str:
    value = normalize_text(title)
    if re.search(r"\b(werkstudent|working student|student assistant)\b", value):
        return "Working student"
    if re.search(r"\b(intern|internship|stagiaire|praktikant)\b", value):
        return "Internship"
    return "Professional"


def _title_function(title: str) -> str:
    value = normalize_text(title)
    if re.search(r"\b(account|sales|revenue)\b", value):
        return "Sales"
    if re.search(r"\b(marketing)\b", value):
        return "Marketing"
    if re.search(r"\b(product manager|product designer)\b", value):
        return "Product"
    if re.search(r"\b(ux|designer|design)\b", value):
        return "Design"
    if re.search(r"\b(comptable|accountant|finance|financial)\b", value):
        return "Finance"
    if re.search(r"\b(data analyst|data scientist|analytics|analyst)\b", value):
        return "Data & Analytics"
    if re.search(r"\b(engineer|engineering|developer|backend|software|technical writer)\b", value):
        return "Engineering"
    if re.search(r"\b(operations|customer support|customer operations)\b", value):
        return "Operations"
    if re.search(r"\b(recruiting|people|human resources)\b", value):
        return "People"
    return ""


def _department_function(department: str) -> str:
    value = normalize_text(department)
    if not value:
        return ""
    if re.search(r"\b(engineering|technology|tech|it)\b", value):
        return "Engineering"
    if re.search(r"\b(marketing)\b", value):
        return "Marketing"
    if re.search(r"\b(finance|accounting)\b", value):
        return "Finance"
    if re.search(r"\b(sales|revenue)\b", value):
        return "Sales"
    if re.search(r"\b(product)\b", value):
        return "Product"
    if re.search(r"\b(design|creative)\b", value):
        return "Design"
    if re.search(r"\b(operations|support)\b", value):
        return "Operations"
    if re.search(r"\b(people|hr|human resources|recruiting)\b", value):
        return "People"
    return ""


class OfflineTrialOrchestrator:
    """Run deterministic trials without storage, networking, AI, or activation."""

    def __init__(
        self,
        config: TrialConfig | None = None,
        *,
        providers: Mapping[str, EnrichmentProvider] | None = None,
        cases: Sequence[Mapping[str, Any]] | None = None,
    ) -> None:
        self.config = config or TrialConfig()
        self.providers = dict(
            providers
            or {
                "place": FixturePlaceProvider(),
                "company": FixtureCompanyProvider(),
                "occupation": FixtureOccupationProvider(),
                "null": NullProvider(),
            }
        )
        self.cases = tuple(dict(case) for case in (cases if cases is not None else load_evaluation_fixture(include_blind_holdout=True)))
        validate_fixture_privacy()
        self._assert_offline_boundary()

    def _assert_offline_boundary(self) -> None:
        allowed = {"null", "fixture_place", "fixture_company", "fixture_occupation"}
        for provider in self.providers.values():
            metadata = provider.metadata()
            if metadata.provider_id not in allowed or metadata.network_required:
                raise ValueError(f"Trial provider is not an approved offline provider: {metadata.provider_id}")

    def _cases_for(self, partitions: Iterable[str] | None) -> tuple[Mapping[str, Any], ...]:
        requested = tuple(partitions or self.config.partitions)
        invalid = set(requested) - set(PARTITIONS)
        if invalid:
            raise ValueError(f"Unsupported trial partitions: {sorted(invalid)}")
        return tuple(case for case in self.cases if case.get("split") in requested)

    def run(
        self,
        *,
        partitions: Iterable[str] | None = None,
        partition: str | None = None,
        rule_version: str | None = None,
    ) -> TrialRun:
        if partition is not None:
            if partitions is not None:
                raise ValueError("Use partition or partitions, not both")
            partitions = (partition,)
        selected_cases = self._cases_for(partitions)
        active_rule_version = rule_version or self.config.rule_versions[0]
        outputs: list[TrialOutput] = []
        for case in selected_cases:
            outputs.extend(self._evaluate_case(case, active_rule_version))
        report = self._build_report(selected_cases, outputs, active_rule_version)
        fixture_fingerprint = _sha256(selected_cases)
        run_id = "trial_run_" + _sha256(
            {"config": self.config.fingerprint, "rule_version": active_rule_version, "fixture": fixture_fingerprint, "partitions": [case.get("split") for case in selected_cases]}
        )[:20]
        return TrialRun(
            run_id=run_id,
            config=self.config,
            rule_version=active_rule_version,
            fixture_fingerprint=fixture_fingerprint,
            observation_ids=tuple(str(case.get("source_observation_id") or case["fixture_id"]) for case in selected_cases),
            outputs=outputs,
            report=report,
        )

    def replay(self, *, baseline_rule_version: str, candidate_rule_version: str, partitions: Iterable[str] | None = None) -> tuple[TrialRun, TrialRun, ReplayComparison]:
        baseline = self.run(partitions=partitions, rule_version=baseline_rule_version)
        candidate = self.run(partitions=partitions, rule_version=candidate_rule_version)
        return baseline, candidate, compare_replays(baseline, candidate)

    def _provider_result(self, provider_key: str, request: Any) -> Any:
        provider = self.providers.get(provider_key) or self.providers["null"]
        return provider.resolve(request, ProviderExecutionContext(allow_network=False, now_iso="2026-08-12T00:00:00+00:00"))

    def _evaluate_case(self, case: Mapping[str, Any], rule_version: str) -> tuple[TrialOutput, ...]:
        return (
            self._evaluate_place(case, rule_version),
            self._evaluate_company(case, rule_version),
            self._evaluate_occupation(case, rule_version),
            self._evaluate_language(case, rule_version),
        )

    def _evaluate_place(self, case: Mapping[str, Any], rule_version: str) -> TrialOutput:
        requests = build_place_requests(
            target_id=str(case["fixture_id"]),
            raw_location=case.get("locations", case.get("location", "")),
            country_code=str(case.get("country_code") or ""),
            region=str(case.get("region") or ""),
            workplace_arrangement=str(case.get("workplace_arrangement") or ""),
            remote_scope=str(case.get("remote_scope") or ""),
            rule_version=rule_version,
        )
        locations: list[dict[str, Any]] = []
        candidate_ids: list[str] = []
        scores: list[float] = []
        states: list[str] = []
        fingerprints: list[str] = []
        for request in requests:
            result = self._provider_result("place", request)
            states.append(str(result.state))
            fingerprints.append(input_fingerprint(request))
            ids = [candidate.candidate_id for candidate in result.candidates]
            candidate_ids.extend(item for item in ids if item not in candidate_ids)
            scores.extend(candidate.provider_score for candidate in result.candidates if candidate.provider_score is not None)
            locations.append({"display": request.input.get("display", ""), "state": str(result.state), "candidate_ids": ids})
        arrangement = str(case.get("workplace_arrangement") or "")
        if not requests:
            state = "not_applicable"
        elif any(item == ProviderResultState.AMBIGUOUS for item in states):
            state = "ambiguous"
        elif any(item == ProviderResultState.MATCHED for item in states):
            state = "matched"
        else:
            state = "no_match"
        predicted = {
            "place_state": state,
            # Ambiguous candidates remain ranked evidence; none is selected or
            # auto-accepted by the trial.
            "place_candidate_id": candidate_ids[0] if candidate_ids and state != "ambiguous" else "",
            "place_candidate_ids": candidate_ids,
            "location_count": len(requests),
            "workplace_arrangement": arrangement,
            "remote_scope": str(case.get("remote_scope") or ""),
            "remote_scope_state": _scope_state(case),
            "locations": locations,
        }
        return TrialOutput(
            fixture_id=str(case["fixture_id"]),
            split=str(case["split"]),
            connector=str(case.get("connector") or "unknown"),
            dimension="place_normalization",
            target_id=str(case["fixture_id"]),
            result_state=state,
            predicted=predicted,
            candidate_ids=tuple(candidate_ids),
            confidence=scores[0] if scores else None,
            ambiguous=state == "ambiguous",
            input_fingerprint=_sha256(fingerprints),
        )

    def _evaluate_company(self, case: Mapping[str, Any], rule_version: str) -> TrialOutput:
        name = str(case.get("company") or "")
        domain = str(case.get("company_domain") or "")
        if not name and not domain:
            predicted = {"company_identity_state": "not_applicable", "company_candidate_id": "", "profile_facts": {}}
            return TrialOutput(str(case["fixture_id"]), str(case["split"]), str(case.get("connector") or "unknown"), "company_profile", str(case["fixture_id"]), "not_applicable", predicted)
        if not company_identity_can_auto_link(name=name, domain=domain):
            predicted = {"company_identity_state": "blocked_name_only", "company_candidate_id": "", "profile_facts": {}}
            return TrialOutput(str(case["fixture_id"]), str(case["split"]), str(case.get("connector") or "unknown"), "company_profile", str(case["fixture_id"]), "blocked_by_policy", predicted, warnings=("name_only_company_link_not_allowed",))
        request = build_company_request(target_id=str(case["fixture_id"]), name=name, domain=domain, rule_version=rule_version)
        result = self._provider_result("company", request)
        candidate_ids = tuple(candidate.candidate_id for candidate in result.candidates)
        profile = result.candidates[0].normalized_value if result.candidates and isinstance(result.candidates[0].normalized_value, Mapping) else {}
        predicted = {
            "company_identity_state": str(result.state),
            "company_candidate_id": candidate_ids[0] if candidate_ids else "",
            "company_candidate_ids": candidate_ids,
            "profile_facts": dict(profile),
            "company_profile": {
                key: profile[key]
                for key in ("company_id", "name", "website")
                if key in profile
            },
        }
        return TrialOutput(
            str(case["fixture_id"]),
            str(case["split"]),
            str(case.get("connector") or "unknown"),
            "company_profile",
            str(case["fixture_id"]),
            str(result.state),
            predicted,
            candidate_ids,
            next((candidate.provider_score for candidate in result.candidates if candidate.provider_score is not None), None),
            len(candidate_ids) > 1,
            input_fingerprint=input_fingerprint(request),
        )

    def _evaluate_occupation(self, case: Mapping[str, Any], rule_version: str) -> TrialOutput:
        title = str(case.get("title") or "")
        department = str(case.get("department") or "")
        request = build_occupation_request(
            target_id=str(case["fixture_id"]),
            title=title,
            department=department,
            description_excerpt=str(case.get("description_excerpt") or ""),
            rule_version=rule_version,
        )
        result = self._provider_result("occupation", request)
        candidate_ids = tuple(candidate.candidate_id for candidate in result.candidates)
        title_function = _title_function(title)
        department_function = _department_function(department)
        conflict = bool(title_function and department_function and title_function != department_function)
        if rule_version == ALTERNATE_RULE_VERSION:
            function = title_function or department_function
        else:
            function = department_function or title_function
        occupation = result.candidates[0].normalized_value if result.candidates else {}
        predicted = {
            "occupation_candidate_id": candidate_ids[0] if candidate_ids and len(candidate_ids) == 1 else "",
            "occupation_candidate_ids": candidate_ids,
            "occupation": dict(occupation) if isinstance(occupation, Mapping) else occupation,
            "runr_function": function,
            "employment_type": _employment_type(title),
            "department_state": "known" if department.strip() else "unknown",
            "conflict": conflict,
            "title_function": title_function,
            "department_function": department_function,
        }
        state = "ambiguous" if len(candidate_ids) > 1 else str(result.state)
        return TrialOutput(
            str(case["fixture_id"]),
            str(case["split"]),
            str(case.get("connector") or "unknown"),
            "occupation_function",
            str(case["fixture_id"]),
            state,
            predicted,
            candidate_ids,
            next((candidate.provider_score for candidate in result.candidates if candidate.provider_score is not None), None),
            ambiguous=conflict or len(candidate_ids) > 1,
            input_fingerprint=input_fingerprint(request),
        )

    def _evaluate_language(self, case: Mapping[str, Any], rule_version: str) -> TrialOutput:
        del rule_version
        evidence = extract_language_evidence(
            structured=case.get("languages"),
            description=str(case.get("description_excerpt") or ""),
            posting_language=str(case.get("posting_language") or ""),
        )
        statuses_by_language: dict[str, set[str]] = defaultdict(set)
        for item in evidence:
            statuses_by_language[item.language].add(item.status)
        conflict = any(len(statuses) > 1 for statuses in statuses_by_language.values())
        predicted_evidence = [
            {
                "language": item.language,
                "status": item.status,
                "proficiency": item.proficiency,
                "evidence": item.evidence,
                "extraction_method": item.extraction_method,
            }
            for item in evidence
        ]
        predicted = {
            "language_state": language_state(evidence),
            "languages": predicted_evidence,
            "language": evidence[0].language if evidence else "",
            "proficiency": evidence[0].proficiency if evidence else "",
            "posting_language_ignored": bool(case.get("posting_language")),
        }
        return TrialOutput(
            str(case["fixture_id"]),
            str(case["split"]),
            str(case.get("connector") or "unknown"),
            "language_evidence",
            str(case["fixture_id"]),
            predicted["language_state"],
            predicted,
            confidence=None,
            ambiguous=conflict,
        )

    def _golden(self) -> dict[str, GoldenLabel]:
        return {fixture_id: GoldenLabel.from_mapping(payload) for fixture_id, payload in load_golden_labels().items()}

    def _build_report(self, cases: Sequence[Mapping[str, Any]], outputs: Sequence[TrialOutput], rule_version: str) -> dict[str, Any]:
        golden = self._golden()
        by_fixture = {case["fixture_id"]: case for case in cases}
        output_by_dimension = {(output.fixture_id, output.dimension): output for output in outputs}
        gaps: list[str] = []
        labelled_cases = [case for case in cases if case["fixture_id"] in golden]
        if any(case.get("split") == "blind_holdout" for case in cases):
            gaps.append("blind holdout is intentionally unlabeled in checked-in fixtures; holdout correctness metrics are unavailable")
        if not any(output.confidence is not None for output in outputs):
            gaps.append("fixture providers supplied no confidence scores; calibration metrics are unavailable")
        if len(labelled_cases) < 30:
            gaps.append(f"small synthetic labeled sample ({len(labelled_cases)} cases); results are directional, not confidence claims")
        gaps.append("no external datasets, production observations, or provider responses were evaluated")
        dimensions = self._dimension_reports(cases, outputs, golden)
        partitions = {}
        for split in PARTITIONS:
            split_cases = [case for case in cases if case.get("split") == split]
            split_outputs = [output for output in outputs if output.split == split]
            split_labelled = [case for case in split_cases if case["fixture_id"] in golden]
            partitions[split] = {
                "fixture_cases": len(split_cases),
                "output_count": len(split_outputs),
                "golden_label_cases": len(split_labelled),
                "metrics_available": bool(split_labelled),
            }
        adversarial = self._adversarial_report(output_by_dimension, by_fixture)
        if adversarial["missing_categories"]:
            gaps.append("adversarial coverage is incomplete: " + ", ".join(adversarial["missing_categories"]))
        recommendation = "reject" if self.config.allow_network or self.config.allow_ai or self.config.publication_active or self.config.allow_production_writes else ("continue shadow evaluation" if gaps else "eligible for human-review trial")
        return {
            "schema_version": "offline_deterministic_trial_report_v1",
            "trial": {
                "trial_id": self.config.trial_id,
                "fixture_version": self.config.fixture_version,
                "config_fingerprint": self.config.fingerprint,
                "provider_mode": self.config.provider_mode,
                "configured_rule_versions": list(self.config.rule_versions),
                "rule_version": rule_version,
                "network_called": False,
                "ai_called": False,
                "production_writes": False,
                "publication_changed": False,
            },
            "partitions": partitions,
            "golden_labels": {
                "label_cases": len(labelled_cases),
                "adjudicated_cases": sum(
                    label.adjudication.status == "adjudicated"
                    for label in golden.values()
                    if label.fixture_id in by_fixture
                ),
                "adjudication_metadata": [
                    {
                        "fixture_id": label.fixture_id,
                        "split": label.split,
                        "status": label.adjudication.status,
                        "annotator_count": label.adjudication.annotator_count,
                        "adjudicator": label.adjudication.adjudicator,
                        "reviewed_at": label.adjudication.reviewed_at,
                    }
                    for label in sorted(golden.values(), key=lambda item: item.fixture_id)
                    if label.fixture_id in by_fixture
                ],
            },
            "dimensions": dimensions,
            "per_language": self._breakdown(cases, outputs, golden, "language"),
            "per_connector": self._breakdown(cases, outputs, golden, "connector"),
            "adversarial": adversarial,
            "promotion": {
                "recommendation": recommendation,
                "allowed_values": sorted(ALLOWED_PROMOTION_RECOMMENDATIONS),
                "reasons": list(gaps) if gaps else ["all configured labeled checks and safety gates completed"],
            },
            "data_gaps": gaps,
            "outputs": [
                {
                    "fixture_id": output.fixture_id,
                    "split": output.split,
                    "connector": output.connector,
                    "dimension": output.dimension,
                    "target_id": output.target_id,
                    "result_state": output.result_state,
                    "predicted": _jsonable(output.predicted),
                    "candidate_ids": list(output.candidate_ids),
                    "confidence": output.confidence,
                    "ambiguous": output.ambiguous,
                    "warnings": list(output.warnings),
                }
                for output in outputs
            ],
        }

    def _dimension_reports(self, cases: Sequence[Mapping[str, Any]], outputs: Sequence[TrialOutput], golden: Mapping[str, GoldenLabel]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for dimension in DIMENSIONS:
            dimension_outputs = [output for output in outputs if output.dimension == dimension]
            fields = sorted(
                {
                    key
                    for case in cases
                    if case["fixture_id"] in golden
                    for key in golden[case["fixture_id"]].labels
                    if self._field_belongs_to_dimension(key, dimension)
                }
            )
            field_reports = {
                field_name: self._field_report(cases, dimension_outputs, golden, field_name)
                for field_name in fields
                if self._field_report(cases, dimension_outputs, golden, field_name)["evaluated"]
            }
            candidate_fields = [field_name for field_name in fields if field_name.endswith("candidate_id")]
            top_k = self._top_k_report(cases, dimension_outputs, golden, candidate_fields)
            calibration_pairs = []
            for output in dimension_outputs:
                label = golden.get(output.fixture_id)
                if not label or not output.confidence:
                    continue
                primary = next((field_name for field_name in candidate_fields if field_name in label.labels), "")
                if primary:
                    calibration_pairs.append((output.confidence, output.predicted.get(primary, "") == label.labels[primary]))
            primary_field = {
                "place_normalization": "place_candidate_id",
                "company_profile": "company_candidate_id",
                "occupation_function": "occupation_candidate_id",
                "language_evidence": "language_state",
            }[dimension]
            primary_report = field_reports.get(primary_field, _classification_metrics([]))
            result[dimension] = {
                "outputs": len(dimension_outputs),
                "fields": field_reports,
                "precision": primary_report["precision"],
                "recall": primary_report["recall"],
                "macro_f1": primary_report["macro_f1"],
                "top_1_accuracy": top_k["top_1_accuracy"],
                "top_3_accuracy": top_k["top_3_accuracy"],
                "false_positive_rate": primary_report["false_positive_rate"],
                "ambiguity_rate": _safe_div(sum(output.ambiguous for output in dimension_outputs), len(dimension_outputs)),
                "calibration": _calibration_metrics(calibration_pairs),
            }
        return result

    def _field_report(self, cases: Sequence[Mapping[str, Any]], outputs: Sequence[TrialOutput], golden: Mapping[str, GoldenLabel], field_name: str) -> dict[str, Any]:
        output_map = {output.fixture_id: output for output in outputs}
        pairs = []
        for case in cases:
            label = golden.get(case["fixture_id"])
            output = output_map.get(case["fixture_id"])
            if label and output and (field_name in label.labels or field_name.endswith("candidate_id")):
                # Candidate fields have an explicit negative class when a
                # golden label does not name a candidate. This makes false
                # positives measurable without inventing a candidate.
                pairs.append((label.labels.get(field_name, ""), output.predicted.get(field_name, "")))
        return {"field": field_name, **_classification_metrics(pairs)}

    @staticmethod
    def _field_belongs_to_dimension(field_name: str, dimension: str) -> bool:
        prefixes = {
            "place_normalization": ("place_", "location_count", "workplace_arrangement", "remote_scope", "remote_scope_state"),
            "company_profile": ("company_",),
            "occupation_function": ("occupation_", "employment_type", "department_state", "conflict", "runr_function"),
            "language_evidence": ("language", "proficiency"),
        }
        return field_name.startswith(prefixes[dimension]) or field_name in prefixes[dimension]

    def _top_k_report(self, cases: Sequence[Mapping[str, Any]], outputs: Sequence[TrialOutput], golden: Mapping[str, GoldenLabel], candidate_fields: Sequence[str]) -> dict[str, Any]:
        output_map = {output.fixture_id: output for output in outputs}
        top1 = top3 = total = 0
        for case in cases:
            label = golden.get(case["fixture_id"])
            output = output_map.get(case["fixture_id"])
            field_name = next((field for field in candidate_fields if label and field in label.labels), None)
            if not output or not field_name:
                continue
            total += 1
            expected = str(label.labels[field_name])
            top1 += bool(output.candidate_ids and output.candidate_ids[0] == expected)
            top3 += expected in output.candidate_ids[:3]
        return {"evaluated": total, "top_1_accuracy": _safe_div(top1, total), "top_3_accuracy": _safe_div(top3, total)}

    def _breakdown(self, cases: Sequence[Mapping[str, Any]], outputs: Sequence[TrialOutput], golden: Mapping[str, GoldenLabel], key: str) -> dict[str, Any]:
        groups: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
        for case in cases:
            groups[str(case.get(key) or "unspecified")].append(case)
        result = {}
        for group, group_cases in sorted(groups.items()):
            ids = {case["fixture_id"] for case in group_cases}
            result[group] = {
                "fixture_cases": len(group_cases),
                "dimensions": self._dimension_reports(group_cases, [output for output in outputs if output.fixture_id in ids], golden),
            }
        return result

    def _adversarial_report(self, outputs: Mapping[tuple[str, str], TrialOutput], cases: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
        checks: dict[str, Any] = {}
        missing: list[str] = []
        for category, fixture_ids in ADVERSARIAL_CATEGORIES.items():
            if not all(fixture_id in cases for fixture_id in fixture_ids):
                missing.append(category)
                continue
            category_checks = []
            for fixture_id in fixture_ids:
                place = outputs.get((fixture_id, "place_normalization"))
                company = outputs.get((fixture_id, "company_profile"))
                occupation = outputs.get((fixture_id, "occupation_function"))
                language = outputs.get((fixture_id, "language_evidence"))
                predicted = {
                    "place": _jsonable(place.predicted) if place else {},
                    "company": _jsonable(company.predicted) if company else {},
                    "occupation": _jsonable(occupation.predicted) if occupation else {},
                    "language": _jsonable(language.predicted) if language else {},
                }
                passed = True
                if category == "ambiguous Paris":
                    passed = predicted["place"].get("place_state") == "ambiguous"
                elif category == "Lowell employer plus Leeds":
                    passed = predicted["company"].get("company_candidate_id") in {"fixture:company:lowell", ""} and (fixture_id.startswith("blind_") or "fixture:leeds-gb" in predicted["place"].get("place_candidate_ids", []))
                elif category == "Lowell, Massachusetts":
                    passed = predicted["place"].get("place_candidate_id") == "fixture:lowell-ma"
                elif category == "multiple locations":
                    passed = predicted["place"].get("location_count") == 2
                elif category == "Remote Germany/EU/unrestricted":
                    passed = predicted["place"].get("location_count") == 0 and predicted["place"].get("workplace_arrangement") == "Remote"
                elif category == "department/title conflict":
                    passed = predicted["occupation"].get("conflict") is True
                elif category == "internship and working-student separation":
                    passed = predicted["occupation"].get("employment_type") in {"Internship", "Working student"}
                elif category == "posting language without language requirement":
                    passed = predicted["language"].get("language_state") == "not_established"
                category_checks.append({"fixture_id": fixture_id, "passed": passed, "predicted": predicted})
            checks[category] = {"passed": all(item["passed"] for item in category_checks), "cases": category_checks}
        return {"categories": checks, "missing_categories": missing, "all_passed": bool(checks) and all(item["passed"] for item in checks.values()) and not missing}


def compare_replays(baseline: TrialRun, candidate: TrialRun) -> ReplayComparison:
    baseline_outputs = {(output.fixture_id, output.dimension): output for output in baseline.outputs}
    candidate_outputs = {(output.fixture_id, output.dimension): output for output in candidate.outputs}
    keys = sorted(set(baseline_outputs) | set(candidate_outputs))
    changed: list[tuple[str, str]] = []
    by_dimension: Counter[str] = Counter()
    for key in keys:
        before = baseline_outputs.get(key)
        after = candidate_outputs.get(key)
        before_value = _jsonable(before.predicted) if before else None
        after_value = _jsonable(after.predicted) if after else None
        if before_value != after_value:
            changed.append(key)
            by_dimension[key[1]] += 1
    return ReplayComparison(
        baseline_run_id=baseline.run_id,
        candidate_run_id=candidate.run_id,
        baseline_rule_version=baseline.rule_version,
        candidate_rule_version=candidate.rule_version,
        compared_outputs=len(keys),
        changed_outputs=len(changed),
        changes_by_dimension=dict(by_dimension),
        changed_fixture_ids=tuple(sorted({fixture_id for fixture_id, _ in changed})),
    )


def render_markdown_report(run: TrialRun, replay: ReplayComparison | None = None) -> str:
    report = _jsonable(run.report)
    lines = [
        "# Offline deterministic enrichment trial",
        "",
        f"- Run: `{run.run_id}`",
        f"- Rule version: `{run.rule_version}`",
        f"- Fixture fingerprint: `{run.fixture_fingerprint}`",
        "- Network calls: **none**",
        "- External/AI provider calls: **none**; only checked-in fixture providers and the NullProvider boundary are allowed",
        "- Production writes/publication: **none**",
        "",
        "## Promotion recommendation",
        "",
        f"**{report['promotion']['recommendation']}**",
        "",
        "This is a report-only trial. No rule becomes production-active and no AI auto-accept path exists.",
        "",
        "## Partitions",
        "",
        "| Partition | Fixture cases | Outputs | Golden-label cases | Metrics |",
        "|---|---:|---:|---:|---|",
    ]
    for partition, values in report["partitions"].items():
        lines.append(f"| {partition} | {values['fixture_cases']} | {values['output_count']} | {values['golden_label_cases']} | {'available' if values['metrics_available'] else 'unavailable'} |")
    lines.extend([
        "",
        "## Golden labels",
        "",
        f"{report['golden_labels']['label_cases']} labeled cases are covered by adjudication metadata; {report['golden_labels']['adjudicated_cases']} are marked adjudicated. The blind holdout remains unlabeled.",
        "",
        "## Dimension metrics",
        "",
        "| Dimension | Precision | Recall | Macro-F1 | Top-1 | Top-3 | FPR | Ambiguity | Calibration |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---|",
    ])
    for dimension, values in report["dimensions"].items():
        calibration = "available" if values["calibration"]["available"] else "unavailable"
        lines.append("| {0} | {1} | {2} | {3} | {4} | {5} | {6} | {7} | {8} |".format(dimension, values["precision"], values["recall"], values["macro_f1"], values["top_1_accuracy"], values["top_3_accuracy"], values["false_positive_rate"], values["ambiguity_rate"], calibration))
    lines.extend(["", "## Adversarial evaluation", ""])
    for category, values in report["adversarial"]["categories"].items():
        lines.append(f"- **{category}:** {'pass' if values['passed'] else 'fail'} ({len(values['cases'])} cases)")
    lines.extend(["", "## Data gaps", ""])
    for gap in report["data_gaps"]:
        lines.append(f"- {gap}")
    if replay:
        lines.extend(["", "## Replay comparison", "", f"`{replay.baseline_rule_version}` → `{replay.candidate_rule_version}` changed **{replay.changed_outputs}** of **{replay.compared_outputs}** outputs."])
        if replay.changes_by_dimension:
            lines.append("Changes by dimension: " + ", ".join(f"{key}={value}" for key, value in replay.changes_by_dimension.items()) + ".")
    return "\n".join(lines) + "\n"


def report_json(run: TrialRun) -> str:
    return json.dumps(_jsonable(run.report), indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def run_offline_trial(*, config: TrialConfig | None = None, partitions: Iterable[str] | None = None) -> TrialRun:
    return OfflineTrialOrchestrator(config).run(partitions=partitions)


__all__ = [
    "ADVERSARIAL_CATEGORIES",
    "ALTERNATE_RULE_VERSION",
    "ALLOWED_PROMOTION_RECOMMENDATIONS",
    "DIMENSIONS",
    "DEFAULT_RULE_VERSION",
    "GoldenLabel",
    "AdjudicationMetadata",
    "OfflineTrialOrchestrator",
    "PARTITIONS",
    "ReplayComparison",
    "TrialConfig",
    "TrialOutput",
    "TrialRun",
    "compare_replays",
    "render_markdown_report",
    "report_json",
    "run_offline_trial",
]
