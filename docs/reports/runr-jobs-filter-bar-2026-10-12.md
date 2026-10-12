# Jobs filter bar compact layout â€” 2026-10-12

The desktop Jobs toolbar uses one compact row instead of wrapping oversized
filter pills and search into two rows. Controls and search share a 34px minimum
height, with reduced spacing and type. Dropdowns retain visible overflow.

All eight quick filters remain visible at every viewport width. Desktop controls
use smaller type, padding and gaps, with additional toolbar scaling below 1401px
to keep every filter, saved filters, clear and search in one row. No criteria
are hidden or moved into All Filters. Mobile keeps its wrapped layout and
full-width search. The selected-company hint floats below the search.

Verification covers a single row, toolbar height under 60px and no control
overflow at 820, 1024, 1280, 1440, 1700, 1920 and 2560px; mobile search and opening
All Filters are also checked. Frontend unit tests, ESLint and Vite build apply.
The older company saved-search test expects a removed â€œSave current filtersâ€
button; that failure is outside this layout change.

`deploy/deploy-jobs-filter-bar-frontend.sh` installs an immutable frontend release
from the committed archive, preserves production Clerk/API settings, checks
release metadata and absence of test auth, and switches nginx with rollback.
It verifies public release metadata and `/jobs` after reload. API, customer
workers and acquisition continue on their existing releases.
