import fs from "node:fs";
import path from "node:path";

const root = path.resolve("../../packages/ats-core/src");
const forbidden = [
  /(?:adapter|greenhouse|lever)\.fill\s*\(/u,
  /\.click\s*\(/u,
  /requestSubmit\s*\(/u,
  /\.submit\s*\(/u,
  /(?:window|document)\.location\s*(?:\.|=)/u,
  /(?:keydown|keyCode|which)\s*[:=].*Enter/iu,
  /dispatchEvent\s*\(\s*new\s+(?:PopStateEvent|HashChangeEvent|BeforeUnloadEvent)/u,
];
const approved = new Set(["page-bridge.ts", "declarative-actions.ts", "submission-guard.ts"]);
const violations = [];
for (const file of fs.readdirSync(root).filter((name) => name.endsWith(".ts") && !approved.has(name))) {
  const source = fs.readFileSync(path.join(root, file), "utf8");
  for (const pattern of forbidden) if (pattern.test(source)) violations.push(`${file}: ${pattern}`);
}
if (violations.length) {
  console.error("Assisted Apply boundary violations:\n" + violations.join("\n"));
  process.exit(1);
}
console.log("Verified adapter boundary: no direct clicks, submit APIs, navigation assignments, keyboard navigation, or navigation event dispatch.");
