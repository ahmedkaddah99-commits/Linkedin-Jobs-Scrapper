import { createHash } from "node:crypto";
import { readFile, readdir } from "node:fs/promises";
import { join, resolve } from "node:path";

const outputDirectory = resolve(".output/chrome-mv3");
const manifest = JSON.parse(await readFile(join(outputDirectory, "manifest.json"), "utf8"));
const reservedExtensionId = "najcdfohhfgbjpbokhmmekkahghfhegp";

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

assert(manifest.manifest_version === 3, "Expected a Manifest V3 build.");
assert(typeof manifest.background?.service_worker === "string", "Expected an MV3 service worker.");
assert(manifest.side_panel?.default_path === "sidepanel.html", "Expected the Runr side panel entrypoint.");
assert(manifest.action, "Expected an explicit toolbar action.");

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

const expectedIcons = {
  16: "icons/runr-16.png",
  32: "icons/runr-32.png",
  48: "icons/runr-48.png",
  128: "icons/runr-128.png",
};
for (const [size, path] of Object.entries(expectedIcons)) {
  assert(manifest.icons?.[size] === path, `Missing manifest icon ${size}: ${path}`);
  assert(manifest.action?.default_icon?.[size] === path, `Missing action icon ${size}: ${path}`);
  const bytes = await readFile(join(outputDirectory, path));
  assert(
    bytes.subarray(0, 8).equals(Buffer.from([137, 80, 78, 71, 13, 10, 26, 10])),
    `Expected a PNG icon: ${path}`,
  );
  assert(bytes.readUInt32BE(16) === Number(size), `Wrong PNG width for ${path}`);
  assert(bytes.readUInt32BE(20) === Number(size), `Wrong PNG height for ${path}`);
}

const permissions = new Set(manifest.permissions || []);
for (const permission of ["activeTab", "identity", "scripting", "storage", "sidePanel"]) {
  assert(permissions.has(permission), `Missing required permission: ${permission}`);
}
for (const permission of permissions) {
  assert(
    ["activeTab", "identity", "scripting", "storage", "sidePanel"].includes(permission),
    `Unexpected production permission: ${permission}`,
  );
}

assert(
  !manifest.optional_host_permissions?.length,
  "Assisted Apply must not request unused optional host permissions.",
);
assert(
  JSON.stringify(manifest.host_permissions || []) ===
    JSON.stringify(["https://runr-api.onrender.com/*"]),
  "Production host access must be limited to the first-party Runr API origin.",
);
assert(!manifest.content_scripts?.length, "AA-01 page code must be injected after a user action.");
assert(!manifest.externally_connectable, "AA-01 must not expose external extension messaging.");

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
  assert(
    !/\.(?:submit|requestSubmit)\s*\(/.test(source),
    `Submission guard: DOM submission API found in ${file}`,
  );
  assert(
    !/\b[\w$]*(?:submit|Submit)[\w$]*\s*\(/.test(source),
    `Submission guard: submit-like callable capability found in ${file}`,
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
    `Production bundle contains AA-01 fixture execution code: ${file}`,
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

console.log("Verified guarded Chrome MV3 manifest and source boundary.");
