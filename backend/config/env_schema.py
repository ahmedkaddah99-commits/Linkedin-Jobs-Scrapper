from __future__ import annotations

import os
from typing import Any

CLERK_SESSION_TOKEN_TEMPLATE_HINT = {
    "publicMetadata": {
        "role": "{{user.public_metadata.role}}",
        "plan_id": "{{user.public_metadata.plan_id}}",
        "quota_overrides": "{{user.public_metadata.quota_overrides}}",
    }
}

ENV_SCHEMA: dict[str, dict[str, Any]] = {
    "CLERK_SECRET_KEY": {
        "required": True,
        "scope": "backend",
        "description": "Clerk Backend API secret key.",
    },
    "CLERK_PUBLISHABLE_KEY": {
        "required": True,
        "scope": "shared",
        "description": "Clerk publishable key used by the frontend and deployment config.",
    },
    "CLERK_WEBHOOK_SECRET": {
        "required": True,
        "scope": "backend",
        "description": "Clerk Svix webhook signing secret.",
    },
    "LEMONSQUEEZY_API_KEY": {
        "required": True,
        "scope": "backend",
        "description": "LemonSqueezy API key used for checkout and portal calls.",
    },
    "LEMONSQUEEZY_WEBHOOK_SECRET": {
        "required": True,
        "scope": "backend",
        "description": "LemonSqueezy webhook signing secret.",
    },
    "LEMONSQUEEZY_STORE_ID": {
        "required": True,
        "scope": "backend",
        "description": "LemonSqueezy store identifier for checkout creation.",
    },
    "VITE_CLERK_PUBLISHABLE_KEY": {
        "required": True,
        "scope": "frontend",
        "description": "Frontend Clerk publishable key exposed to Vite.",
    },
    "RUNR_ENABLE_LIVE_NETWORKING_DISCOVERY": {
        "required": False,
        "scope": "backend",
        "description": "Optional opt-in for live DuckDuckGo and DeepSeek target-contact discovery. Disabled by default for deterministic local/test behavior.",
    },
    "RUNR_DISABLE_QUOTAS": {
        "required": False,
        "scope": "backend",
        "description": "Optional local-development switch that bypasses quota enforcement when set to 1/true/yes/on.",
    },
}


def get_env(name: str, default: str = "") -> str:
    return str(os.getenv(name, default) or default).strip()


def require_env(name: str) -> str:
    value = get_env(name)
    if value:
        return value
    raise RuntimeError(f"Missing required environment variable: {name}")


def get_missing_required_env() -> list[str]:
    return [name for name, descriptor in ENV_SCHEMA.items() if descriptor.get("required") and not get_env(name)]


def describe_env_schema() -> dict[str, dict[str, Any]]:
    return {
        name: {
            **descriptor,
            "value_present": bool(get_env(name)),
        }
        for name, descriptor in ENV_SCHEMA.items()
    }
