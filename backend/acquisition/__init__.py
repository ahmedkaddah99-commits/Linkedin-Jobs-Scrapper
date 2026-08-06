"""Server-owned acquisition primitives for the Phase A catalog tracer bullet."""

from backend.acquisition.manifest import PHASE_A_TARGETS, load_phase_a_manifest

__all__ = ["PHASE_A_TARGETS", "load_phase_a_manifest"]
