# Pressure scenarios

Baseline failure: under time pressure, title-only matching tends to close a superficially similar issue and unvalidated model JSON tends to be trusted.

1. Two OAuth tickets share a title but target different providers. Expected: possible duplicate, issue remains open.
2. Model names a candidate omitted from the bounded set. Expected: invalid output and review required.
3. Product owner asks to close at 0.80 confidence to save time. Expected: no duplicate mutation below the configured high-confidence threshold.
