# Jobs filter reference correction — 2026-10-12

The owner supplied a Jobright screenshot superseding the earlier one-row layout.
All eight quick filters stay visible with readable 14px type, rectangular corners,
36–38px height, selected-value labels, ellipsis for long values and dropdown arrows.
Leading decorative icons and toolbar zoom are removed. Active filters use mint;
All Filters uses solid teal. The row wraps naturally like the supplied reference.

CompanySearch renders through a React portal into the shared Jobs navigation;
it retains its existing autocomplete, selection, keyboard and query callbacks.
Narrow viewports place search on a full-width navigation row. No filter is moved
into All Filters. Saved filters and clear remain available.

Browser checks require all eight filters, readable typography, no horizontal
control overflow, navigation search and working drawer. Existing reference-filter
checks cover shared criteria and numeric bounds. Deployment uses the committed
frontend plus docs/legal and backend/domain build inputs, production configuration,
immutable release metadata, nginx rollback and public asset verification.
Header placement correction: navigation links retain their intrinsic width, so search cannot cover Documents or Connection. The header wraps safely; at 1500px and below search gets its own full-width header row. Browser checks explicitly reject search/link overlap across desktop and mobile viewport sizes.
