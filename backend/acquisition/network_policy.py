from __future__ import annotations

import ipaddress
import os
from collections.abc import Mapping
from urllib.parse import urlsplit


LIVE_NETWORK_ENV = "RUNR_ACQUISITION_LIVE_NETWORK_ENABLED"


class AcquisitionNetworkPolicyError(RuntimeError):
    """Raised before Phase A can perform an unauthorized network operation."""


def live_network_enabled(environ: Mapping[str, str] | None = None) -> bool:
    source = os.environ if environ is None else environ
    return str(source.get(LIVE_NETWORK_ENV, "")).strip().casefold() in {"1", "true", "yes", "on"}


def hostname_for_url(url: str) -> str:
    return (urlsplit(str(url or "")).hostname or "").casefold().rstrip(".")


def is_loopback_or_local_host(hostname: str) -> bool:
    normalized = str(hostname or "").casefold().rstrip(".")
    if normalized in {"localhost", "localhost.localdomain"}:
        return True
    try:
        return ipaddress.ip_address(normalized).is_loopback
    except ValueError:
        return False


def require_phase_a_network_permission(
    *,
    request_url: str,
    canonical_url: str,
    requester_injected: bool,
    allowed_hosts: set[str],
) -> None:
    """Enforce the final pre-dispatch guard for real Phase A requests.

    Fixture requesters are explicitly injected and never leave the process. Real
    requesters require the environment gate and an exact manifest hostname.
    """

    request_parts = urlsplit(str(request_url or ""))
    canonical_parts = urlsplit(str(canonical_url or ""))
    request_host = hostname_for_url(request_url)
    canonical_host = hostname_for_url(canonical_url)
    expected_hosts = {str(host).casefold().rstrip(".") for host in allowed_hosts if str(host).strip()}
    if request_parts.scheme.casefold() != "https" or canonical_parts.scheme.casefold() != "https":
        raise AcquisitionNetworkPolicyError("phase_a_https_required")
    if (
        not request_host
        or request_host not in expected_hosts
        or not canonical_host
        or canonical_host not in expected_hosts
    ):
        raise AcquisitionNetworkPolicyError("phase_a_hostname_not_allowlisted")
    if is_loopback_or_local_host(request_host):
        raise AcquisitionNetworkPolicyError("phase_a_loopback_target_rejected")
    if not requester_injected and not live_network_enabled():
        raise AcquisitionNetworkPolicyError("phase_a_live_network_disabled")


__all__ = [
    "AcquisitionNetworkPolicyError",
    "LIVE_NETWORK_ENV",
    "hostname_for_url",
    "is_loopback_or_local_host",
    "live_network_enabled",
    "require_phase_a_network_permission",
]
