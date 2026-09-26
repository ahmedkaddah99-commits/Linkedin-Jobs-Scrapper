"""OpenRouter Chat Completions adapter with a bounded local tool loop."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Callable, Mapping
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from ..redaction import redact_text
from ..scope_router import ScopeError, ScopeManifest
from ..state import StateStore
from .base import ProviderResult


_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read one repository-relative file covered by the ticket read allowlist.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Write one repository-relative file covered by the ticket write allowlist.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["path", "content"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_required_tests",
            "description": "Run the exact test commands already approved by the ticket.",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "finish",
            "description": "Finish after making the requested bounded changes.",
            "parameters": {
                "type": "object",
                "properties": {"summary": {"type": "string"}},
                "required": ["summary"],
                "additionalProperties": False,
            },
        },
    },
]


class OpenRouterProvider:
    name = "openrouter"

    def __init__(
        self,
        api_key: str,
        *,
        model: str,
        endpoint: str = "https://openrouter.ai/api/v1",
        store: StateStore,
        max_usd_per_job: float,
        max_usd_per_day: float,
        max_tool_calls: int = 24,
        estimated_request_cost_usd: float = 0.01,
        timeout_seconds: int = 120,
        purpose_models: Mapping[str, str] | None = None,
        opener: Callable[..., Any] = urlopen,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.endpoint = endpoint.rstrip("/") + "/chat/completions"
        self.store = store
        self.max_usd_per_job = max_usd_per_job
        self.max_usd_per_day = max_usd_per_day
        self.max_tool_calls = max_tool_calls
        self.estimated_request_cost_usd = estimated_request_cost_usd
        self.timeout_seconds = timeout_seconds
        self.purpose_models = dict(purpose_models or {"implementation": model})
        self._opener = opener

    @property
    def available(self) -> bool:
        return bool(self.api_key.strip())

    def run(self, prompt_path: Path, *, cwd: Path) -> ProviderResult:
        return ProviderResult(1, "OpenRouter requires a scoped ticket execution request")

    def run_implementation(
        self,
        request: Any,
        prompt_path: Path,
        *,
        cwd: Path,
        test_runner: Callable[[Path, tuple[str, ...]], bool],
    ) -> ProviderResult:
        prompt = prompt_path.read_text(encoding="utf-8")
        scope: ScopeManifest = request.scope
        messages: list[dict[str, Any]] = [
            {
                "role": "system",
                "content": (
                    "You are Runr's bounded implementation worker. Use only the supplied tools. "
                    "Never invent paths, use a shell, access Linear, install packages, commit, deploy, "
                    "or edit anything outside the ticket manifest. Read before editing. Make the smallest "
                    "correct change, run the required tests, then call finish."
                ),
            },
            {"role": "user", "content": prompt},
        ]
        usage: dict[str, Any] = {"requests": 0, "tool_calls": 0}
        session_id: str | None = None
        tests_ran = False
        tests_passed = True

        for _ in range(self.max_tool_calls):
            allowed, job_spend, daily_spend = self._budget_state(request.job_id)
            if not allowed:
                return ProviderResult(
                    1,
                    redact_text(
                        "OpenRouter budget exhausted before the next request "
                        f"(job=${job_spend:.6f}, day=${daily_spend:.6f})"
                    ),
                    session_id,
                    usage,
                )
            try:
                response = self._request(self.model, messages, tools=_TOOLS)
            except HTTPError as exc:
                body = exc.read().decode("utf-8", errors="replace")
                return ProviderResult(
                    1,
                    redact_text(f"OpenRouter HTTP {exc.code}: {body[:2000]}"),
                    session_id,
                    usage,
                )
            except (OSError, URLError, TimeoutError) as exc:
                return ProviderResult(1, redact_text(f"OpenRouter request failed: {exc}"), session_id, usage)
            except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
                return ProviderResult(1, redact_text(f"OpenRouter invalid JSON response: {exc}"), session_id, usage)

            usage["requests"] += 1
            session_id = str(response.get("id") or session_id or "") or None
            response_usage = response.get("usage") or {}
            if not isinstance(response_usage, Mapping):
                response_usage = {}
            self._merge_usage(usage, response_usage)
            cost = self._cost(response_usage)
            self.store.record_provider_spend(
                job_id=request.job_id,
                provider=self.name,
                model=self.model,
                amount_usd=cost,
            )

            message = self._message(response)
            tool_calls = message.get("tool_calls") or []
            if not tool_calls:
                return ProviderResult(
                    1,
                    "OpenRouter invalid output: model must use tools and call finish",
                    session_id,
                    usage,
                    cost,
                )
            messages.append(
                {
                    "role": "assistant",
                    "content": message.get("content"),
                    "tool_calls": tool_calls,
                }
            )

            finished = False
            summary = ""
            for tool_call in tool_calls:
                usage["tool_calls"] += 1
                function = tool_call.get("function") or {}
                name = function.get("name")
                arguments = function.get("arguments", {})
                if isinstance(arguments, str):
                    try:
                        arguments = json.loads(arguments)
                    except json.JSONDecodeError:
                        arguments = {}
                if not isinstance(arguments, dict):
                    arguments = {}
                result, is_finished, finish_summary = self._execute_tool(
                    name,
                    arguments,
                    scope=scope,
                    cwd=cwd,
                    test_runner=test_runner,
                )
                if name == "run_required_tests":
                    tests_ran = True
                    tests_passed = result == "tests_passed: true"
                finished = finished or is_finished
                summary = finish_summary or summary
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": str(tool_call.get("id") or "runr-tool"),
                        "content": result,
                    }
                )
            if finished:
                if tests_ran and not tests_passed:
                    return ProviderResult(1, "tool failed: required tests failed", session_id, usage, cost)
                return ProviderResult(0, redact_text(summary or "OpenRouter finished"), session_id, usage, cost)

        return ProviderResult(1, "OpenRouter invalid output: tool-call limit reached", session_id, usage)

    def complete(self, purpose: str, prompt: str, *, job_id: str = "operator") -> str:
        model = self.purpose_models.get(purpose, self.model)
        allowed, job_spend, daily_spend = self._budget_state(job_id)
        if not allowed:
            raise RuntimeError(
                f"OpenRouter budget exhausted before {purpose} "
                f"(job=${job_spend:.6f}, day=${daily_spend:.6f})"
            )
        response = self._request(
            model,
            [{"role": "system", "content": "Return only the requested artifact."}, {"role": "user", "content": prompt}],
        )
        response_usage = response.get("usage") or {}
        if not isinstance(response_usage, Mapping):
            response_usage = {}
        self.store.record_provider_spend(
            job_id=job_id,
            provider=self.name,
            model=model,
            amount_usd=self._cost(response_usage),
        )
        message = self._message(response)
        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            raise RuntimeError("OpenRouter returned an empty completion")
        return redact_text(content)

    def _budget_state(self, job_id: str) -> tuple[bool, float, float]:
        job_spend, daily_spend = self.store.provider_spend(job_id=job_id, provider=self.name)
        allowed = (
            self.max_usd_per_job > 0
            and self.max_usd_per_day > 0
            and job_spend < self.max_usd_per_job
            and daily_spend < self.max_usd_per_day
        )
        return allowed, job_spend, daily_spend

    def _request(self, model: str, messages: list[dict[str, Any]], *, tools: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": 0.2,
        }
        if tools is not None:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        request = Request(
            self.endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "X-Title": "Runr local automation",
            },
            method="POST",
        )
        with self._opener(request, timeout=self.timeout_seconds) as response:
            decoded = json.loads(response.read().decode("utf-8"))
        if not isinstance(decoded, dict):
            raise ValueError("response body is not an object")
        return decoded

    @staticmethod
    def _message(response: Mapping[str, Any]) -> dict[str, Any]:
        choices = response.get("choices")
        if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
            raise ValueError("response has no choices")
        message = choices[0].get("message")
        if not isinstance(message, dict):
            raise ValueError("response has no message")
        return message

    def _execute_tool(
        self,
        name: str | None,
        arguments: Mapping[str, Any],
        *,
        scope: ScopeManifest,
        cwd: Path,
        test_runner: Callable[[Path, tuple[str, ...]], bool],
    ) -> tuple[str, bool, str]:
        try:
            if name == "read_file":
                relative = self._argument(arguments, "path")
                scope.validate_read_paths((relative,))
                target = self._safe_target(cwd, relative)
                if not target.is_file():
                    return "tool failed: file not found", False, ""
                content = target.read_text(encoding="utf-8")
                return content[:120_000], False, ""
            if name == "write_file":
                relative = self._argument(arguments, "path")
                content = self._argument(arguments, "content")
                scope.validate_write_paths((relative,))
                target = self._safe_target(cwd, relative)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content, encoding="utf-8")
                return "write_ok", False, ""
            if name == "run_required_tests":
                passed = test_runner(cwd, scope.required_tests)
                return f"tests_passed: {str(passed).lower()}", False, ""
            if name == "finish":
                return "finish_acknowledged", True, self._argument(arguments, "summary")
            return "tool failed: unknown tool", False, ""
        except (OSError, ScopeError, TypeError, ValueError) as exc:
            return redact_text(f"tool failed: {exc}"), False, ""

    @staticmethod
    def _argument(arguments: Mapping[str, Any], name: str) -> str:
        value = arguments.get(name)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{name} must be a non-empty string")
        return value

    @staticmethod
    def _safe_target(cwd: Path, relative: str) -> Path:
        if re.match(r"^[A-Za-z]:", relative) or relative.replace("\\", "/").startswith("/"):
            raise ValueError("path must be repository-relative")
        candidate = (cwd / relative).resolve(strict=False)
        root = cwd.resolve()
        if not candidate.is_relative_to(root):
            raise ValueError("path escapes the worktree")
        return candidate

    def _cost(self, usage: Mapping[str, Any]) -> float:
        details = usage.get("cost_details")
        detail_cost = details.get("upstream_inference_cost") if isinstance(details, Mapping) else None
        for value in (usage.get("cost"), detail_cost):
            try:
                if value is not None:
                    return max(0.0, float(value))
            except (TypeError, ValueError):
                continue
        return max(0.0, self.estimated_request_cost_usd)

    @staticmethod
    def _merge_usage(total: dict[str, Any], current: Mapping[str, Any]) -> None:
        for key, value in current.items():
            if isinstance(value, (int, float)):
                total[key] = total.get(key, 0) + value
