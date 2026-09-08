import assert from "node:assert/strict";
import test from "node:test";

import {
  currentEntryAssetPath,
  entryAssetPathFromUrl,
  extractEntryAssetPathFromHtml,
  fetchLatestEntryAssetPath,
} from "./deployVersion.js";

test("extracts Vite entry asset paths from HTML without following lazy chunks", () => {
  assert.equal(
    extractEntryAssetPathFromHtml(`
      <script type="module" crossorigin src="/assets/index-DaE3d8PR.js"></script>
      <script type="module" src="/assets/TrackerPage-BffxFgLA.js"></script>
    `),
    "/assets/index-DaE3d8PR.js",
  );
});

test("normalizes absolute and relative entry script URLs", () => {
  assert.equal(
    entryAssetPathFromUrl("assets/index-DOe2Ci7g.js", "https://app.userunr.com/documents"),
    "/assets/index-DOe2Ci7g.js",
  );
  assert.equal(
    entryAssetPathFromUrl("https://app.userunr.com/assets/index-DOe2Ci7g.js?cache=1"),
    "/assets/index-DOe2Ci7g.js",
  );
  assert.equal(entryAssetPathFromUrl("/assets/TrackerPage-BffxFgLA.js"), "");
});

test("reads the current entry script from a minimal document object", () => {
  const documentRef = {
    location: { href: "https://app.userunr.com/" },
    querySelectorAll() {
      return [
        { getAttribute: () => "/assets/TrackerPage-BffxFgLA.js" },
        { getAttribute: () => "/assets/index-DaE3d8PR.js" },
      ];
    },
  };

  assert.equal(currentEntryAssetPath(documentRef), "/assets/index-DaE3d8PR.js");
});

test("fetches the latest entry script using a cache-busting index request", async () => {
  const requested = [];
  const entryPath = await fetchLatestEntryAssetPath({
    baseUrl: "https://app.userunr.com/tracker",
    fetchImpl: async (url, options) => {
      requested.push({ url, options });
      return {
        ok: true,
        async text() {
          return '<script type="module" src="/assets/index-NewBuild.js"></script>';
        },
      };
    },
    now: () => 123,
  });

  assert.equal(entryPath, "/assets/index-NewBuild.js");
  assert.equal(requested[0].url, "https://app.userunr.com/?__runr_version_check=123");
  assert.equal(requested[0].options.cache, "no-store");
});
