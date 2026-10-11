from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from backend.acquisition.audit import (
    ACQUISITION_AUDIT_DOMAIN,
    AcquisitionAuditEvent,
    AcquisitionAuditQuery,
    acquisition_audit_event_hash,
    redact_acquisition_audit_payload,
)
from backend.domain.models import utc_now_iso
from backend.repositories.sqlite_core import _SqliteStore


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _decode(value: Any) -> Any:
    if value in (None, ""):
        return {}
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return {}


class SqliteAcquisitionAuditStore(_SqliteStore):
    """Append-only acquisition audit event store with filtered read models."""

    def append_event(
        self,
        *,
        event: str,
        actor: str = "",
        entity_type: str = "",
        entity_id: str = "",
        operation_id: str = "",
        occurred_at: str = "",
        payload: Mapping[str, Any] | None = None,
        event_id: str = "",
        domain: str = ACQUISITION_AUDIT_DOMAIN,
    ) -> dict[str, Any]:
        record = AcquisitionAuditEvent.create(
            event=event,
            actor=actor,
            entity_type=entity_type,
            entity_id=entity_id,
            operation_id=operation_id,
            occurred_at=occurred_at,
            payload=payload,
            event_id=event_id,
            domain=domain,
        )
        if not record.event:
            raise ValueError("Acquisition audit event is required.")
        if record.domain != ACQUISITION_AUDIT_DOMAIN:
            raise ValueError(f"Unsupported acquisition audit domain: {record.domain}")

        def write(connection) -> dict[str, Any]:
            previous = connection.execute(
                "SELECT event_hash FROM acquisition_audit_events ORDER BY sequence_id DESC LIMIT 1"
            ).fetchone()
            previous_hash = str(previous["event_hash"] or "") if previous is not None else ""
            event_hash = acquisition_audit_event_hash(
                previous_event_hash=previous_hash,
                event_id=record.event_id,
                domain=record.domain,
                event=record.event,
                actor=record.actor,
                entity_type=record.entity_type,
                entity_id=record.entity_id,
                operation_id=record.operation_id,
                occurred_at=record.occurred_at,
                payload=dict(record.payload),
            )
            connection.execute(
                """
                INSERT INTO acquisition_audit_events (
                    event_id, domain, event, actor_id, entity_type, entity_id,
                    operation_id, occurred_at, payload_json, previous_event_hash,
                    event_hash, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.event_id,
                    record.domain,
                    record.event,
                    record.actor,
                    record.entity_type,
                    record.entity_id,
                    record.operation_id,
                    record.occurred_at,
                    _json(redact_acquisition_audit_payload(dict(record.payload))),
                    previous_hash,
                    event_hash,
                    utc_now_iso(),
                ),
            )
            return {
                **record.to_dict(),
                "previous_event_hash": previous_hash,
                "event_hash": event_hash,
            }

        return self._run_transaction(write)

    append = append_event
    record_event = append_event

    def query_events(
        self,
        *,
        domain: str = ACQUISITION_AUDIT_DOMAIN,
        event: str = "",
        actor: str = "",
        entity_type: str = "",
        entity_id: str = "",
        operation_id: str = "",
        occurred_from: str = "",
        occurred_to: str = "",
        limit: int = 100,
        offset: int = 0,
    ) -> dict[str, Any]:
        query = AcquisitionAuditQuery.from_mapping(
            {
                "domain": domain,
                "event": event,
                "actor": actor,
                "entity_type": entity_type,
                "entity_id": entity_id,
                "operation_id": operation_id,
                "occurred_from": occurred_from,
                "occurred_to": occurred_to,
                "limit": limit,
                "offset": offset,
            }
        )
        predicates = ["domain = ?"]
        parameters: list[Any] = [query.domain]
        for column, value in (
            ("event", query.event),
            ("actor_id", query.actor),
            ("entity_type", query.entity_type),
            ("entity_id", query.entity_id),
            ("operation_id", query.operation_id),
        ):
            if value:
                predicates.append(f"{column} = ?")
                parameters.append(value)
        if query.occurred_from:
            predicates.append("occurred_at >= ?")
            parameters.append(query.occurred_from)
        if query.occurred_to:
            predicates.append("occurred_at < ?")
            parameters.append(query.occurred_to)
        where = " AND ".join(predicates)
        with self._connect() as connection:
            total_row = connection.execute(
                f"SELECT COUNT(*) AS total FROM acquisition_audit_events WHERE {where}",
                tuple(parameters),
            ).fetchone()
            rows = connection.execute(
                f"""
                SELECT event_id, domain, event, actor_id, entity_type, entity_id,
                       operation_id, occurred_at, payload_json, previous_event_hash,
                       event_hash
                FROM acquisition_audit_events
                WHERE {where}
                ORDER BY occurred_at DESC, sequence_id DESC
                LIMIT ? OFFSET ?
                """,
                (*parameters, query.limit, query.offset),
            ).fetchall()
        total = int(total_row["total"] or 0) if total_row is not None else 0
        events = [self._event_payload(row) for row in rows]
        return {
            "events": events,
            "pagination": {
                "limit": query.limit,
                "offset": query.offset,
                "returned": len(events),
                "total": total,
                "has_more": query.offset + len(events) < total,
            },
            "filters": {
                "domain": query.domain,
                "event": query.event,
                "actor": query.actor,
                "entity_type": query.entity_type,
                "entity_id": query.entity_id,
                "operation_id": query.operation_id,
                "occurred_from": query.occurred_from,
                "occurred_to": query.occurred_to,
            },
        }

    query = query_events
    list_events = query_events

    def entity_timeline(
        self,
        entity_type: str,
        entity_id: str,
        *,
        limit: int = 100,
        offset: int = 0,
        occurred_from: str = "",
        occurred_to: str = "",
    ) -> dict[str, Any]:
        return self.query_events(
            entity_type=entity_type,
            entity_id=entity_id,
            limit=limit,
            offset=offset,
            occurred_from=occurred_from,
            occurred_to=occurred_to,
        )

    get_entity_timeline = entity_timeline
    list_entity_timeline = entity_timeline

    @staticmethod
    def _event_payload(row: Mapping[str, Any]) -> dict[str, Any]:
        row = dict(row)
        payload = _decode(row.get("payload_json"))
        if not isinstance(payload, Mapping):
            payload = {}
        actor = str(row.get("actor_id") or "")
        return {
            "event_id": str(row.get("event_id") or ""),
            "domain": str(row.get("domain") or ACQUISITION_AUDIT_DOMAIN),
            "event": str(row.get("event") or ""),
            "actor": actor,
            "actor_id": actor,
            "entity_type": str(row.get("entity_type") or ""),
            "entity_id": str(row.get("entity_id") or ""),
            "operation_id": str(row.get("operation_id") or ""),
            "occurred_at": str(row.get("occurred_at") or ""),
            "payload": redact_acquisition_audit_payload(dict(payload)),
            "previous_event_hash": str(row.get("previous_event_hash") or ""),
            "event_hash": str(row.get("event_hash") or ""),
        }


__all__ = ["SqliteAcquisitionAuditStore"]
