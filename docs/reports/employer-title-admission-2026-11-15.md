# Employer titles must reach function review

The live PUMA collector fetched R44332, Junior Product Line Manager Kids
Footwear, in its 80-job full-source verification but its business-title regex
rejected the posting before catalog ingestion. The exact title was absent from
the live catalog. This also affected other wording and functions, including
Customer Service Representative, despite its supported business classification.

Recurring employer collection, offline focus preparation, import validation,
enrichment scope and publication scope now admit nonempty unfamiliar titles.
Explicit student/apprenticeship titles remain excluded. Known manual/frontline
retail exclusions, Germany evidence, source integrity, bounded requests, provider
budget and complete-description requirements remain enforced. The original
business matcher is retained only for canonical classification labels; admitting
a source title never authorizes publication. Source-grounded classification,
matching content hashes, contract checks and mandatory experience above two
years still decide publication. Unknown or failed classification stays in review.

This does not expand the paused LinkedIn/legacy acquisition services or authorize
all source jobs for publication. Continuous successful-employer rounds pick up
the broader admission behavior as each source is revisited. PUMA is explicitly
rechecked for immediate owner verification.

Verification: 128 focused tests passed across title admission, focus eligibility,
full PUMA pagination, filtered employer sources and durable registry rounds.
The new regression traverses the actual PUMA collector with unrelated unfamiliar
titles and confirms every eligible listing reaches its full detail request.
Deployed operational evidence is retained under
`/srv/runr/ops/employer-title-admission-20261115/`.
