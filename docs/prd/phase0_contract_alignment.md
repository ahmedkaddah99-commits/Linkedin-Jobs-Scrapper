# Phase 0 Contract Alignment

This document records the concrete outputs of Phase 0 from the remediation PRD.

## Goal

Freeze the shared payload shapes before the larger product workstreams begin, so later changes can build against stable contracts instead of rediscovering structure in each stream.

## Shipped Outputs

Phase 0 is now represented in code by:

- [backend/domain/phase0_contracts.py](/c:/Users/ahmed/Projects_Local/job-automation/Linkedin Jobs Scrapper/backend/domain/phase0_contracts.py)
- `GET /contracts/phase0`

The contract catalog currently exposes:

1. `workspace_configuration_v2`
2. `candidate_asset_descriptor`
3. `rejected_job_review`
4. `mail_connection`
5. `referral_relationship`

## Main Decisions

### Workspace Configuration V2

- Keyword-first targeting is the canonical targeting model.
- Country-based targeting is the canonical location model.
- Source configuration is grouped by source type instead of scattered field ids.
- Technical runtime controls remain supported as backend-only `technical_runtime`.
- Deprecated frontend fields such as `target_roles`, `geo_id`, `candidate_name`, and `candidate_email` are preserved only in `legacy_passthrough`.

### Candidate Assets

- Generated CVs, uploaded CVs, letters, certifications, and bundle exports all fit under one candidate-asset descriptor.
- Workspace binding is explicit and separate from file storage metadata.

### Rejected Job Review

- Rejection reasons are normalized into stable reason codes.
- Override and requeue state is modeled explicitly even before the full rejected-jobs UX lands.

### Mail Connection

- The canonical forward path is `google_oauth`.
- Legacy IMAP password state is still representable as `legacy_imap_password` for migration compatibility.
- Connection state, authorization state, token refs, and sync state are separate concerns.

### Referral Relationship

- The canonical model is person plus company relationships, not one flat contact per company.
- Legacy flat referral contacts normalize into the richer relationship shape.

## Intended Use By Later Streams

- Stream A uses `mail_connection`.
- Stream B uses `workspace_configuration_v2`.
- Stream C uses `candidate_asset_descriptor` and `rejected_job_review`.
- Stream D uses `referral_relationship`.

## Validation

Phase 0 is covered by:

- [tests/test_phase0_contracts.py](/c:/Users/ahmed/Projects_Local/job-automation/Linkedin Jobs Scrapper/tests/test_phase0_contracts.py)
- [tests/test_backend_api.py](/c:/Users/ahmed/Projects_Local/job-automation/Linkedin Jobs Scrapper/tests/test_backend_api.py)
