# OpenRouter adapter and configurable provider routing

## Goal

Make the deployment branch's local Linear controller able to execute a bounded
ticket through OpenRouter, while keeping OpenCode and Codex selectable in a
user-defined priority order. Codex is the recommended final fallback, not an
implicit first choice. Load secrets from the deployment checkout's
`user_config/.env` (with process environment taking precedence) without
printing or committing them.

## Design

1. Extend configuration with a provider order, OpenRouter endpoint/key-env,
   per-purpose model names, and spend limits. Keep the execution interface
   compatible with the existing CLI providers.
2. Add a standard-library OpenRouter Chat Completions adapter. It will execute
   only four local tools: read an allowed file, write an allowed file, run the
   ticket's already-approved test commands, and finish. No shell tool, Linear
   tool, package installer, commit, or deployment tool is exposed to the
   model. Every path is checked against the ticket scope before access.
3. Add durable OpenRouter spend accounting and prevent calls when per-job or
   per-day limits are reached. Preserve the existing checkpoint/safe-stop and
   approval flow.
4. Load `OPENROUTER_API_KEY`, `LINEAR_API_TOKEN`, and other process settings
   from `user_config/.env` as a local compatibility path, while allowing the
   recommended `%LOCALAPPDATA%\\RunrAutomation\\secrets.env` path too.
5. Wire the provider into `doctor`, `once`, and `verify-provider`; update the
   example configuration and operator guide with exact setup and routing
   semantics.
6. Add tests first for config/env loading, tool-call path enforcement, budget
   limits, provider fallback order, and a full isolated controller cycle using
   a local HTTP OpenRouter fixture. Run the complete automation test suite,
   Ruff, the deployment branch's Python-version check, and a real OpenRouter
   verification only when the configured key and enabled budget permit it.

## Acceptance criteria

- `providers.order` is the only priority source; an example can place
  `opencode_subscription`, then `openrouter`, then `codex`.
- OpenRouter is skipped unless enabled, keyed, and both spend limits are
  positive; Codex remains available as the final fallback when discovered.
- An OpenRouter tool-call implementation can change only allowed ticket paths,
  run only approved tests, produce the same isolated commit and predeployment
  approval as the CLI adapters, and persist redacted usage/session metadata.
- The key is accepted from `user_config/.env` but never printed, stored in
  SQLite, or committed.
- A local end-to-end test reaches `awaiting_approval`; no fake approval is used.
- The deployment branch contains the implementation and its guide.
