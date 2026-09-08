import fs from "node:fs";
import path from "node:path";
import process from "node:process";
import { chromium } from "playwright";
import { buildCvStudioHtml, buildWorkspacePreviewState } from "../src/lib/cvStudio.js";

function parseArgs(argv) {
  const args = {};
  for (let index = 0; index < argv.length; index += 1) {
    const value = argv[index];
    if (value === "--output") {
      args.output = argv[index + 1] || "";
      index += 1;
    } else if (value === "--html-output") {
      args.htmlOutput = argv[index + 1] || "";
      index += 1;
    }
  }
  return args;
}

async function readStdin() {
  const chunks = [];
  for await (const chunk of process.stdin) {
    chunks.push(chunk);
  }
  return Buffer.concat(chunks).toString("utf8");
}

function imagePathToDataUrl(imagePath) {
  const normalizedPath = String(imagePath || "").trim();
  if (!normalizedPath || !fs.existsSync(normalizedPath)) return "";
  const extension = path.extname(normalizedPath).toLowerCase();
  const mimeType =
    extension === ".jpg" || extension === ".jpeg"
      ? "image/jpeg"
      : extension === ".png"
        ? "image/png"
        : "";
  if (!mimeType) return "";
  const data = fs.readFileSync(normalizedPath).toString("base64");
  return `data:${mimeType};base64,${data}`;
}

function findSystemBrowserExecutable() {
  const candidates = [
    process.env.CV_PDF_BROWSER_EXECUTABLE,
    process.env.CHROME_PATH,
    process.env.EDGE_PATH,
    "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
    "C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe",
    "C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe",
    "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe",
    "/usr/bin/google-chrome",
    "/usr/bin/google-chrome-stable",
    "/usr/bin/chromium",
    "/usr/bin/chromium-browser",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
  ].filter(Boolean);
  return candidates.find((candidate) => fs.existsSync(candidate)) || "";
}

async function launchBrowser() {
  try {
    return await chromium.launch({ headless: true });
  } catch (bundledError) {
    const executablePath = findSystemBrowserExecutable();
    if (executablePath) {
      return chromium.launch({ executablePath, headless: true });
    }
    throw new Error(
      [
        "Unable to launch Chromium for CV PDF export.",
        "Install the browser runtime with: npm --prefix frontend exec playwright install chromium",
        `Original error: ${bundledError.message}`,
      ].join(" "),
    );
  }
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  if (!args.output) {
    throw new Error("Missing required --output path.");
  }

  const rawPayload = await readStdin();
  const payload = JSON.parse(rawPayload || "{}");
  const profile = { ...(payload.profile || {}) };
  if (!profile.photo_data_url && payload.photo_path) {
    profile.photo_data_url = imagePathToDataUrl(payload.photo_path);
  }
  const state =
    payload.state ||
    buildWorkspacePreviewState(profile, payload.documents || {}, payload.workspaceSettings || {});
  const html = buildCvStudioHtml(state, { forIframe: false });

  fs.mkdirSync(path.dirname(path.resolve(args.output)), { recursive: true });
  if (args.htmlOutput) {
    fs.mkdirSync(path.dirname(path.resolve(args.htmlOutput)), { recursive: true });
    fs.writeFileSync(args.htmlOutput, html, "utf8");
  }

  const browser = await launchBrowser();
  try {
    const page = await browser.newPage({ viewport: { width: 1240, height: 1754 } });
    await page.emulateMedia({ media: "print" });
    await page.setContent(html, { waitUntil: "networkidle" });
    await page.pdf({
      path: args.output,
      format: "A4",
      printBackground: true,
      preferCSSPageSize: true,
    });
  } finally {
    await browser.close();
  }
}

main().catch((error) => {
  console.error(error && error.stack ? error.stack : String(error));
  process.exit(1);
});
