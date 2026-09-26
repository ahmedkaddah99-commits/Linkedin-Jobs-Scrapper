import assert from "node:assert/strict";
import test from "node:test";
import { ROUTE_INVENTORY, markRoutePhase, routeForPath, routeReadyState, summarizeReadiness } from "./routePerformance.js";

test("critical route inventory uses only stable route names and redacts IDs", () => {
  assert.deepEqual(ROUTE_INVENTORY.map(({ name }) => name), [
    "home", "jobs", "job-detail", "tracker", "tracker-ats", "job-description",
    "documents", "document-edit", "career-evidence", "career-evidence-detail",
    "career-assets", "refer", "settings",
  ]);
  assert.equal(routeForPath("/jobs/private-job-123")?.name, "job-detail");
  assert.equal(routeForPath("/tracker/private-review/ats")?.name, "tracker-ats");
  assert.equal(routeForPath("/unknown"), null);
});

test("percentiles use only finite nonnegative readiness samples", () => {
  assert.deepEqual(summarizeReadiness([120, 140, 100, 180, 200, null, -1, Infinity]), {
    samples: 5, p50: 140, p75: 180, p95: 200,
  });
});

test("ready state requires an observed useful element rather than route mount", () => {
  const route = routeForPath("/documents");
  const absent = { querySelector: (selector) => selector === "main" ? { querySelector: () => null } : null };
  assert.equal(routeReadyState(route, absent), null);
  const loading = { querySelector: (selector) => selector === "main" ? {
    querySelector: (query) => query === route.useful ? { textContent: "Loading documents", matches: () => false } : null,
  } : null };
  assert.equal(routeReadyState(route, loading), null);
  const empty = { querySelector: (selector) => selector === "main" ? {
    querySelector: (query) => query === route.useful ? { textContent: "", matches: (match) => match.includes(".documents-empty-state") } : null,
  } : null };
  assert.equal(routeReadyState(route, empty), "empty");
});

test("privacy-safe marks reject arbitrary route names and phases", () => {
  const previous = globalThis.performance;
  const marks = [];
  globalThis.performance = { mark: (...args) => marks.push(args) };
  try {
    assert.equal(markRoutePhase("/jobs/private-id", "navigation"), null);
    assert.equal(markRoutePhase("jobs", "private-payload"), null);
    assert.equal(markRoutePhase("jobs", "useful-render", "cold", "content"), "runr-route:jobs:useful-render");
    assert.equal(marks.length, 1);
    assert.deepEqual(Object.keys(marks[0][1].detail).sort(), ["deviceClass", "mode", "phase", "revision", "route", "state"]);
  } finally {
    globalThis.performance = previous;
  }
});
