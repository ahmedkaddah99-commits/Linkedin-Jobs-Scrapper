---
name: runr-ticket-deduplication
description: Use when a Runr Linear issue must be checked against open or recently closed work before implementation or issue normalization.
---

# Runr ticket deduplication

Use deterministic title, acceptance-criteria, subsystem, entity, and allowed-path filters first. Send only the bounded candidate set to the controller's strict schema adjudicator.

Return exactly `clear`, `possible_duplicate`, or `duplicate`, with candidate ID, confidence, concrete overlap, and concrete differences. Never close or mark an issue duplicate from title similarity alone. Never close an ambiguous candidate. Invalid JSON, a candidate outside the bounded set, contradictory evidence, or confidence below the configured high-confidence threshold becomes `possible_duplicate` plus `Automation State: Needs Review`.

For a schema-valid high-confidence duplicate, ask the controller to add the native duplicate relation, apply `Deduplication State: Duplicate`, and comment with evidence. The controller—not model prose—performs and verifies mutations idempotently.

## Quick check

- Same title but different provider or acceptance criteria: review, not duplicate.
- Same paths but distinct outcomes: review or clear.
- Candidate outside supplied list: invalid output.
- No deterministic candidates: clear without a model call.

Do not implement, close issues, remove relations, or inspect files outside the supplied issue summaries.
