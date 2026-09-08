import path from "node:path";
import { fileURLToPath } from "node:url";
import { defineConfig } from "vitest/config";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

// Use vitest's functional config form to support async plugin setup.
export default defineConfig(async () => {
  const { WxtVitest } = await import("wxt/testing/vitest-plugin");
  const plugins = await WxtVitest();

  // On Windows + Node 24, WxtVitest's virtual setup module resolves
  // wxt/testing/fake-browser to an absolute path missing the drive letter.
  if (process.platform === "win32") {
    const fakeBrowser = path.resolve(
      __dirname,
      "node_modules/wxt/dist/testing/fake-browser.mjs",
    );
    plugins.push({
      name: "wxt:windows-alias-fix",
      config: () => ({
        resolve: {
          alias: [{ find: "wxt/testing/fake-browser", replacement: fakeBrowser }],
        },
      }),
    });
  }

  return {
    plugins,
    test: {
      environment: "jsdom",
      include: ["tests/unit/**/*.test.ts"],
      restoreMocks: true,
      testTimeout: 30_000,
    },
  };
});
