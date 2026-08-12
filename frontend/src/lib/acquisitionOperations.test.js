import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import {
  ACQUISITION_GET_ENDPOINTS,
  buildInspectionPath,
  buildJobsPath,
  getResourceViewState,
  getSourceCollectionState,
  getSourceOperationalState,
  parseJobFilters,
} from "./acquisitionOperations.js";

test("acquisition routes use the verified read-only endpoint set", () => {
  assert.deepEqual(ACQUISITION_GET_ENDPOINTS, [
    "/admin/acquisition/overview",
    "/admin/acquisition/sources",
    "/admin/acquisition/jobs",
    "/admin/acquisition/connectors/capabilities",
  ]);
});

test("App keeps the new acquisition routes and legacy admin routes", () => {
  const appSource = readFileSync(new URL("../App.jsx", import.meta.url), "utf8");

  assert.match(appSource, /path=\"\/admin\/acquisition\"/);
  assert.match(appSource, /path=\"\/admin\/acquisition\/sources\"/);
  assert.match(appSource, /path=\"\/admin\/acquisition\/jobs\"/);
  assert.match(appSource, /path=\"\/admin\/acquisition\/jobs\/:canonicalJobId\"/);
  assert.match(appSource, /path=\"\/admin\/job-import\"/);
  assert.match(appSource, /path=\"\/admin\/scrapeops\"/);
  assert.match(appSource, /path=\"\/admin\/events\"/);
});

test("job filters are parsed and rebuilt as URL-backed pagination", () => {
  const filters = parseJobFilters("?search=data%20engineer&function=engineering&limit=50&offset=100");

  assert.equal(filters.search, "data engineer");
  assert.equal(filters.function, "engineering");
  assert.equal(filters.limit, 50);
  assert.equal(filters.offset, 100);
  assert.equal(
    buildJobsPath(filters),
    "/admin/acquisition/jobs?search=data+engineer&function=engineering&limit=50&offset=100",
  );
});

test("inspection paths preserve the current job filters", () => {
  assert.equal(
    buildInspectionPath("job/42", "?function=engineering&limit=25&offset=25"),
    "/admin/acquisition/jobs/job%2F42?function=engineering&limit=25&offset=25",
  );
});

test("job paths omit the backend source filter until its query contract is fixed", () => {
  assert.doesNotMatch(
    buildJobsPath({ search: "personio", source: "personio", limit: 25, offset: 0 }),
    /source=/,
  );
});

test("resource states distinguish loading, errors, empty, partial and unavailable data", () => {
  assert.equal(getResourceViewState({ loading: true }), "loading");
  assert.equal(getResourceViewState({ error: "offline" }), "error");
  assert.equal(getResourceViewState({ data: {}, empty: true }), "empty");
  assert.equal(getResourceViewState({ data: {}, error: "refresh failed" }), "partial");
  assert.equal(getResourceViewState({ unavailable: true }), "unavailable");
});

test("source labels are derived from backend status and limits, not connector names", () => {
  assert.equal(getSourceOperationalState({ status: "ready" }), "Ready");
  assert.equal(getSourceOperationalState({ status: "source_paused" }), "Paused");
  assert.equal(getSourceOperationalState({ status: "disabled" }), "Unavailable");
  assert.equal(
    getSourceCollectionState({ max_pages: 1 }, {}),
    "Bounded collection",
  );
  assert.equal(
    getSourceCollectionState({ status: "ready" }, {}),
    "Completeness unavailable",
  );
});

test("the first-pr frontend page contains no mutation request or unsupported action controls", () => {
  const pageSource = readFileSync(new URL("../pages/AcquisitionOperationsPage.jsx", import.meta.url), "utf8");

  assert.doesNotMatch(pageSource, /method:\s*["'](?:POST|PUT|PATCH|DELETE)["']/i);
  assert.doesNotMatch(pageSource, /Queue import|Import jobs|Enrich|Publish preview|Undo last publication|Confirm duplicate|Select all matching/i);
  assert.match(pageSource, /read-only/i);
});
