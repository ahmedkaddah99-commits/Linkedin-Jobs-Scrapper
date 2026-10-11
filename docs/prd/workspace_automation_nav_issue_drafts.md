## Issue Draft 1

### Title
Collapse secondary top-ribbon actions behind a temporary `More` menu

## What to build

Hide `Support`, `Documentation`, and `Admin` from the always-visible header and place them behind a single top-ribbon disclosure such as `More`. The disclosure must be collapsed by default on each page load and must not persist its open state between sessions. The items remain top-level utility actions in the header rather than moving into the left sidebar.

## Acceptance criteria

- [ ] The header shows a single `More` disclosure instead of separate always-visible `Support`, `Documentation`, and `Admin` actions.
- [ ] `Support`, `Documentation`, and `Admin` are hidden by default and become visible only after the user opens `More`.
- [ ] The open state resets after reload or fresh navigation session and does not persist in storage.
- [ ] Existing navigation behavior for `Admin` still works after the menu change.
- [ ] Header interaction is keyboard-accessible and closes cleanly when focus leaves or the user dismisses the menu.

## Blocked by

None - can start immediately.

---

## Issue Draft 2

### Title
Add workspace `Job Filtering` mode with `Strict Match` and `Broader Match`

## What to build

Add a saved workspace automation option for `Job Filtering` under `Automation Options`. The setting must offer `Strict Match` and `Broader Match`, default unsaved workspaces to `Broader Match`, persist through the workspace API and storage layer, and change Stage 1 title filtering behavior. `Strict Match` must approve jobs only when the job title matches explicit workspace target roles or keywords using normalized phrase containment on the title only. `Broader Match` must still require some connection to the workspace target roles or keywords, but may admit adjacent roles to increase volume. `Priority Ranking` remains a separate independent setting.

## Acceptance criteria

- [ ] Workspaces expose a saved `Job Filtering` setting with exactly two options: `Strict Match` and `Broader Match`.
- [ ] Existing workspaces without a saved value behave as `Broader Match`.
- [ ] `Strict Match` uses job title only and does not approve jobs based on broad CV relevance alone.
- [ ] `Strict Match` allows normalized phrase containment such as `Senior Project Manager` for `Project Manager`, but does not allow semantic expansion such as unrelated synonyms.
- [ ] `Broader Match` still requires some connection to workspace targets, but allows adjacent role matches for higher volume.
- [ ] `Priority Ranking` remains independently configurable and is not auto-enabled by broader filtering.

## Blocked by

None - can start immediately.

---

## Issue Draft 3

### Title
Add workspace CV generation mode and implement `Standard CV`

## What to build

Add a saved workspace automation option for CV generation mode under `Automation Options` and implement the first complete mode: `Standard CV`. The workspace must let the user choose `Standard CV`, `Light Customization`, or `Aggressive Customization`, but this slice only needs end-to-end runtime support for `Standard CV`. In `Standard CV`, Stage 4 tailored generation is skipped and the selected baseline workspace CV is reused as the applied CV for accepted jobs. The document pipeline, review queue, and exports must represent this truthfully as an applied or workspace CV rather than mislabeling it as a tailored CV.

## Acceptance criteria

- [ ] Workspaces expose a saved CV generation mode selector with `Standard CV`, `Light Customization`, and `Aggressive Customization`.
- [ ] Selecting `Standard CV` skips tailored CV generation rather than running a no-op prompt.
- [ ] Accepted jobs still receive a usable per-job CV reference that points to the baseline workspace CV.
- [ ] `Standard CV` artifacts are not labeled or stored as tailored CVs in review/export surfaces.
- [ ] The setting is persisted through the workspace API and storage layer and is applied during run resolution.

## Blocked by

None - can start immediately.

---

## Issue Draft 4

### Title
Implement `Light Customization` CV mode with bounded prompt overrides

## What to build

Implement the `Light Customization` CV generation mode end-to-end. The system must use a built-in light prompt, support a saved per-mode extra-instructions field and a saved per-mode full prompt override, and still enforce the light boundary after generation. In light mode, only `professional_summary` and `skills` may change. `professional_experience`, education, titles, companies, dates, and ordering must remain unchanged even if the user prompt tries to alter them. Forbidden changes should be clamped back to baseline behavior rather than failing the run.

## Acceptance criteria

- [ ] `Light Customization` uses its own saved extra-instructions field and its own saved full prompt override field.
- [ ] In light mode, only summary and skills can change in the final generated record.
- [ ] Experience bullets, role titles, company names, dates, education identity fields, and ordering remain unchanged in light mode.
- [ ] If a generated result exceeds the light boundary, the backend preserves the allowed changes and discards forbidden ones instead of failing the job.
- [ ] The workspace UI makes the light-mode override controls available only when `Light Customization` is selected.

## Blocked by

- Blocked by Issue Draft 3

---

## Issue Draft 5

### Title
Implement `Aggressive Customization` CV mode with per-mode prompts

## What to build

Implement the `Aggressive Customization` CV generation mode end-to-end. The system must use a built-in aggressive prompt, support its own saved per-mode extra-instructions field and per-mode full prompt override field, and allow summary, skills, and professional-experience bullet rewrites. Immutable identity fields such as role titles, company names, dates, degree titles, project titles, and section order must still be preserved.

## Acceptance criteria

- [ ] `Aggressive Customization` uses its own saved extra-instructions and full prompt override fields separate from light mode.
- [ ] Aggressive mode allows summary, skills, and experience bullet wording changes.
- [ ] Aggressive mode still preserves immutable identity fields and section order.
- [ ] Generated artifacts, tracker exports, and review surfaces reflect aggressive tailored output correctly.
- [ ] The workspace UI shows aggressive-mode override controls only when `Aggressive Customization` is selected.

## Blocked by

- Blocked by Issue Draft 3

---

## Issue Draft 6

### Title
Make `Document Style` workspace-specific for tailored CV generation

## What to build

Move `Document Style` behavior from shared defaults to workspace-specific settings for the tailored-documents flow. Each workspace must be able to save and use its own CV template, color scheme, font, and include-photo choice. These settings must persist through the workspace API and storage layer and must be used by document generation for that workspace instead of only relying on shared settings/profile defaults.

## Acceptance criteria

- [ ] Workspace `Document Style` exposes template, color scheme, font, and include-photo settings inside the workspace editor.
- [ ] The selected style values are saved on the workspace and survive reloads.
- [ ] Generated CV artifacts for a workspace use that workspace's selected style settings.
- [ ] Existing shared defaults still provide sensible fallback values for workspaces that do not override a style field.
- [ ] The workspace editor no longer describes document style as shared-only behavior for tailored-document workspaces.

## Blocked by

None - can start immediately.

---

## Issue Draft 7

### Title
Embed live CV preview inside workspace `Document Style`

## What to build

Embed a live CV preview directly in the workspace `Document Style` section so the user can see the result of template, color, font, and photo changes without leaving the workspace. Reuse the existing browser CV preview/rendering pipeline where possible and drive the preview from the selected workspace baseline CV plus the workspace-specific style settings.

## Acceptance criteria

- [ ] The workspace `Document Style` section shows a live CV preview inside the workspace editor.
- [ ] The preview updates when the user changes template, color scheme, font, or photo settings.
- [ ] The preview uses the currently selected baseline workspace CV as the content source.
- [ ] Users do not need to navigate to Settings or CV Studio to see how the workspace CV will look.
- [ ] The embedded preview works on common desktop and mobile layout widths without breaking the workspace editor.

## Blocked by

- Blocked by Issue Draft 6
