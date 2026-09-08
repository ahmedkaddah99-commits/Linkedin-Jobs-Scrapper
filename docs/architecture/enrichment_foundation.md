# Runr enrichment foundation

This document describes the inactive, provider-neutral backend foundation
introduced by migration `049_enrichment_foundation`.

## Boundary

Providers implement `EnrichmentProvider` from `backend/enrichment/contracts.py`.
They expose metadata, capability, and resolution. They return candidates and
`EvidenceEnvelope` values; they do not receive a database connection, storage
handle, HTTP client, or publication writer.

The current worker-only `CompanyEnrichmentProvider` remains unchanged. It is a
separate compatibility boundary for the existing disabled company worker. The
new contract is the future provider-neutral boundary and does not activate that
worker.

## Evidence lifecycle

1. Build an `EnrichmentRequest` from an immutable observation or sanitized
   offline fixture.
2. Calculate the deterministic input fingerprint and cache key.
3. Execute a provider with `ProviderExecutionContext`. The default external
   budget is zero and network access is false.
4. Receive candidates and evidence without writing storage.
5. Apply deterministic selection rules outside the provider.
6. Append evidence to `enrichment_evidence`; historical evidence is never
   updated or deleted. Superseding evidence references the prior row.
7. Keep any result report-only until a later approval explicitly activates a
   version and a publication path.

Raw source responses are not persisted unless both the provider license and the
retention policy explicitly allow it. Cache entries contain sanitized result
metadata and use separate positive and negative TTLs.

## Versions and activation

`enrichment_version_registry` records mapping tables, adapters, datasets,
policies, rules, and model/prompt versions. New rows are inactive by default.
Activation is explicit and independent from publication. The foundation's
publication gate is hard-disabled; the existing `unified_mapping_v1` output is
not changed.

## Deterministic domain boundaries

`backend/enrichment/boundaries.py` keeps place, company, occupation, and
language concerns separate:

- multiple locations become independent place requests;
- remote is workplace context, not a worldwide geography;
- company identity cannot be auto-linked by name alone;
- headquarters, registered office, and job location remain distinct;
- Runr function, occupation, employment type, and seniority remain distinct;
- posting language alone never establishes a required language or proficiency.

Required language evidence must be structured or explicit/labeled. Otherwise
the result is `preferred`, `mentioned`, or `not_established`.

## Fixture privacy

The checked-in fixture is local-only, sanitized, and explicitly synthetic. It
contains connector labels, safe fixture identifiers, titles, locations, short
evidence excerpts, and expected labels for development/calibration cases. It
does not contain full descriptions, personal data, secrets, or provider
payloads. The blind holdout has no labels in the ordinary fixture file.

The current verified production context is **1,789 observations, 217 canonical
jobs, 17 canonical-company rows, and 15 profiled employers**. Those figures are
context only: the offline trial never reads production records and does not
write or publish enrichment results.

## Replay, rollback, and approval gates

Replay must preserve immutable observations and create new evidence/projections
under new rule/provider/version keys. Rollback means switching an inactive
projection/version pointer or disabling the provider; it does not delete
evidence. A shadow trial requires explicit approval for provider terms,
accounts, data transfer, budgets, retention, and publication.

## Adding a provider safely

Add provider metadata and a pure adapter implementing the contract. Start with
an offline fixture provider. Add contract, result-state, budget, network,
license, privacy, cache, replacement, and replay tests. Do not add a provider
to a production registry or publication path in the same change as the
foundation.
