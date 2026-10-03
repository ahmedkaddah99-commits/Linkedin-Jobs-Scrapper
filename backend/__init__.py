"""Unified backend package for workspace-driven job automation."""

__all__ = ["create_backend"]


def __getattr__(name: str):
    if name == "create_backend":
        from .bootstrap import create_backend

        return create_backend
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
