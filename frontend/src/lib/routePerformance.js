// Route names, never raw URLs or user-controlled identifiers, are used in marks.
export const ROUTE_READINESS_BUDGET_MS = 5000;

export const ROUTE_INVENTORY = Object.freeze([
  { name: "home", path: /^\/$/, useful: ".runr-focus-list a" },
  { name: "jobs", path: /^\/jobs$/, useful: ".jobs-list-card, .jobs-list-panel__body .jobs-empty, .jobs-catalog-state--failure" },
  { name: "job-detail", path: /^\/jobs\/[^/]+$/, useful: ".jobs-detail-heading h1, .jobs-catalog-state--failure" },
  { name: "tracker", path: /^\/tracker$/, useful: "[data-column]" },
  { name: "tracker-ats", path: /^\/tracker\/[^/]+\/ats$/, useful: "main h1" },
  { name: "job-description", path: /^\/tracker\/job-descriptions\/[^/]+$/, useful: "main h1" },
  { name: "documents", path: /^\/documents$/, useful: ".documents-table__row, .documents-empty-state, .documents-table-message--error" },
  { name: "document-edit", path: /^\/documents\/assets\/[^/]+\/edit$/, useful: "main h1" },
  { name: "career-evidence", path: /^\/career-evidence$/, useful: "main h4, main .text-error" },
  { name: "career-evidence-detail", path: /^\/career-evidence\/[^/]+$/, useful: "main h1" },
  { name: "career-assets", path: /^\/career-assets$/, useful: "main section article" },
  { name: "refer", path: /^\/(?:refer|referrals)$/, useful: ".referral-list__body .referral-contact, .referral-list__body .referral-empty, .referral-list__body .referral-feedback--error" },
  { name: "settings", path: /^\/settings$/, useful: "main .grid .space-y-8, main .text-error" },
]);

export function routeForPath(pathname) {
  return ROUTE_INVENTORY.find((route) => route.path.test(String(pathname || ""))) || null;
}

export function routeReadyState(route, root) {
  if (!route || !root) return null;
  const main = root.querySelector("main");
  if (!main) return null;
  const fatal = main.querySelector("[role='alert'] h1");
  if (fatal && /could not|unavailable/i.test(fatal.textContent || "")) return "error";
  const useful = main.querySelector(route.useful);
  if (!useful) {
    if (route.name === "career-evidence" && main.textContent?.includes("No career profiles yet.")) return "empty";
    if (route.name === "career-assets" && main.textContent?.includes("No assets match these filters")) return "empty";
    return null;
  }
  const text = String(useful.textContent || "");
  if (/\bLoading\b/i.test(text)) return null;
  if (useful.tagName === "H1" && /unavailable|could not/i.test(text)) return "error";
  if (useful.matches(".jobs-catalog-state--failure, .documents-table-message--error, .referral-feedback--error, .text-error")) return "error";
  if (/^(No |There are no |Nothing )/i.test(text.trim()) || useful.matches(".documents-empty-state, .jobs-empty")) return "empty";
  return "content";
}

export function percentile(values, fraction) {
  if (!values.length) return null;
  const sorted = [...values].sort((left, right) => left - right);
  return sorted[Math.ceil((sorted.length - 1) * fraction)];
}

export function summarizeReadiness(samples) {
  const timings = samples.filter((sample) => Number.isFinite(sample) && sample >= 0);
  return {
    samples: timings.length,
    p50: percentile(timings, 0.5),
    p75: percentile(timings, 0.75),
    p95: percentile(timings, 0.95),
  };
}

export function markRoutePhase(routeName, phase, mode = "warm", state = null) {
  if (!ROUTE_INVENTORY.some((route) => route.name === routeName)) return null;
  if (!["navigation", "shell", "session-connected", "useful-render", "interactive", "error"].includes(phase)) return null;
  if (typeof performance === "undefined" || typeof performance.mark !== "function") return null;
  const name = `runr-route:${routeName}:${phase}`;
  const detail = {
    route: routeName,
    phase,
    mode: mode === "cold" ? "cold" : "warm",
    deviceClass: typeof matchMedia === "function" && matchMedia("(pointer: coarse) and (max-width: 640px)").matches ? "mobile" : "desktop",
    revision: String(import.meta.env?.VITE_RELEASE_VERSION || import.meta.env?.VITE_RUNR_REVISION || "dev"),
  };
  if (["content", "empty", "error"].includes(state)) detail.state = state;
  performance.mark(name, { detail });
  return name;
}
