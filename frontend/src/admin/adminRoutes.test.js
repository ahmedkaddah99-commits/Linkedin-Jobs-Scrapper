import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import test from "node:test";

import { ADMIN_NAV_GROUPS, compatibilityTarget, getAdminPageMeta, preserveSafeQuery } from "./adminRoutes.js";

const canonicalRoutes = [
  "/admin", "/admin/analytics", "/admin/acquisition/sources", "/admin/acquisition/imports",
  "/admin/acquisition/jobs", "/admin/acquisition/companies", "/admin/acquisition/enrichment",
  "/admin/acquisition/data-quality", "/admin/acquisition/rules", "/admin/acquisition/reprocessing",
  "/admin/acquisition/duplicates", "/admin/acquisition/publication", "/admin/acquisition/live-catalog",
  "/admin/acquisition/audit", "/admin/system", "/admin/provider-policy", "/admin/events",
  "/admin/promotions", "/admin/access",
];

test("admin navigation exposes the canonical grouped information architecture", () => {
  assert.deepEqual(ADMIN_NAV_GROUPS.map((group) => group.label), ["Command center", "Acquisition", "Quality", "Release", "Platform"]);
  assert.deepEqual(ADMIN_NAV_GROUPS.flatMap((group) => group.items.map((item) => item.to)), canonicalRoutes);
});

test("legacy entry points redirect to canonical routes with only safe query state", () => {
  assert.equal(compatibilityTarget("/admin/acquisition", "?ignored=1"), "/admin");
  assert.equal(compatibilityTarget("/admin/acquisition/analytics", "?range=30d&timezone=Europe%2FBerlin&secret=no"), "/admin/analytics?range=30d&timezone=Europe%2FBerlin");
  assert.equal(compatibilityTarget("/admin/job-import", "?canonical_job_id=job%2F42&source_id=greenhouse&token=no"), "/admin/acquisition/jobs/job%2F42");
  assert.equal(compatibilityTarget("/admin/scrapeops", "?workspace_id=w1&date=2026-08-12&write=true"), "/admin/provider-policy?workspace_id=w1&date=2026-08-12");
  assert.equal(preserveSafeQuery("?range=7d&token=secret", ["range"]), "?range=7d");
});

test("deep links resolve to useful breadcrumbs and unknown admin URLs stay inside the shell", () => {
  assert.deepEqual(getAdminPageMeta("/admin/acquisition/jobs/job-123"), { group: "Acquisition", title: "Jobs detail" });
  assert.deepEqual(getAdminPageMeta("/admin/not-real"), { group: "Admin", title: "Page not found" });
});

test("one admin shell owns all canonical and compatibility routes", () => {
  const router = readFileSync(new URL("./AdminOperationsRouter.jsx", import.meta.url), "utf8");
  const app = readFileSync(new URL("../App.jsx", import.meta.url), "utf8");
  const events = readFileSync(new URL("../pages/AdminEventsPage.jsx", import.meta.url), "utf8");
  canonicalRoutes.forEach((route) => assert.ok(router.includes(`path="${route}"`), `missing ${route}`));
  assert.match(router, /<AdminOperationsShell>/);
  assert.doesNotMatch(app, /<AppShell[^>]*>[\s\S]*<AdminOperationsRouter/);
  assert.match(events, /General admin events — acquisition scope may be incomplete/);
  assert.equal(existsSync(new URL("../components/acquisition/AcquisitionShell.jsx", import.meta.url)), false);
  assert.equal(existsSync(new URL("../adminInspectorV3.css", import.meta.url)), false);
  assert.equal(existsSync(new URL("../pages/AdminJobImportPage.jsx", import.meta.url)), false);
});

test("the new shell has keyboard, focus, responsive, and connection-state contracts", () => {
  const shell = readFileSync(new URL("../components/admin/AdminOperationsShell.jsx", import.meta.url), "utf8");
  const primitives = readFileSync(new URL("../components/admin/AdminPrimitives.jsx", import.meta.url), "utf8");
  const styles = readFileSync(new URL("./adminOperations.css", import.meta.url), "utf8");
  assert.match(shell, /event\.ctrlKey \|\| event\.metaKey/);
  assert.match(shell, /Admin data may be stale/);
  assert.match(shell, /External providers, AI, and paid calls remain policy-controlled/);
  assert.match(primitives, /event\.key === "Escape"/);
  assert.match(primitives, /returnFocusRef\.current/);
  assert.match(styles, /@media\(max-width:820px\)/);
  assert.match(styles, /prefers-reduced-motion/);
  const providerPage = readFileSync(new URL("../pages/AdminScrapeOpsPage.jsx", import.meta.url), "utf8");
  assert.match(providerPage, /if \(!telemetryRequested\) return "\/admin\/scrapeops\/policy"/);
  assert.match(providerPage, /Load provider telemetry/);
  const router = readFileSync(new URL("./AdminOperationsRouter.jsx", import.meta.url), "utf8");
  assert.match(router, /<AdminPage deferExternalLoad initialTab="promoCodes"/);
});
