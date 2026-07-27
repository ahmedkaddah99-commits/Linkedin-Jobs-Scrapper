import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const appShellSource = readFileSync(new URL("../components/AppShell.jsx", import.meta.url), "utf8");
const appSource = readFileSync(new URL("../App.jsx", import.meta.url), "utf8");
const documentsSource = readFileSync(new URL("../pages/ArtifactsPage.jsx", import.meta.url), "utf8");

test("Career Assets navigation opens the canonical guided flow", () => {
  assert.match(appShellSource, /label: "Career Assets",[\s\S]*?to: "\/career-evidence"/);
});

test("Career Assets exposes its three main sections on every section page", () => {
  assert.match(appShellSource, /aria-label="Career Assets sections"/);
  assert.match(appShellSource, /label: "Asset Library",[\s\S]*?to: "\/documents"/);
  assert.match(appShellSource, /label: "Career Evidence",[\s\S]*?to: "\/career-evidence"/);
  assert.match(appShellSource, /label: "CV Studio",[\s\S]*?to: "\/cv-studio"/);
});

test("legacy Career Memory routes redirect to the canonical flow", () => {
  assert.match(appSource, /path="\/career-memory"[^>]*<Navigate replace to="\/career-evidence"/);
  assert.match(appSource, /path="\/career-memory\/guide"[^>]*<Navigate replace to="\/career-evidence"/);
});

test("legacy documents memory query redirects without assigning window.location", () => {
  assert.match(documentsSource, /return <Navigate replace to="\/career-evidence"/);
  assert.doesNotMatch(documentsSource, /window\.location\.href\s*=\s*"\/career-evidence"/);
});
