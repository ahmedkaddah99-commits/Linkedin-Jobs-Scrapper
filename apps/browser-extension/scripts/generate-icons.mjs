import { mkdir } from "node:fs/promises";
import { resolve } from "node:path";
import { chromium } from "playwright";

const outputDirectory = resolve("public/icons");
const sizes = [16, 32, 48, 128];

function iconSvg(size) {
  const storePadding = size === 128 ? 16 : 0;
  const markSize = 128 - storePadding * 2;
  const scale = markSize / 128;
  const offset = storePadding;
  const value = (coordinate) => offset + coordinate * scale;

  const background = {
    x: offset,
    y: offset,
    width: markSize,
    height: markSize,
    radius: 30 * scale,
  };
  const bars = [
    { x: 24, y: 28, width: 80 },
    { x: 42, y: 56, width: 62 },
    { x: 24, y: 84, width: 48 },
  ];

  return `
    <svg xmlns="http://www.w3.org/2000/svg" width="${size}" height="${size}" viewBox="0 0 128 128">
      <rect x="${background.x}" y="${background.y}" width="${background.width}" height="${background.height}" rx="${background.radius}" fill="#eaf1ff" />
      ${bars
        .map(
          (bar) =>
            `<rect x="${value(bar.x)}" y="${value(bar.y)}" width="${bar.width * scale}" height="${16 * scale}" rx="${8 * scale}" fill="#245ee8" />`,
        )
        .join("\n")}
    </svg>
  `;
}

await mkdir(outputDirectory, { recursive: true });
const browser = await chromium.launch({ headless: true });
try {
  for (const size of sizes) {
    const page = await browser.newPage({ viewport: { width: size, height: size } });
    await page.setContent(
      `<style>html,body{margin:0;background:transparent;overflow:hidden}</style>${iconSvg(size)}`,
    );
    await page.screenshot({
      path: resolve(outputDirectory, `runr-${size}.png`),
      omitBackground: true,
    });
    await page.close();
  }
} finally {
  await browser.close();
}

console.log(`Generated ${sizes.length} Runr extension icons in ${outputDirectory}.`);
