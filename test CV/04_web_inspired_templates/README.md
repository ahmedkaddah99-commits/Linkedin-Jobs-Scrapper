# Web-Inspired CV Templates

This folder contains print-ready HTML CV prototypes chosen from web research because they are both:

- light to generate in code
- visually strong enough to compare with the repo's current CV outputs

Implemented templates:

- `01_ats_single_column.html`
- `01_ats_single_column_no_photo.html`
- `02_editorial_sidebar.html`
- `02_editorial_sidebar_no_photo.html`
- `03_mono_nav.html`
- `03_mono_nav_no_photo.html`
- `04_europass_lite.html`
- `04_europass_lite_no_photo.html`
- `05_signal_header.html`
- `05_signal_header_no_photo.html`
- `06_ledger_split.html`
- `06_ledger_split_no_photo.html`
- `index.html` gallery entry point

Photo support:

- Every template includes an optional profile photo slot.
- If a candidate photo exists in the configured repo path, it is copied into `_assets/` and rendered automatically.
- If no photo exists, the layout still renders with a clean placeholder so the slot remains easy to use.

Why these patterns:

- `ATS Single Column`: highest robustness and lowest generation complexity
- `Editorial Sidebar`: best visual payoff for minimal layout code
- `Mono Nav`: modern feel without complex composition logic
- `Europass Lite`: Europe-familiar structure without the full Europass visual heaviness
- `Signal Header`: strongest visual presence while still remaining code-light
- `Ledger Split`: dense, practical layout for detail-heavy applications

Research sources:


- University of Pennsylvania resume guidance: https://careerservices.upenn.edu/channels/resume/
- Yale resume action verbs: https://ocs.yale.edu/resources/resume-action-verbs/
- Europass CV guidance: https://europass.europa.eu/en/create-europass-cv
- Overleaf MTeck's Resume: https://www.overleaf.com/latex/templates/mtecks-resume/fzgztpkgngjc
- Overleaf CV Sidebar Template: https://www.overleaf.com/latex/templates/cv-sidebar-template/mnwdwhxbxgdg
- Overleaf Monocol Navbar CV: https://www.overleaf.com/latex/templates/monocol-navbar-cv/xdhwjpkpmxyv
