# AA-13 frame and shadow DOM support boundary

Recorded: 2026-07-18

| Surface | Inspection | Fill/validation | V1 outcome | Permission impact |
|---|---|---|---|---|
| Top document | Native V1 controls | Supported | Ready/review according to package policy | Existing active-tab access only |
| Same-origin iframe | Recursive native-control inspection | Supported with frame-realm native setters, events, readback, and validation | Ready/review according to package policy | None; browser same-origin access only |
| Cross-origin iframe | Frame boundary only; child DOM is not read | Not supported | Manual: complete the third-party frame directly | None; no child-origin permission requested |
| Open shadow root | Recursive native-control inspection | Supported with composed events, readback, and validation | Ready/review according to package policy | None |
| Closed shadow root | Host boundary only when the page exposes a closed-root marker; contents remain unreadable | Not supported | Manual: complete the closed-root section directly | None |
| Custom semantic control | ARIA role and accessible label may be classified | Never generically filled | Manual: adapter-specific support is required | None |

The generic fallback is deliberately classification-only. It creates no executable
control registration or approved fill match, does not infer support for a new ATS,
and cannot operate final-submit controls. A supported Greenhouse or Lever adapter
and an approved package answer remain prerequisites for every fill.

Fixture evidence lives in `greenhouse-application.html`, `same-origin-frame.html`,
and `cross-origin-frame.html`. The unit matrix additionally forces an inaccessible
frame boundary and proves that cross-origin, closed-root, and custom semantic
records resolve to actionable `manual_only` matches.
