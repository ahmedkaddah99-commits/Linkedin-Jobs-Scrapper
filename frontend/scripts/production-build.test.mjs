import assert from "node:assert/strict";
import { readFile, readdir } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");

test("production build embeds the real Jobs mode and retired legacy navigation", async () => {
  const config = JSON.parse(await readFile(path.join(root, "dist", "runr-build-config.json"), "utf8"));
  assert.deepEqual(config, { jobs: { dataMode: "real", replaceLegacyJobsNav: true } });

  const assetNames = await readdir(path.join(root, "dist", "assets"));
  const assetText = (await Promise.all(assetNames.map((name) => readFile(path.join(root, "dist", "assets", name), "utf8")))).join("\n");
  assert.match(assetText, /runr-build-config|real/);
  assert.match(assetText, /Workspaces|Runs/);
});
