"""Offline-safe policies for company enrichment and identity resolution.

This module contains the decisions that are safe to exercise without provider
access.  It deliberately does not perform HTTP work.  The resolver runner uses
``PersistentResolverSafety`` as a durable gate around provider calls, while the
queue and evidence helpers are also useful to manifest/import callers.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping
from urllib.parse import urlsplit


MISSING_CANONICAL_ID = "missing_canonical_id"
MISSING_WEBSITE = "missing_website"
MISSING_LINKEDIN_URL = "missing_linkedin_url"
UNRESOLVED_NUMERIC_ID = "unresolved_numeric_id"
OWNERSHIP_CONFLICT = "ownership_conflict"

ACCESS_FAILURES = frozenset({"blocked", "challenge", "rate_limited", "network_error", "malformed"})

# Evidence ranks are intentionally explicit.  User-confirmed evidence is the
# only source allowed to outrank a verified value; a discovered value cannot
# silently replace either one.
EVIDENCE_RANKS = {
    "provisional": 10,
    "discovered": 20,
    "verified": 30,
    "user_confirmed": 40,
}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _is_http_url(value: Any, *, host_suffix: str = "") -> bool:
    parsed = urlsplit(_text(value))
    host = (parsed.hostname or "").casefold().rstrip(".")
    if parsed.scheme.casefold() not in {"http", "https"} or not host or not parsed.path:
        return False
    return not host_suffix or host == host_suffix or host.endswith("." + host_suffix)


def _numeric_id(value: Any) -> bool:
    return bool(re.fullmatch(r"\d+", _text(value)))


def enrichment_queues(row: Mapping[str, Any]) -> tuple[str, ...]:
    """Return independent queues required by one input row.

    A row can be in several queues.  For example, a row without a canonical ID
    and without a LinkedIn numeric ID belongs to both identity queues; they are
    not collapsed into one apparent failure reason.
    """

    queues: list[str] = []
    canonical = _text(row.get("canonical_CompanyID"))
    website = _text(row.get("website_url"))
    linkedin_url = _text(row.get("linkedin_company_url"))
    linkedin_id = _text(row.get("linkedin_company_id"))
    if not canonical or canonical in {"//", "null", "None"}:
        queues.append(MISSING_CANONICAL_ID)
    if not _is_http_url(website):
        queues.append(MISSING_WEBSITE)
    if not _is_http_url(linkedin_url, host_suffix="linkedin.com"):
        queues.append(MISSING_LINKEDIN_URL)
    elif not _numeric_id(linkedin_id):
        queues.append(UNRESOLVED_NUMERIC_ID)

    raw_conflict = row.get("ownership_conflict")
    candidate_ids = row.get("canonical_company_ids")
    if raw_conflict is True or (
        isinstance(candidate_ids, (list, tuple, set))
        and len({_text(value) for value in candidate_ids if _text(value)}) > 1
    ):
        queues.append(OWNERSHIP_CONFLICT)
    return tuple(queues)


@dataclass(frozen=True)
class EvidenceCandidate:
    value: str
    source: str
    strength: str = "discovered"
    user_confirmed: bool = False

    @property
    def rank(self) -> int:
        return EVIDENCE_RANKS.get("user_confirmed" if self.user_confirmed else self.strength, 0)


@dataclass(frozen=True)
class EvidenceMerge:
    value: str
    selected: EvidenceCandidate | None
    status: str
    conflict: bool
    reason: str


def merge_evidence(existing: EvidenceCandidate | None, incoming: EvidenceCandidate) -> EvidenceMerge:
    """Merge one value without silently downgrading stronger evidence."""

    if existing is None or not existing.value:
        return EvidenceMerge(incoming.value, incoming, "accepted", False, "no_existing_value")
    if existing.value == incoming.value:
        selected = existing if existing.rank >= incoming.rank else incoming
        return EvidenceMerge(selected.value, selected, "unchanged", False, "same_value")
    if existing.user_confirmed or incoming.user_confirmed:
        if existing.user_confirmed and incoming.user_confirmed:
            return EvidenceMerge(existing.value, existing, "review", True, "two_user_confirmed_values")
        if existing.user_confirmed:
            return EvidenceMerge(existing.value, existing, "protected", True, "incoming_weaker_than_user_confirmed")
        return EvidenceMerge(incoming.value, incoming, "accepted", True, "user_confirmed_replaces_weaker_value")
    if incoming.rank > existing.rank:
        return EvidenceMerge(incoming.value, incoming, "review", True, "stronger_incoming_value_requires_review")
    return EvidenceMerge(existing.value, existing, "review", True, "existing_value_protected_until_review")


def evidence_fingerprint(values: Mapping[str, Any]) -> str:
    """Return a stable fingerprint for source evidence, independent of row order."""

    canonical = {str(key): values[key] for key in sorted(values)}
    encoded = json.dumps(canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _now_epoch() -> float:
    return datetime.now(timezone.utc).timestamp()


def _iso(epoch: float | None) -> str | None:
    if epoch is None:
        return None
    return datetime.fromtimestamp(float(epoch), tz=timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


@dataclass(frozen=True)
class SafetyDecision:
    allowed: bool
    reason: str = "allowed"
    reservation_id: str = ""
    provider: str = ""
    recovery_probe: bool = False
    next_eligible_at: str | None = None


@dataclass(frozen=True)
class SafetyConfig:
    total_request_limit: int = 50_000
    provider_request_limit: int = 25_000
    scrapeops_credit_limit: float = 0.0
    rolling_window_seconds: float = 3600.0
    reservation_lease_seconds: float = 900.0
    cooldown_base_seconds: float = 30.0
    cooldown_max_seconds: float = 900.0
    circuit_failure_threshold: int = 3
    circuit_open_seconds: float = 300.0


class PersistentResolverSafety:
    """Durable request gate, retry schedule, rolling budgets and circuit breaker.

    The store is intentionally separate from the resolver result database so
    the guard can be replaced or audited without rewriting identity results.
    All admission decisions are made in a SQLite write transaction, which keeps
    request and credit ceilings global across worker threads and restarts.
    """

    def __init__(
        self,
        path: Path,
        *,
        config: SafetyConfig | None = None,
        clock: Callable[[], float] = _now_epoch,
    ) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.config = config or SafetyConfig()
        self.clock = clock
        self.connection = sqlite3.connect(self.path, check_same_thread=False, timeout=60)
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("PRAGMA synchronous=FULL")
        self._lock = threading.RLock()
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS safety_requests (
              request_id INTEGER PRIMARY KEY AUTOINCREMENT,
              normalized_url TEXT NOT NULL,
              provider TEXT NOT NULL,
              classification TEXT NOT NULL,
              cost REAL NOT NULL DEFAULT 0,
              recorded_at REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS safety_requests_provider_time
              ON safety_requests(provider, recorded_at);
            CREATE TABLE IF NOT EXISTS safety_reservations (
              reservation_id TEXT PRIMARY KEY,
              normalized_url TEXT NOT NULL,
              provider TEXT NOT NULL,
              estimated_cost REAL NOT NULL DEFAULT 0,
              recovery_probe INTEGER NOT NULL DEFAULT 0,
              reserved_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS safety_retry_state (
              normalized_url TEXT NOT NULL,
              provider TEXT NOT NULL,
              attempts INTEGER NOT NULL DEFAULT 0,
              next_eligible_at REAL,
              last_classification TEXT NOT NULL DEFAULT '',
              last_error TEXT NOT NULL DEFAULT '',
              updated_at REAL NOT NULL,
              PRIMARY KEY(normalized_url, provider)
            );
            CREATE TABLE IF NOT EXISTS safety_circuit_state (
              provider TEXT PRIMARY KEY,
              consecutive_failures INTEGER NOT NULL DEFAULT 0,
              opened_until REAL,
              probe_in_flight INTEGER NOT NULL DEFAULT 0,
              updated_at REAL NOT NULL
            );
            """
        )
        self.connection.commit()

    def _cleanup_expired(self, now: float) -> None:
        cutoff = now - self.config.reservation_lease_seconds
        self.connection.execute("DELETE FROM safety_reservations WHERE reserved_at < ?", (cutoff,))

    def _window_start(self, now: float) -> float:
        return now - self.config.rolling_window_seconds

    def _provider_counts(self, provider: str, now: float) -> tuple[int, float, int, float]:
        window = self._window_start(now)
        request_count, request_cost = self.connection.execute(
            "SELECT COUNT(*), COALESCE(SUM(cost), 0) FROM safety_requests WHERE provider = ? AND recorded_at >= ?",
            (provider, window),
        ).fetchone()
        reservation_count, reservation_cost = self.connection.execute(
            "SELECT COUNT(*), COALESCE(SUM(estimated_cost), 0) FROM safety_reservations WHERE provider = ? AND reserved_at >= ?",
            (provider, window),
        ).fetchone()
        return int(request_count or 0), float(request_cost or 0), int(reservation_count or 0), float(reservation_cost or 0)

    def _total_counts(self, now: float) -> tuple[int, float, int, float]:
        window = self._window_start(now)
        request_count, request_cost = self.connection.execute(
            "SELECT COUNT(*), COALESCE(SUM(cost), 0) FROM safety_requests WHERE recorded_at >= ?",
            (window,),
        ).fetchone()
        reservation_count, reservation_cost = self.connection.execute(
            "SELECT COUNT(*), COALESCE(SUM(estimated_cost), 0) FROM safety_reservations WHERE reserved_at >= ?",
            (window,),
        ).fetchone()
        return int(request_count or 0), float(request_cost or 0), int(reservation_count or 0), float(reservation_cost or 0)

    def allow(self, normalized_url: str, provider: str, *, estimated_cost: float = 0.0, now: float | None = None) -> SafetyDecision:
        """Atomically admit a request or return the durable reason it is held."""

        current = float(self.clock() if now is None else now)
        provider = str(provider or "").strip() or "unknown"
        with self._lock:
            self.connection.execute("BEGIN IMMEDIATE")
            try:
                self._cleanup_expired(current)
                retry = self.connection.execute(
                    "SELECT attempts, next_eligible_at FROM safety_retry_state WHERE normalized_url = ? AND provider = ?",
                    (normalized_url, provider),
                ).fetchone()
                if retry and retry[1] is not None and float(retry[1]) > current:
                    self.connection.commit()
                    return SafetyDecision(False, "cooldown", next_eligible_at=_iso(float(retry[1])))

                circuit = self.connection.execute(
                    "SELECT consecutive_failures, opened_until, probe_in_flight FROM safety_circuit_state WHERE provider = ?",
                    (provider,),
                ).fetchone()
                recovery_probe = False
                if circuit and circuit[1] is not None:
                    opened_until = float(circuit[1])
                    if opened_until > current:
                        self.connection.commit()
                        return SafetyDecision(False, "circuit_open", next_eligible_at=_iso(opened_until))
                    if int(circuit[2] or 0):
                        self.connection.commit()
                        return SafetyDecision(False, "recovery_probe_in_flight", next_eligible_at=_iso(opened_until))
                    recovery_probe = True

                provider_requests, provider_cost, provider_reservations, provider_reserved_cost = self._provider_counts(provider, current)
                total_requests, _total_cost, total_reservations, _total_reserved_cost = self._total_counts(current)
                if provider_requests + provider_reservations >= self.config.provider_request_limit:
                    self.connection.commit()
                    return SafetyDecision(False, "provider_request_budget_exhausted")
                if total_requests + total_reservations >= self.config.total_request_limit:
                    self.connection.commit()
                    return SafetyDecision(False, "global_request_budget_exhausted")
                if provider == "scrapeops" and self.config.scrapeops_credit_limit:
                    if provider_cost + provider_reserved_cost + float(estimated_cost) > self.config.scrapeops_credit_limit:
                        self.connection.commit()
                        return SafetyDecision(False, "provider_credit_budget_exhausted")

                reservation_id = uuid.uuid4().hex
                self.connection.execute(
                    "INSERT INTO safety_reservations(reservation_id, normalized_url, provider, estimated_cost, recovery_probe, reserved_at) VALUES(?,?,?,?,?,?)",
                    (reservation_id, normalized_url, provider, float(estimated_cost), int(recovery_probe), current),
                )
                if recovery_probe:
                    self.connection.execute(
                        "UPDATE safety_circuit_state SET probe_in_flight = 1, updated_at = ? WHERE provider = ?",
                        (current, provider),
                    )
                self.connection.commit()
                return SafetyDecision(True, reservation_id=reservation_id, provider=provider, recovery_probe=recovery_probe)
            except Exception:
                self.connection.rollback()
                raise

    def record(
        self,
        decision: SafetyDecision,
        *,
        normalized_url: str,
        provider: str,
        classification: str,
        success: bool,
        estimated_cost: float = 0.0,
        error: str = "",
        now: float | None = None,
    ) -> None:
        """Commit an admitted request and update its retry/circuit state."""

        current = float(self.clock() if now is None else now)
        provider = str(provider or "").strip() or "unknown"
        classification = str(classification or "network_error").casefold()
        failure = not success or classification in ACCESS_FAILURES
        with self._lock:
            self.connection.execute("BEGIN IMMEDIATE")
            try:
                reservation = self.connection.execute(
                    "SELECT estimated_cost FROM safety_reservations WHERE reservation_id = ?",
                    (decision.reservation_id,),
                ).fetchone()
                reserved_cost = float(reservation[0]) if reservation else float(estimated_cost)
                self.connection.execute("DELETE FROM safety_reservations WHERE reservation_id = ?", (decision.reservation_id,))
                self.connection.execute(
                    "INSERT INTO safety_requests(normalized_url, provider, classification, cost, recorded_at) VALUES(?,?,?,?,?)",
                    (normalized_url, provider, classification, max(reserved_cost, float(estimated_cost)), current),
                )
                state = self.connection.execute(
                    "SELECT attempts FROM safety_retry_state WHERE normalized_url = ? AND provider = ?",
                    (normalized_url, provider),
                ).fetchone()
                attempts = int(state[0] or 0) + 1 if state else 1
                if failure:
                    delay = min(self.config.cooldown_max_seconds, self.config.cooldown_base_seconds * (2 ** max(0, attempts - 1)))
                    next_eligible = current + delay
                    self.connection.execute(
                        """INSERT INTO safety_retry_state(normalized_url, provider, attempts, next_eligible_at, last_classification, last_error, updated_at)
                           VALUES(?,?,?,?,?,?,?)
                           ON CONFLICT(normalized_url, provider) DO UPDATE SET
                             attempts=excluded.attempts, next_eligible_at=excluded.next_eligible_at,
                             last_classification=excluded.last_classification, last_error=excluded.last_error,
                             updated_at=excluded.updated_at""",
                        (normalized_url, provider, attempts, next_eligible, classification, error[:300], current),
                    )
                else:
                    self.connection.execute(
                        """INSERT INTO safety_retry_state(normalized_url, provider, attempts, next_eligible_at, last_classification, last_error, updated_at)
                           VALUES(?,?,?,?,?,?,?)
                           ON CONFLICT(normalized_url, provider) DO UPDATE SET
                             attempts=excluded.attempts, next_eligible_at=excluded.next_eligible_at,
                             last_classification=excluded.last_classification, last_error=excluded.last_error,
                             updated_at=excluded.updated_at""",
                        (normalized_url, provider, attempts, None, classification, "", current),
                    )

                circuit = self.connection.execute(
                    "SELECT consecutive_failures FROM safety_circuit_state WHERE provider = ?",
                    (provider,),
                ).fetchone()
                failures = int(circuit[0] or 0) if circuit else 0
                if failure:
                    failures += 1
                    opened_until = None
                    if failures >= self.config.circuit_failure_threshold:
                        exponent = failures - self.config.circuit_failure_threshold
                        opened_until = current + min(self.config.rolling_window_seconds, self.config.circuit_open_seconds * (2 ** exponent))
                    self.connection.execute(
                        """INSERT INTO safety_circuit_state(provider, consecutive_failures, opened_until, probe_in_flight, updated_at)
                           VALUES(?,?,?,?,?)
                           ON CONFLICT(provider) DO UPDATE SET
                             consecutive_failures=excluded.consecutive_failures, opened_until=excluded.opened_until,
                             probe_in_flight=0, updated_at=excluded.updated_at""",
                        (provider, failures, opened_until, 0, current),
                    )
                else:
                    self.connection.execute(
                        """INSERT INTO safety_circuit_state(provider, consecutive_failures, opened_until, probe_in_flight, updated_at)
                           VALUES(?,?,?,?,?)
                           ON CONFLICT(provider) DO UPDATE SET
                             consecutive_failures=0, opened_until=NULL, probe_in_flight=0, updated_at=excluded.updated_at""",
                        (provider, 0, None, 0, current),
                    )
                self.connection.commit()
            except Exception:
                self.connection.rollback()
                raise

    def cancel(self, decision: SafetyDecision) -> None:
        """Release an admission when a local budget guard prevents the call."""

        if not decision.reservation_id:
            return
        with self._lock:
            self.connection.execute("DELETE FROM safety_reservations WHERE reservation_id = ?", (decision.reservation_id,))
            if decision.recovery_probe:
                self.connection.execute(
                    "UPDATE safety_circuit_state SET probe_in_flight = 0, updated_at = ? WHERE provider = ?",
                    (float(self.clock()), decision.provider),
                )
            self.connection.commit()

    def retry_due(self, normalized_url: str, *, providers: tuple[str, ...] = ()) -> bool:
        """Return whether a retry is currently due for a known failure."""

        current = float(self.clock())
        with self._lock:
            if providers:
                placeholders = ",".join("?" for _ in providers)
                rows = self.connection.execute(
                    f"SELECT next_eligible_at FROM safety_retry_state WHERE normalized_url = ? AND provider IN ({placeholders})",
                    (normalized_url, *providers),
                ).fetchall()
            else:
                rows = self.connection.execute(
                    "SELECT next_eligible_at FROM safety_retry_state WHERE normalized_url = ?",
                    (normalized_url,),
                ).fetchall()
        return not rows or any(value[0] is not None and float(value[0]) <= current for value in rows)

    def snapshot(self, *, now: float | None = None) -> dict[str, Any]:
        current = float(self.clock() if now is None else now)
        with self._lock:
            self._cleanup_expired(current)
            self.connection.commit()
            total_requests, total_cost, total_reservations, total_reserved_cost = self._total_counts(current)
            providers = self.connection.execute(
                "SELECT provider, COUNT(*), COALESCE(SUM(cost),0) FROM safety_requests WHERE recorded_at >= ? GROUP BY provider ORDER BY provider",
                (self._window_start(current),),
            ).fetchall()
            circuits = self.connection.execute(
                "SELECT provider, consecutive_failures, opened_until, probe_in_flight FROM safety_circuit_state ORDER BY provider"
            ).fetchall()
        return {
            "window_seconds": self.config.rolling_window_seconds,
            "total_requests": total_requests,
            "total_reserved_requests": total_reservations,
            "total_cost": round(total_cost, 3),
            "total_reserved_cost": round(total_reserved_cost, 3),
            "providers": {str(row[0]): {"requests": int(row[1]), "cost": round(float(row[2]), 3)} for row in providers},
            "circuits": {
                str(row[0]): {
                    "consecutive_failures": int(row[1]),
                    "opened_until": _iso(row[2]) if row[2] is not None else None,
                    "probe_in_flight": bool(row[3]),
                }
                for row in circuits
            },
        }

    def close(self) -> None:
        with self._lock:
            self.connection.close()
