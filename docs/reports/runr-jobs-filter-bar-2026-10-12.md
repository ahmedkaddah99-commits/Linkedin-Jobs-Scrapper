# Jobs filter bar compact layout — 2026-10-12

The desktop Jobs toolbar uses one compact row instead of wrapping oversized
filter pills and search into two rows. Controls and search share a 34px minimum
height, with reduced spacing and type. Dropdowns retain visible overflow.

Above 1700px all eight quick filters remain visible. At 1401–1700px Industry and
Years of Experience move into the existing All Filters drawer. At 801–1400px the
row keeps Location, Job Function, All Filters, saved filters, clear and search;
all other criteria remain available in All Filters. Mobile keeps its wrapped
layout and full-width search. The selected-company hint floats below the search
without increasing toolbar height.

Verification covers a single row, toolbar height under 60px and no control
overflow at 820, 1024, 1280, 1440, 1700, 1920 and 2560px; mobile search and opening
All Filters are also checked. Frontend unit tests, ESLint and Vite build apply.
The older company saved-search test expects a removed “Save current filters”
button; that failure is outside this layout change.

`deploy/deploy-jobs-filter-bar-frontend.sh` installs an immutable frontend release
from the committed archive, preserves production Clerk/API settings, checks
release metadata and absence of test auth, and switches nginx with rollback.
It verifies public release metadata and `/jobs` after reload. API, customer
workers and acquisition continue on their existing releases.
