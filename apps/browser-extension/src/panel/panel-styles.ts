/**
 * Styles for the in-page assistant panel.
 *
 * Delivered as a string and injected into a shadow root rather than imported as
 * a stylesheet: a runtime-registered content script has no web-accessible CSS
 * file to fetch, and the shadow boundary is what keeps employer page CSS from
 * reaching the panel (and vice versa).
 *
 * Geometry follows the reference captures: a fixed right-edge column roughly
 * 380px wide, with a fixed header, a fixed tab row, a scrolling body, and a
 * pinned bottom action.
 */
export const PANEL_WIDTH_PX = 380;

export const PANEL_CSS = `
:host {
  all: initial;
}

*, *::before, *::after { box-sizing: border-box; }

.panel {
  --runr-bg: #ffffff;
  --runr-surface: #f6f7f9;
  --runr-border: #e3e6ea;
  --runr-text: #14181f;
  --runr-muted: #646c7a;
  --runr-accent: #1f9d8f;
  --runr-accent-text: #ffffff;
  --runr-warn: #c77700;
  --runr-shadow: 0 1px 3px rgba(16, 22, 33, 0.08);

  position: fixed;
  top: 0;
  right: 0;
  width: ${PANEL_WIDTH_PX}px;
  height: 100vh;
  z-index: 2147483646;
  display: flex;
  flex-direction: column;
  background: var(--runr-bg);
  border-left: 1px solid var(--runr-border);
  color: var(--runr-text);
  font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
  font-size: 14px;
  line-height: 1.45;
}

@media (prefers-color-scheme: dark) {
  .panel {
    --runr-bg: #0f1520;
    --runr-surface: #17202e;
    --runr-border: #26303f;
    --runr-text: #eef2f7;
    --runr-muted: #93a0b1;
    --runr-accent: #2fc4b2;
    --runr-accent-text: #06231f;
    --runr-warn: #f0ad3e;
    --runr-shadow: 0 1px 3px rgba(0, 0, 0, 0.4);
  }
}

.header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 12px 14px;
  border-bottom: 1px solid var(--runr-border);
  flex: 0 0 auto;
}

.brand { display: flex; align-items: center; gap: 8px; font-weight: 650; font-size: 15px; }
.brand-mark {
  width: 22px; height: 22px; border-radius: 6px;
  background: var(--runr-accent); color: var(--runr-accent-text);
  display: grid; place-items: center; font-size: 12px; font-weight: 700;
}

.header-actions { display: flex; align-items: center; gap: 4px; }

.icon-button {
  appearance: none; background: transparent; border: 1px solid transparent;
  border-radius: 6px; padding: 4px 8px; cursor: pointer;
  color: var(--runr-muted); font: inherit; font-size: 12px; line-height: 1.2;
}
.icon-button:hover { background: var(--runr-surface); color: var(--runr-text); }
.icon-button:focus-visible { outline: 2px solid var(--runr-accent); outline-offset: 1px; }

.tabs {
  display: flex; gap: 4px; padding: 8px 10px;
  border-bottom: 1px solid var(--runr-border); flex: 0 0 auto;
}
.tab {
  appearance: none; background: transparent; border: none; border-radius: 8px;
  padding: 6px 10px; cursor: pointer; color: var(--runr-muted);
  font: inherit; font-size: 13px; font-weight: 550; flex: 1 1 auto;
}
.tab[aria-selected="true"] { background: var(--runr-surface); color: var(--runr-text); }
.tab:focus-visible { outline: 2px solid var(--runr-accent); outline-offset: 1px; }

.body { flex: 1 1 auto; overflow-y: auto; padding: 12px 14px; display: flex; flex-direction: column; gap: 12px; }

.card {
  border: 1px solid var(--runr-border); border-radius: 10px;
  background: var(--runr-bg); box-shadow: var(--runr-shadow); padding: 12px;
}

.job { display: flex; gap: 10px; align-items: flex-start; }
.job-logo {
  width: 40px; height: 40px; border-radius: 8px; flex: 0 0 auto;
  background: var(--runr-surface); color: var(--runr-text);
  display: grid; place-items: center; font-weight: 700; font-size: 16px;
}
.job-title { font-weight: 650; font-size: 15px; margin: 0; }
.job-meta { color: var(--runr-muted); font-size: 12px; margin: 2px 0 0; }

.footer {
  flex: 0 0 auto; padding: 12px 14px;
  border-top: 1px solid var(--runr-border); background: var(--runr-bg);
}

.primary {
  appearance: none; width: 100%; border: none; border-radius: 10px;
  padding: 11px 14px; cursor: pointer;
  background: var(--runr-accent); color: var(--runr-accent-text);
  font: inherit; font-size: 14px; font-weight: 650;
}
.primary:disabled { opacity: 0.55; cursor: not-allowed; }
.primary:focus-visible { outline: 2px solid var(--runr-text); outline-offset: 2px; }

.footer-note { color: var(--runr-muted); font-size: 12px; margin: 8px 0 0; text-align: center; }

.empty { color: var(--runr-muted); font-size: 13px; margin: 0; }

.progress-title { font-weight: 650; font-size: 14px; margin: 0 0 2px; }
.progress-detail { color: var(--runr-muted); font-size: 12px; margin: 0 0 8px; }
.accent { color: var(--runr-accent); font-weight: 650; }
.section-title { font-weight: 650; font-size: 13px; margin: 12px 0 4px; }

.field-list { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 4px; }
.field-row { display: flex; gap: 8px; align-items: flex-start; font-size: 13px; }
.field-label { flex: 1 1 auto; overflow-wrap: anywhere; }
.glyph { flex: 0 0 auto; width: 16px; text-align: center; font-size: 12px; line-height: 1.5; font-weight: 700; }
.glyph-done { color: var(--runr-accent); }
.glyph-attention { color: var(--runr-warn); }

.score-row { display: flex; gap: 12px; align-items: center; margin-bottom: 8px; }
.score-ring {
  width: 44px; height: 44px; border-radius: 50%; flex: 0 0 auto;
  display: grid; place-items: center; font-weight: 700; font-size: 15px;
  border: 3px solid var(--runr-border); color: var(--runr-text);
}
.score-low { border-color: #d2544a; }
.score-fair { border-color: var(--runr-warn); }
.score-strong { border-color: var(--runr-accent); }

.collapsed {
  position: fixed; top: 88px; right: 0; z-index: 2147483646;
  appearance: none; cursor: pointer;
  border: 1px solid var(--runr-border); border-right: none;
  border-radius: 8px 0 0 8px; padding: 10px 8px;
  background: var(--runr-bg); color: var(--runr-text);
  font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
  font-size: 12px; font-weight: 650; box-shadow: var(--runr-shadow);
  writing-mode: vertical-rl;
}
`;
