# Offline deterministic enrichment trial

- Run: `trial_run_68332a7696ef82840d24`
- Rule version: `deterministic_trial_rules_v1`
- Fixture fingerprint: `97fbec0664acc6f718b0248759e96929ff037008a6265fbd89adb73547f1b2e5`
- Network calls: **none**
- External/AI provider calls: **none**; only checked-in fixture providers and the NullProvider boundary are allowed
- Production writes/publication: **none**

## Promotion recommendation

**continue shadow evaluation**

This is a report-only trial. No rule becomes production-active and no AI auto-accept path exists.

## Partitions

| Partition | Fixture cases | Outputs | Golden-label cases | Metrics |
|---|---:|---:|---:|---|
| development | 18 | 72 | 18 | available |
| calibration | 5 | 20 | 5 | available |
| blind_holdout | 5 | 20 | 0 | unavailable |

## Golden labels

23 labeled cases are covered by adjudication metadata; 23 are marked adjudicated. The blind holdout remains unlabeled.

## Dimension metrics

| Dimension | Precision | Recall | Macro-F1 | Top-1 | Top-3 | FPR | Ambiguity | Calibration |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| place_normalization | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 0.0 | 0.035714 | unavailable |
| company_profile | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 0.0 | 0.0 | unavailable |
| occupation_function | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | 0.0 | 0.035714 | unavailable |
| language_evidence | 1.0 | 1.0 | 1.0 | None | None | 0.0 | 0.0 | unavailable |

## Adversarial evaluation

- **ambiguous Paris:** pass (1 cases)
- **Lowell employer plus Leeds:** pass (2 cases)
- **Lowell, Massachusetts:** pass (1 cases)
- **multiple locations:** pass (1 cases)
- **Remote Germany/EU/unrestricted:** pass (5 cases)
- **department/title conflict:** pass (1 cases)
- **internship and working-student separation:** pass (3 cases)
- **posting language without language requirement:** pass (2 cases)

## Data gaps

- blind holdout is intentionally unlabeled in checked-in fixtures; holdout correctness metrics are unavailable
- fixture providers supplied no confidence scores; calibration metrics are unavailable
- small synthetic labeled sample (23 cases); results are directional, not confidence claims
- no external datasets, production observations, or provider responses were evaluated

## Replay comparison

`deterministic_trial_rules_v1` → `deterministic_trial_rules_v2` changed **1** of **112** outputs.
Changes by dimension: occupation_function=1.
