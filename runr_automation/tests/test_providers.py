from datetime import datetime, timedelta, timezone
from pathlib import Path
import subprocess
import sys

import pytest

from runr_automation.providers.base import LocalCLIProvider, ProviderErrorKind, classify_provider_error
from runr_automation.providers.routing import ProviderRouter, RoutingConfig


def test_routing_prefers_subscriptions_and_never_uses_disabled_openrouter() -> None:
    router = ProviderRouter(
        RoutingConfig(("codex", "opencode_subscription", "opencode_openrouter"), False, 0, 0),
        available={"codex": False, "opencode_subscription": True, "opencode_openrouter": True},
    )
    assert router.choose(job_spend_usd=0, daily_spend_usd=0) == "opencode_subscription"
    router.available["opencode_subscription"] = False
    assert router.choose(job_spend_usd=0, daily_spend_usd=0) is None


def test_openrouter_requires_both_budgets_and_open_circuit_fails_over() -> None:
    now = datetime(2026, 9, 17, tzinfo=timezone.utc)
    router = ProviderRouter(
        RoutingConfig(("codex", "opencode_openrouter"), True, 2.0, 10.0),
        available={"codex": True, "opencode_openrouter": True},
    )
    router.open_circuit("codex", "capacity", now + timedelta(minutes=5))
    assert router.choose(job_spend_usd=1.0, daily_spend_usd=5.0, now=now) == "opencode_openrouter"
    assert router.choose(job_spend_usd=2.0, daily_spend_usd=5.0, now=now) is None


@pytest.mark.parametrize(
    ("message", "kind"),
    [
        ("401 unauthorized", ProviderErrorKind.AUTHENTICATION),
        ("429 rate limit exceeded", ProviderErrorKind.CAPACITY),
        ("connection timed out", ProviderErrorKind.TRANSIENT),
        ("invalid json response", ProviderErrorKind.INVALID_OUTPUT),
    ],
)
def test_provider_errors_are_classified(message, kind) -> None:
    assert classify_provider_error(message) == kind


def test_local_cli_provider_materializes_paths_uses_stdin_and_extracts_session(tmp_path: Path) -> None:
    prompt = tmp_path / "prompt.md"
    prompt.write_text("bounded prompt", encoding="utf-8")
    script = tmp_path / "provider.py"
    script.write_text(
        "import pathlib,sys; print(pathlib.Path.cwd()); print(sys.stdin.read()); print('session id: session-123')",
        encoding="utf-8",
    )
    provider = LocalCLIProvider(
        "codex",
        sys.executable,
        (sys.executable, str(script), "{cwd}", "-"),
        model="test-model",
    )

    result = provider.run(prompt, cwd=tmp_path)

    assert result.returncode == 0
    assert "bounded prompt" in result.output
    assert result.session_id == "session-123"


def test_local_cli_provider_decodes_utf8_provider_output(tmp_path: Path) -> None:
    prompt = tmp_path / "prompt.md"
    prompt.write_text("bounded prompt", encoding="utf-8")
    script = tmp_path / "provider.py"
    script.write_text(
        "import sys; sys.stdout.buffer.write(bytes.fromhex('72696768742071756f74653a20e2809d0a'))",
        encoding="utf-8",
    )
    provider = LocalCLIProvider(
        "codex",
        sys.executable,
        (sys.executable, str(script), "-"),
        model="test-model",
    )

    result = provider.run(prompt, cwd=tmp_path)

    assert result.returncode == 0
    assert "right quote: ”" in result.output


def test_local_cli_provider_turns_timeout_into_a_retryable_result(tmp_path: Path, monkeypatch) -> None:
    prompt = tmp_path / "prompt.md"
    prompt.write_text("bounded prompt", encoding="utf-8")
    provider = LocalCLIProvider(
        "codex",
        sys.executable,
        (sys.executable, "provider.py"),
        model="test-model",
        timeout_seconds=1,
    )

    def timed_out(*args, **kwargs):
        raise subprocess.TimeoutExpired(args[0], 1, output="partial", stderr="deadline")

    monkeypatch.setattr(subprocess, "run", timed_out)

    result = provider.run(prompt, cwd=tmp_path)

    assert result.returncode == 124
    assert classify_provider_error(result.output) == ProviderErrorKind.TRANSIENT
    assert "timed out" in result.output
