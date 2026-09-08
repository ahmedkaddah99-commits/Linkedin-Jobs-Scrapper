"""Adapters from the independent job producers to one observation contract.

The producer CLIs own collection, checkpointing, and source-specific state.  This
module only reads their durable results and turns each source row into an
immutable-at-the-boundary observation.  It deliberately does not read either
producer's CSV export; RC-009 can connect the transport protocol to the
existing acquisition store without coupling the collectors to that store.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Iterator, Mapping, Sequence
from contextlib import nullcontext
from dataclasses import dataclass, field
from typing import Any, Protocol

from backend.acquisition.unified_mapping import map_job_fields


OBSERVATION_SCHEMA_VERSION = "runr_source_observation_v1"
DEFAULT_BATCH_SIZE = 100
UNKNOWN = "unknown"
SOURCE_LINKEDIN = "linkedin"
SOURCE_EMPLOYER = "employer_site"
DEFAULT_SCOPE = {
    "country_code": "DE",
    "country_name": "Germany",
    "scope_version": "germany_jobs_v1",
}


def _text(value: Any, default: str = UNKNOWN) -> str:
    if value is None:
        return default
    text = str(value).strip()
    return text or default


def _first(record: Mapping[str, Any], *keys: str) -> str:
    for key in keys:
        value = record.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return UNKNOWN


def _json_ready(value: Any) -> Any:
    """Copy JSON-like producer data without dropping unknown source fields."""

    if isinstance(value, Mapping):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_json_ready(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _mapping_copy(value: Mapping[str, Any]) -> dict[str, Any]:
    copied = _json_ready(value)
    return copied if isinstance(copied, dict) else {}


def _list_value(value: Any) -> list[str]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_text(item) for item in value if item is not None and str(item).strip()]
    if value is not None and str(value).strip():
        return [item.strip() for item in str(value).split("|") if item.strip()]
    return [UNKNOWN]


def _scope(value: Mapping[str, Any] | None) -> dict[str, Any]:
    result = dict(DEFAULT_SCOPE)
    if isinstance(value, Mapping):
        result.update(_mapping_copy(value))
    return result


def _hash_payload(value: Any) -> str:
    encoded = json.dumps(_json_ready(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _observed_at(record: Mapping[str, Any], fallback: str) -> str:
    return _first(
        record,
        "observed_at",
        "detail_last_refreshed_at",
        "last_seen_at",
        "updated_at",
        "date_updated",
        "first_seen_at",
        "date_posted",
    ) if any(record.get(key) not in (None, "") for key in (
        "observed_at",
        "detail_last_refreshed_at",
        "last_seen_at",
        "updated_at",
        "date_updated",
        "first_seen_at",
        "date_posted",
    )) else _text(fallback)


def _application_type(record: Mapping[str, Any], source: str, apply_url: str) -> str:
    explicit = _first(record, "apply_type", "application_type", "apply_url_type")
    if explicit != UNKNOWN:
        return explicit
    destination = record.get("application_destination")
    if isinstance(destination, Mapping):
        classification = _first(destination, "destination_type", "classification")
        if classification != UNKNOWN:
            return classification
    if source == SOURCE_LINKEDIN:
        easy_apply = _first(record, "easy_apply_status")
        if easy_apply.casefold() in {"true", "yes", "1"}:
            return "linkedin_easy_apply"
        if apply_url != UNKNOWN:
            return "linkedin_external"
        return UNKNOWN
    if _first(record, "source_provider") not in {UNKNOWN, "generic_employer_site"}:
        return "employer_ats"
    if apply_url != UNKNOWN:
        return "employer_site"
    return UNKNOWN


def _mapping_input(
    record: Mapping[str, Any],
    *,
    source: str,
    source_observation_id: str,
    observed_at: str,
    apply_url: str,
    apply_type: str,
) -> dict[str, Any]:
    """Provide aliases expected by the shared mapper while retaining the row."""

    value = _mapping_copy(record)
    value.setdefault("title", _first(record, "job_title", "title"))
    value.setdefault("description", _first(record, "description_text", "description", "description_html"))
    value.setdefault("location", _first(record, "location", "location_raw"))
    value.setdefault("source_posted_at", _first(record, "posted_at_estimated", "date_posted", "posted_text"))
    value.setdefault("source_updated_at", _first(record, "date_updated", "last_seen_at"))
    value.setdefault("source_company_name", _first(record, "source_company_name", "observed_company_name"))
    value.setdefault("source_company_url", _first(record, "source_company_url", "observed_company_url"))
    value.setdefault(
        "company",
        {
            "name": value["source_company_name"],
            "website": value["source_company_url"],
        },
    )
    value.setdefault("source_raw_payload", _mapping_copy(record))
    value.setdefault(
        "application_destination",
        {
            "classification": {
                "linkedin_easy_apply": "linkedin_easy_apply",
                "linkedin_external": "employer_application",
                "employer_ats": "ats_application",
                "employer_site": "employer_application",
            }.get(apply_type, "unknown"),
            "contract_type": apply_type,
            "resolved_url": None if apply_url == UNKNOWN else apply_url,
            "source": _first(record, "apply_url_source", "source_type"),
        },
    )
    value.setdefault(
        "source_timestamps",
        {
            "fields": {
                "source_posted_at": {"value": value.get("source_posted_at"), "source_field": "source_posted_at"},
                "source_updated_at": {"value": value.get("source_updated_at"), "source_field": "source_updated_at"},
            }
        },
    )
    value["source"] = source
    value["source_observation_id"] = source_observation_id
    value["observed_at"] = observed_at
    return value


def _metadata(record: Mapping[str, Any], source: str) -> dict[str, Any]:
    if source == SOURCE_LINKEDIN:
        return {
            "linkedin_company": {
                "company_id": _first(record, "linkedin_company_id"),
                "source_company_ids": _list_value(record.get("source_company_ids")),
                "source_company_names": _list_value(record.get("source_company_names")),
                "source_company_urls": _list_value(record.get("source_company_urls")),
                "observed_name": _first(record, "observed_company_name", "source_company_name"),
                "observed_url": _first(record, "observed_company_url", "source_company_url"),
            },
            "ownership": {
                "company_match_status": _first(record, "company_match_status"),
                "ownership_status": _first(record, "ownership_status"),
                "ownership_alias_status": _first(record, "ownership_alias_status"),
            },
            "application": {
                "easy_apply_status": _first(record, "easy_apply_status"),
                "applicant_count": _first(record, "applicant_count"),
            },
            "collection": {
                "run_id": _first(record, "run_id"),
                "company_scan_id": _first(record, "company_scan_id"),
                "source_endpoint": _first(record, "source_endpoint"),
                "transport": _first(record, "transport"),
            },
        }
    return {
        "employer_source": {
            "source_provider": _first(record, "source_provider"),
            "ats_tenant": _first(record, "ats_tenant"),
            "career_target_url": _first(record, "career_target_url"),
            "source_site_url": _first(record, "source_site_url"),
            "discovery_method": _first(record, "discovery_method"),
            "extraction_method": _first(record, "extraction_method"),
            "extraction_endpoint": _first(record, "extraction_endpoint"),
            "transport": _first(record, "transport"),
            "collection_status": _first(record, "collection_status"),
        },
        "geography": {
            "classification": _first(record, "germany_classification"),
            "evidence": _first(record, "germany_evidence"),
        },
    }


@dataclass(frozen=True)
class SourceObservation:
    """One source-specific posting observation at the producer boundary."""

    observation_id: str
    idempotency_key: str
    canonical_company_id: str
    canonical_employer: Mapping[str, Any]
    source: str
    source_job_id: str
    source_url: str
    apply_url: str
    apply_type: str
    scope: Mapping[str, Any]
    cycle_id: str
    scan_id: str
    observed_at: str
    content_hash: str
    schema_version: str
    source_record: Mapping[str, Any]
    source_metadata: Mapping[str, Any]
    normalized_mapping: Mapping[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "observation_id": self.observation_id,
            "idempotency_key": self.idempotency_key,
            "canonical_company_id": self.canonical_company_id,
            "canonical_employer": _mapping_copy(self.canonical_employer),
            "source": self.source,
            "source_job_id": self.source_job_id,
            "source_url": self.source_url,
            "apply_url": self.apply_url,
            "apply_type": self.apply_type,
            "scope": _mapping_copy(self.scope),
            "cycle_id": self.cycle_id,
            "scan_id": self.scan_id,
            "observed_at": self.observed_at,
            "content_hash": self.content_hash,
            "schema_version": self.schema_version,
            "source_record": _mapping_copy(self.source_record),
            "source_metadata": _mapping_copy(self.source_metadata),
            "normalized_mapping": _mapping_copy(self.normalized_mapping),
        }


def _adapt(
    record: Mapping[str, Any],
    *,
    source: str,
    cycle_id: str,
    scan_id: str,
    scope: Mapping[str, Any] | None,
    observed_at: str,
) -> SourceObservation:
    raw = _mapping_copy(record)
    canonical_company_id = _first(raw, "canonical_company_id", "company_id")
    source_job_url = _first(raw, "source_job_url", "linkedin_job_url", "job_url", "url")
    source_job_id = _first(raw, "source_job_id", "linkedin_job_id", "external_job_id", "job_id", "id")
    if source_job_id == UNKNOWN and source_job_url != UNKNOWN:
        source_job_id = source_job_url
    source_url = source_job_url
    apply_url = _first(raw, "apply_url_canonical", "apply_url_raw", "application_url", "apply_url", "apply_link")
    apply_type = _application_type(raw, source, apply_url)
    timestamp = _observed_at(raw, observed_at)
    cycle = _text(cycle_id)
    scan = _text(scan_id)
    content_hash = _first(raw, "content_hash", "raw_content_hash")
    if content_hash == UNKNOWN:
        content_hash = _hash_payload(raw)
    identity = {
        "schema_version": OBSERVATION_SCHEMA_VERSION,
        "source": source,
        "canonical_company_id": canonical_company_id,
        "source_job_id": source_job_id,
        "source_url": source_url,
        "cycle_id": cycle,
        "scan_id": scan,
        "content_hash": content_hash,
    }
    idempotency_key = "obs_" + _hash_payload(identity)
    observation_id = idempotency_key
    canonical_employer = {
        "canonical_company_id": canonical_company_id,
        "source_company_name": _first(raw, "source_company_name", "observed_company_name"),
        "source_company_url": _first(raw, "source_company_url", "observed_company_url"),
        "source_company_ids": _list_value(raw.get("source_company_ids") or raw.get("linkedin_company_id")),
        "source_company_names": _list_value(raw.get("source_company_names") or raw.get("source_company_name")),
        "source_company_urls": _list_value(raw.get("source_company_urls") or raw.get("source_company_url")),
    }
    mapping_input = _mapping_input(
        raw,
        source=source,
        source_observation_id=observation_id,
        observed_at=timestamp,
        apply_url=apply_url,
        apply_type=apply_type,
    )
    normalized_mapping = map_job_fields(
        mapping_input,
        observed_at=timestamp,
        source_observation_id=observation_id,
        source=source,
    )
    return SourceObservation(
        observation_id=observation_id,
        idempotency_key=idempotency_key,
        canonical_company_id=canonical_company_id,
        canonical_employer=canonical_employer,
        source=source,
        source_job_id=source_job_id,
        source_url=source_url,
        apply_url=apply_url,
        apply_type=apply_type,
        scope=_scope(scope),
        cycle_id=cycle,
        scan_id=scan,
        observed_at=timestamp,
        content_hash=content_hash,
        schema_version=OBSERVATION_SCHEMA_VERSION,
        source_record=raw,
        source_metadata=_metadata(raw, source),
        normalized_mapping=normalized_mapping,
    )


def adapt_employer_job(
    record: Mapping[str, Any],
    *,
    cycle_id: str,
    scan_id: str = "",
    scope: Mapping[str, Any] | None = None,
    observed_at: str = "",
) -> SourceObservation:
    """Adapt one persisted row from ``EmployerState``."""

    return _adapt(
        record,
        source=SOURCE_EMPLOYER,
        cycle_id=cycle_id,
        scan_id=scan_id,
        scope=scope,
        observed_at=observed_at,
    )


def adapt_linkedin_job(
    record: Mapping[str, Any],
    *,
    cycle_id: str,
    scan_id: str = "",
    scope: Mapping[str, Any] | None = None,
    observed_at: str = "",
) -> SourceObservation:
    """Adapt one persisted row from ``StateStore.job_company_observations``."""

    return _adapt(
        record,
        source=SOURCE_LINKEDIN,
        cycle_id=cycle_id,
        scan_id=scan_id,
        scope=scope,
        observed_at=observed_at,
    )


def iter_employer_observations(
    state: Any,
    *,
    cycle_id: str,
    scan_id: str = "",
    scope: Mapping[str, Any] | None = None,
    observed_at: str = "",
) -> Iterator[SourceObservation]:
    """Stream jobs from an existing employer checkpoint database."""

    for row in state.iter_jobs():
        yield adapt_employer_job(row, cycle_id=cycle_id, scan_id=scan_id, scope=scope, observed_at=observed_at)


def _iter_linkedin_rows(state: Any, run_id: str) -> Iterator[dict[str, Any]]:
    row_iterator = getattr(state, "iter_catalog_rows", None)
    if callable(row_iterator):
        yield from row_iterator(run_id=run_id)
        return
    connection = getattr(state, "connection", None)
    if connection is None:
        raise TypeError("LinkedIn state must expose iter_catalog_rows() or a SQLite connection")
    state_lock = getattr(state, "_lock", None)
    lock = state_lock if state_lock is not None else nullcontext()
    query = "SELECT linkedin_company_id, linkedin_job_id, run_id, company_scan_id, row_json FROM job_company_observations"
    parameters: tuple[Any, ...] = ()
    if run_id:
        query += " WHERE run_id=?"
        parameters = (str(run_id),)
    query += " ORDER BY linkedin_company_id, linkedin_job_id"
    with lock:
        cursor = connection.execute(query, parameters)
        for row in cursor:
            payload = json.loads(row[4])
            if not isinstance(payload, Mapping):
                continue
            result = _mapping_copy(payload)
            result.setdefault("linkedin_company_id", row[0])
            result.setdefault("linkedin_job_id", row[1])
            result.setdefault("run_id", row[2])
            result.setdefault("company_scan_id", row[3])
            yield result


def iter_linkedin_observations(
    state: Any,
    *,
    cycle_id: str,
    run_id: str = "",
    scan_id: str = "",
    scope: Mapping[str, Any] | None = None,
    observed_at: str = "",
) -> Iterator[SourceObservation]:
    """Stream LinkedIn rows from durable state, never from the CSV export."""

    for row in _iter_linkedin_rows(state, run_id):
        row_scan_id = _first(row, "company_scan_id")
        yield adapt_linkedin_job(
            row,
            cycle_id=cycle_id,
            scan_id=row_scan_id if row_scan_id != UNKNOWN else scan_id,
            scope=scope,
            observed_at=observed_at,
        )


@dataclass(frozen=True)
class ObservationBatch:
    """Bounded delivery unit with a deterministic identity."""

    batch_id: str
    schema_version: str
    observations: tuple[SourceObservation, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "batch_id": self.batch_id,
            "schema_version": self.schema_version,
            "observations": [observation.to_dict() for observation in self.observations],
        }


def _batch(observations: tuple[SourceObservation, ...]) -> ObservationBatch:
    identity = {
        "schema_version": OBSERVATION_SCHEMA_VERSION,
        "idempotency_keys": [item.idempotency_key for item in observations],
    }
    return ObservationBatch(
        batch_id="batch_" + _hash_payload(identity),
        schema_version=OBSERVATION_SCHEMA_VERSION,
        observations=observations,
    )


def iter_observation_batches(
    observations: Iterable[SourceObservation], *, max_batch_size: int = DEFAULT_BATCH_SIZE
) -> Iterator[ObservationBatch]:
    """Group a producer stream without materializing the complete catalog."""

    if int(max_batch_size) < 1:
        raise ValueError("max_batch_size must be positive")
    batch: list[SourceObservation] = []
    for observation in observations:
        batch.append(observation)
        if len(batch) == int(max_batch_size):
            yield _batch(tuple(batch))
            batch.clear()
    if batch:
        yield _batch(tuple(batch))


@dataclass(frozen=True)
class ObservationDeliveryReceipt:
    receipt_id: str
    batch_id: str
    accepted_count: int
    duplicate_count: int
    store_result: Mapping[str, Any] = field(default_factory=dict)


class ObservationTransport(Protocol):
    def send(self, batch: ObservationBatch) -> ObservationDeliveryReceipt: ...


class IdempotentMemoryTransport:
    """Deterministic fake transport used by offline producer-to-contract tests."""

    def __init__(self) -> None:
        self._observations: dict[str, str] = {}

    @property
    def observations(self) -> tuple[dict[str, Any], ...]:
        return tuple(json.loads(payload) for payload in self._observations.values())

    def send(self, batch: ObservationBatch) -> ObservationDeliveryReceipt:
        accepted = 0
        duplicates = 0
        for observation in batch.observations:
            payload = json.dumps(observation.to_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            existing = self._observations.get(observation.idempotency_key)
            if existing is None:
                self._observations[observation.idempotency_key] = payload
                accepted += 1
            elif existing == payload:
                duplicates += 1
            else:
                raise ValueError(f"idempotency key conflict: {observation.idempotency_key}")
        receipt_id = "receipt_" + hashlib.sha256(batch.batch_id.encode("utf-8")).hexdigest()
        return ObservationDeliveryReceipt(receipt_id, batch.batch_id, accepted, duplicates)


def empty_observation_batch() -> ObservationBatch:
    """Build the explicit zero-job delivery unit for a validated final scan."""

    return _batch(())


def _observation_to_ingest_job(observation: SourceObservation) -> dict[str, Any]:
    """Project a contract record into the existing ingestion input shape."""

    source_record = _mapping_copy(observation.source_record)
    job = dict(source_record)
    source_url = "" if observation.source_url == UNKNOWN else observation.source_url
    apply_url = "" if observation.apply_url == UNKNOWN else observation.apply_url
    provider = ""
    employer_metadata = observation.source_metadata.get("employer_source")
    if isinstance(employer_metadata, Mapping):
        provider = str(employer_metadata.get("source_provider") or "")
    job.update(
        {
            "canonical_company_id": observation.canonical_company_id,
            "source": observation.source,
            "source_observation_id": observation.observation_id,
            "observation_id": observation.observation_id,
            "job_id": observation.source_job_id if observation.source_job_id != UNKNOWN else "",
            "external_job_id": observation.source_job_id if observation.source_job_id != UNKNOWN else "",
            "source_job_id": observation.source_job_id,
            "title": _first(source_record, "title", "job_title"),
            "job_detail_url": source_url,
            "url": source_url,
            "source_url": source_url,
            "application_url": apply_url,
            "apply_url": apply_url,
            "apply_link": apply_url or _first(source_record, "apply_url_raw", "apply_link", "application_url"),
            "source_ats": provider or observation.source,
            "source_display_name": _first(source_record, "source_company_name", "observed_company_name"),
            "source_token": observation.canonical_company_id,
            "employer_name": _first(source_record, "source_company_name", "observed_company_name"),
            "observed_at": observation.observed_at,
            "observation_scope": _mapping_copy(observation.scope),
            "observation_cycle_id": observation.cycle_id,
            "observation_scan_id": observation.scan_id,
            "observation_content_hash": observation.content_hash,
        }
    )
    existing_raw_payload = job.get("source_raw_payload")
    if isinstance(existing_raw_payload, Mapping):
        raw_payload = _mapping_copy(existing_raw_payload)
    else:
        raw_payload = {"producer_record": source_record}
    raw_payload["observation_contract"] = observation.to_dict()
    job["source_raw_payload"] = raw_payload
    return job


class SqliteAcquisitionTransport:
    """Bind source batches to ``SqliteAcquisitionStore.ingest_snapshot``.

    ``send`` is intentionally non-final.  A caller must use ``send_final`` with
    an explicit complete source-ID inventory before absence/lifecycle decisions
    can be evaluated.  This keeps a lost or interrupted adapter batch from
    looking like a valid empty source snapshot.
    """

    def __init__(
        self,
        store: Any,
        *,
        cycle_id: str,
        task_id: str,
        target_id: str,
        observed_at: str = "",
    ) -> None:
        self.store = store
        self.cycle_id = _text(cycle_id)
        self.task_id = _text(task_id)
        self.target_id = _text(target_id)
        self.observed_at = _text(observed_at, default="") if observed_at else ""

    def _validate_batch_scope(self, batch: ObservationBatch) -> None:
        if batch.schema_version != OBSERVATION_SCHEMA_VERSION:
            raise ValueError(f"unsupported observation batch schema: {batch.schema_version}")
        if not batch.observations:
            return
        sources = {observation.source for observation in batch.observations}
        if len(sources) > 1:
            raise ValueError("one acquisition transport may deliver only one source")
        company_ids = {
            observation.canonical_company_id
            for observation in batch.observations
            if observation.canonical_company_id != UNKNOWN
        }
        if len(company_ids) > 1:
            raise ValueError("one acquisition transport may deliver only one canonical employer")

    def _receipt_id(self, batch: ObservationBatch, *, final: bool) -> str:
        return "receipt_" + _hash_payload(
            {
                "transport": "sqlite_acquisition_v1",
                "target_id": self.target_id,
                "cycle_id": self.cycle_id,
                "task_id": self.task_id,
                "batch_id": batch.batch_id,
                "final": final,
            }
        )

    def _send(
        self,
        batch: ObservationBatch,
        *,
        complete_snapshot: bool,
        valid_snapshot: bool,
        closure_safe: bool,
        snapshot_external_ids: Iterable[str] | None,
    ) -> ObservationDeliveryReceipt:
        self._validate_batch_scope(batch)
        if complete_snapshot and snapshot_external_ids is None:
            raise ValueError("a final snapshot requires an explicit source external-ID inventory")
        jobs = [_observation_to_ingest_job(observation) for observation in batch.observations]
        result = dict(
            self.store.ingest_snapshot(
                cycle_id=self.cycle_id,
                task_id=self.task_id,
                target_id=self.target_id,
                jobs=jobs,
                complete_snapshot=complete_snapshot,
                valid_snapshot=valid_snapshot,
                closure_safe=closure_safe,
                observed_at=self.observed_at or next(
                    (observation.observed_at for observation in batch.observations if observation.observed_at != UNKNOWN),
                    "",
                ),
                snapshot_external_ids=snapshot_external_ids,
            )
        )
        return ObservationDeliveryReceipt(
            receipt_id=self._receipt_id(batch, final=complete_snapshot),
            batch_id=batch.batch_id,
            accepted_count=int(result.get("observed") or 0),
            duplicate_count=int(result.get("duplicates") or 0),
            store_result=result,
        )

    def send(self, batch: ObservationBatch) -> ObservationDeliveryReceipt:
        """Deliver a resumable intermediate batch; closure is always disabled."""

        if not batch.observations:
            raise ValueError("an intermediate acquisition batch cannot be empty")
        return self._send(
            batch,
            complete_snapshot=False,
            valid_snapshot=True,
            closure_safe=False,
            snapshot_external_ids=None,
        )

    def send_final(
        self,
        batch: ObservationBatch,
        *,
        snapshot_external_ids: Iterable[str] | None,
        valid_snapshot: bool = True,
        closure_safe: bool | None = None,
    ) -> ObservationDeliveryReceipt:
        """Deliver the only batch allowed to authorize source absence handling."""

        if snapshot_external_ids is None:
            raise ValueError("snapshot_external_ids is required for a final batch")
        external_ids = tuple(dict.fromkeys(str(item).strip() for item in snapshot_external_ids if str(item).strip()))
        batch_ids = {
            observation.source_job_id
            for observation in batch.observations
            if observation.source_job_id != UNKNOWN
        }
        if UNKNOWN in {observation.source_job_id for observation in batch.observations}:
            raise ValueError("a final batch cannot contain an observation without a source job ID")
        if not batch_ids.issubset(set(external_ids)):
            raise ValueError("the final source inventory must include every delivered observation")
        final_closure_safe = bool(valid_snapshot) if closure_safe is None else bool(closure_safe)
        if not valid_snapshot and final_closure_safe:
            raise ValueError("an invalid snapshot cannot be closure-safe")
        return self._send(
            batch,
            complete_snapshot=True,
            valid_snapshot=bool(valid_snapshot),
            closure_safe=final_closure_safe,
            snapshot_external_ids=external_ids,
        )


def deliver_observation_batches(
    batches: Iterable[ObservationBatch], transport: ObservationTransport
) -> tuple[ObservationDeliveryReceipt, ...]:
    """Send bounded batches through a transport while leaving retry policy to it."""

    return tuple(transport.send(batch) for batch in batches)


__all__ = [
    "DEFAULT_BATCH_SIZE",
    "DEFAULT_SCOPE",
    "SOURCE_EMPLOYER",
    "IdempotentMemoryTransport",
    "SOURCE_LINKEDIN",
    "OBSERVATION_SCHEMA_VERSION",
    "ObservationBatch",
    "ObservationDeliveryReceipt",
    "ObservationTransport",
    "SourceObservation",
    "UNKNOWN",
    "adapt_employer_job",
    "adapt_linkedin_job",
    "deliver_observation_batches",
    "empty_observation_batch",
    "iter_employer_observations",
    "iter_linkedin_observations",
    "iter_observation_batches",
    "SqliteAcquisitionTransport",
]
