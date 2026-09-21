import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const extensionRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const repoRoot = path.resolve(extensionRoot, "../..");

const scanRoots = [
  ["apps/browser-extension/entrypoints/**", path.join(extensionRoot, "entrypoints")],
  ["apps/browser-extension/src/**", path.join(extensionRoot, "src")],
  ["packages/ats-core/src/**", path.resolve(extensionRoot, "../../packages/ats-core/src")],
];

const forbidden = [
  { pattern: /(?:adapter|greenhouse|lever)\.fill\s*\(/u, kind: "adapter fill bypass (AA-P03)" },
  { pattern: /\.click\s*\(/u, kind: "programmatic control click" },
  { pattern: /\.requestSubmit\s*\(/u, kind: "form.requestSubmit call" },
  { pattern: /\.submit\s*\(/u, kind: "form submit call" },
  { pattern: /(?:window|document|globalThis|self|top|parent|frames)\.location\s*=[^=]/u, kind: "location assignment" },
  { pattern: /(?:window|document|globalThis|self|top|parent|frames)\.location\.(?:href\s*=[^=]|assign\s*\(|replace\s*\(|reload\s*\()/u, kind: "location navigation mutation" },
  { pattern: /(?:^|[;({]\s*)location\s*(?:\.\s*href)?\s*=[^=]/u, kind: "bare location assignment" },
  { pattern: /(?:^|[;({]\s*)location\s*\.\s*(?:assign|replace|reload)\s*\(/u, kind: "bare location navigation mutation" },
  { pattern: /(?:keydown|keyCode|which)\s*[:=].*Enter/iu, kind: "Enter-key submission path" },
  { pattern: /\bkey\s*(?:===|==)\s*["'`]Enter["'`]/u, kind: "Enter-key submission path" },
  { pattern: /dispatchEvent\s*\(\s*new\s+(?:window\.)?(?:MouseEvent|PointerEvent|TouchEvent)\b/u, kind: "synthetic pointer activation" },
  { pattern: /dispatchEvent\s*\(\s*new\s+(?:window\.)?KeyboardEvent\b/u, kind: "synthetic keyboard activation" },
  { pattern: /dispatchEvent\s*\(\s*new\s+(?:window\.)?Event\s*\(\s*["'`]submit["'`]/u, kind: "synthetic submit event dispatch" },
  { pattern: /dispatchEvent\s*\(\s*new\s+(?:PopStateEvent|HashChangeEvent|BeforeUnloadEvent)/u, kind: "history navigation event dispatch" },
];

const exemptFiles = new Set(["packages/ats-core/src/submission-guard.ts"]);

const classifiedAllowances = [
  {
    file: "packages/ats-core/src/declarative-actions.ts",
    allow: [/\boption\.click\s*\(\s*\)/u],
    reason: "AA-216 combobox option value interaction; terminal controls are refused by executeNativeValueAction.",
  },
  {
    file: "apps/browser-extension/entrypoints/sidepanel/App.tsx",
    allow: [
      /(?:keydown|keyCode|which)\s*[:=].*Enter/iu,
      /\bkey\s*(?:===|==)\s*["'`]Enter["'`]/u,
    ],
    reason: "Extension-own side panel keyboard accessibility for document upload and review state; never a page-form activation.",
  },
];

function withGlobalFlags(pattern) {
  return new RegExp(pattern.source, pattern.flags.includes("g") ? pattern.flags : `${pattern.flags}g`);
}

function forbiddenMatches(line, relativeFile) {
  const allowances = classifiedAllowances
    .filter((entry) => entry.file === relativeFile)
    .flatMap((entry) => entry.allow.map(withGlobalFlags));
  const covered = [];
  for (const allowed of allowances) {
    for (const match of line.matchAll(allowed)) {
      covered.push([match.index, match.index + match[0].length]);
    }
  }
  const hits = [];
  for (const { pattern, kind } of forbidden) {
    for (const match of line.matchAll(withGlobalFlags(pattern))) {
      const start = match.index;
      const end = start + match[0].length;
      if (!covered.some(([from, to]) => start >= from && end <= to)) hits.push(`${kind} (${pattern})`);
    }
  }
  return hits;
}

function collectSources(root) {
  const files = [];
  const walk = (dir) => {
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      if (entry.isDirectory()) walk(path.join(dir, entry.name));
      else if (entry.isFile() && /\.tsx?$/u.test(entry.name)) files.push(path.join(dir, entry.name));
    }
  };
  if (fs.existsSync(root)) walk(root);
  return files;
}

const violations = [];
for (const [label, root] of scanRoots) {
  for (const file of collectSources(root)) {
    const relative = path.relative(repoRoot, file).split(path.sep).join("/");
    if (exemptFiles.has(relative)) continue;
    const lines = fs.readFileSync(file, "utf8").split(/\r?\n/u);
    for (let index = 0; index < lines.length; index += 1) {
      for (const kind of forbiddenMatches(lines[index], relative)) {
        violations.push(`${relative}:${index + 1}: ${kind}`);
      }
    }
  }
}

if (violations.length) {
  console.error(
    "Assisted Apply never-submit boundary violations:\n" + violations.join("\n") +
    "\nTerminal DOM submission and unreviewed synthetic control activation are prohibited." +
    "\nNon-terminal value or option interactions require an explicit classification in this script.",
  );
  process.exit(1);
}
console.log(
  "Verified never-submit boundary across apps/browser-extension/entrypoints/**, apps/browser-extension/src/**, and packages/ats-core/src/**:" +
  " no terminal DOM submission APIs and no unreviewed synthetic control activation;" +
  " classified non-terminal value and option interactions remain allowed.",
);
