import fs from "node:fs";
import path from "node:path";

const meaningful = (...values) => {
  for (const value of values) {
    const normalized = String(value || "").trim();
    if (normalized && !["unknown", "unset", "none"].includes(normalized.toLowerCase())) {
      return normalized;
    }
  }
  return "unknown";
};

const metadata = {
  schema_version: "runr.release.v1",
  service: "frontend",
  branch: meaningful(process.env.RUNR_RELEASE_BRANCH, process.env.RENDER_GIT_BRANCH),
  commit: meaningful(process.env.RUNR_RELEASE_COMMIT, process.env.RENDER_GIT_COMMIT),
  contract_version: meaningful(process.env.RUNR_RELEASE_CONTRACT_VERSION, "runr-contract-v1"),
  generated_at: new Date().toISOString(),
};

const publicDirectory = path.resolve(process.cwd(), "public");
fs.mkdirSync(publicDirectory, { recursive: true });
fs.writeFileSync(
  path.join(publicDirectory, "runr-release.json"),
  `${JSON.stringify(metadata, null, 2)}\n`,
  "utf8",
);
