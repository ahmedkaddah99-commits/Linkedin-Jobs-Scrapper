import { createHash } from "node:crypto";
import { readFile, readdir } from "node:fs/promises";
import { join, resolve } from "node:path";

const targetBrowser = process.argv[2] || "chrome";
const outputDirectory = resolve(`.output/${targetBrowser}-mv3`);
const manifest = JSON.parse(await readFile(join(outputDirectory, "manifest.json"), "utf8"));
const packageMetadata = JSON.parse(await readFile(resolve("package.json"), "utf8"));
const reservedExtensionId = "najcdfohhfgbjpbokhmmekkahghfhegp";
const expectedOptionalHostPermissions = [
  "https://*.lever.co/*",
  "https://boards.greenhouse.io/*",
];

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

assert(manifest.manifest_version === 3, "Expected a Manifest V3 build.");
assert(typeof manifest.background?.service_worker === "string", "Expected an MV3 service worker.");
assert(manifest.side_panel?.default_path === "sidepanel.html", "Expected the Runr side panel entrypoint.");
assert(manifest.action, "Expected an explicit toolbar action.");
assert(
  manifest.version === packageMetadata.version,
  `Expected manifest version ${packageMetadata.version}, received ${manifest.version}.`,
);

if (targetBrowser === "chrome") {
  const publicKeyBytes = Buffer.from(String(manifest.key || ""), "base64");
  const publicKeyDigest = createHash("sha256").update(publicKeyBytes).digest().subarray(0, 16);
  const derivedExtensionId = Array.from(publicKeyDigest)
    .flatMap((byte) => [byte >> 4, byte & 0x0f])
    .map((nibble) => String.fromCharCode("a".charCodeAt(0) + nibble))
    .join("");
  assert(
    derivedExtensionId === reservedExtensionId,
    `Manifest public key resolves to ${derivedExtensionId}, expected ${reservedExtensionId}.`,
  );
  assert(
    manifest.minimum_chrome_version === "116",
    "Expected minimum_chrome_version: 116 for Chrome builds.",
  );
} else if (targetBrowser === "edge") {
  assert(!manifest.key, "Edge build must not include the Chrome key field.");
  assert(
    manifest.minimum_edge_version === "120",
    "Expected minimum_edge_version: 120 for Edge builds.",
  );
} else {
  throw new Error(`Unsupported manifest verification target: ${targetBrowser}`);
}

const expectedIcons = {
  16: "icons/runr-16.png",
  32: "icons/runr-32.png",
  48: "icons/runr-48.png",
  128: "icons/runr-128.png",
};
for (const [size, iconPath] of Object.entries(expectedIcons)) {
  assert(manifest.icons?.[size] === iconPath, `Missing manifest icon ${size}: ${iconPath}`);
  assert(manifest.action?.default_icon?.[size] === iconPath, `Missing action icon ${size}: ${iconPath}`);
  const bytes = await readFile(join(outputDirectory, iconPath));
  assert(
    bytes.subarray(0, 8).equals(Buffer.from([137, 80, 78, 71, 13, 10, 26, 10])),
    `Expected a PNG icon: ${iconPath}`,
  );
  assert(bytes.readUInt32BE(16) === Number(size), `Wrong PNG width for ${iconPath}`);
  assert(bytes.readUInt32BE(20) === Number(size), `Wrong PNG height for ${iconPath}`);
}

const permissions = new Set(manifest.permissions || []);
for (const permission of ["activeTab", "identity", "scripting", "sidePanel", "storage"]) {
  assert(permissions.has(permission), `Missing required permission: ${permission}`);
}
for (const permission of permissions) {
  assert(
    ["activeTab", "identity", "scripting", "sidePanel", "storage"].includes(permission),
    `Unexpected production permission: ${permission}`,
  );
}

assert(
  JSON.stringify(manifest.host_permissions || []) ===
    JSON.stringify(["https://runr-api.onrender.com/*", "https://www.linkedin.com/*"]),
  "Production host access must be limited to the first-party Runr API and LinkedIn connections origins.",
);
assert(
  JSON.stringify([...(manifest.optional_host_permissions || [])].sort()) ===
    JSON.stringify([...expectedOptionalHostPermissions].sort()),
  "Production optional host permissions must be the declared portal patterns for Greenhouse and Lever.",
);
assert(!manifest.content_scripts?.length, "Page code must be injected after a user action.");
assert(
  JSON.stringify(manifest.externally_connectable) ===
    JSON.stringify({ matches: ["https://app.userunr.com/*"] }),
  "External messaging must be limited to the first-party Runr web origin.",
);

const sourceRoots = [
  resolve("entrypoints"),
  resolve("src"),
  resolve("../../packages/ats-core/src"),
  resolve("../../packages/extension-messages/src"),
];
const files = [];
async function collect(directory) {
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    const path = join(directory, entry.name);
    if (entry.isDirectory()) await collect(path);
    else if (/\.(ts|tsx|js|jsx)$/.test(entry.name)) files.push(path);
  }
}
for (const root of sourceRoots) await collect(root);

for (const file of files) {
  const source = await readFile(file, "utf8");
  assert(!/\beval\s*\(/.test(source), `Remote-code guard: eval found in ${file}`);
  assert(!/new\s+Function\s*\(/.test(source), `Remote-code guard: Function constructor found in ${file}`);
  assert(!/import\s*\(\s*["']https?:/.test(source), `Remote-code guard: URL import found in ${file}`);
  assert(!/\.(?:submit|requestSubmit)\s*\(/.test(source), `Submission guard: DOM API found in ${file}`);
  assert(
    !/\b[\w$]*(?:submit|Submit)[\w$]*\s*\(/.test(source),
    `Submission guard: submit-like capability found in ${file}`,
  );
}

const productionBundles = [];
async function collectProductionBundles(directory) {
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    const path = join(directory, entry.name);
    if (entry.isDirectory()) await collectProductionBundles(path);
    else if (entry.name.endsWith(".js")) productionBundles.push(path);
  }
}
await collectProductionBundles(outputDirectory);
for (const file of productionBundles) {
  const source = await readFile(file, "utf8");
  assert(
    !source.includes("candidate@example.com") &&
      !source.includes("CONTENT_RUN_GREENHOUSE_FIXTURE_PROOF"),
    `Production bundle contains fixture execution code: ${file}`,
  );
  if (file.endsWith("application-form.js") || file.endsWith("background.js")) {
    assert(
      !/\.(?:submit|requestSubmit)\s*\(/.test(source),
      `Privileged production bundle contains a DOM submission API: ${file}`,
    );
  }
  if (!file.endsWith("background.js")) {
    for (const secretMarker of ["session_token", "sessionToken", "code_verifier", "codeVerifier"]) {
      assert(
        !source.includes(secretMarker),
        `Extension secret boundary: ${secretMarker} escaped the service-worker bundle in ${file}`,
      );
    }
  }
}

console.log(`Verified guarded ${targetBrowser === "chrome" ? "Chrome" : "Edge"} MV3 manifest and source boundary.`);
