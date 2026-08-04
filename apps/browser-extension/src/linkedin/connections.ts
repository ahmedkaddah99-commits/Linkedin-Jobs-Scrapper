export interface LinkedInConnectionRow {
  firstName: string;
  lastName: string;
  profileUrl: string;
  email: string;
  company: string;
  position: string;
  connectedOn: string;
}

export interface LinkedInConnectionsSnapshot {
  sourceUrl: string;
  extractedAt: string;
  rows: LinkedInConnectionRow[];
}

const PROFILE_PATH_PATTERN = /^\/in\/[^/]+/iu;
const CARD_SELECTORS = [
  "li.mn-connection-card",
  "[class*='mn-connection-card' i]",
  "li[data-view-name*='connection' i]",
  "[data-view-name*='connection-card' i]",
  "main [role='listitem']",
  "main li",
  "main article",
];

function textFrom(element: Element | null | undefined): string {
  return String(element?.textContent || "").replace(/\s+/gu, " ").trim();
}

function profileUrlFrom(element: Element, origin: string): string {
  const raw = element.getAttribute("href") || "";
  try {
    const parsed = new URL(raw, origin || "https://www.linkedin.com");
    if (
      parsed.hostname !== "linkedin.com" &&
      !parsed.hostname.endsWith(".linkedin.com") ||
      !PROFILE_PATH_PATTERN.test(parsed.pathname)
    ) {
      return "";
    }
    parsed.search = "";
    parsed.hash = "";
    return parsed.toString();
  } catch {
    return "";
  }
}

function splitName(value: string): { firstName: string; lastName: string } {
  const parts = value.trim().split(/\s+/u).filter(Boolean);
  return {
    firstName: parts.shift() || "",
    lastName: parts.join(" "),
  };
}

function splitOccupation(value: string): { company: string; position: string } {
  const normalized = value.replace(/\s+/gu, " ").trim();
  const atMatch = normalized.match(/^(.+?)\s+(?:at|@)\s+(.+)$/iu);
  if (atMatch) {
    return { position: (atMatch[1] || "").trim(), company: (atMatch[2] || "").trim() };
  }
  return { company: "", position: normalized };
}

function textLinesFrom(element: Element): string[] {
  return String(element.textContent || "")
    .split(/\r?\n/gu)
    .map((line) => line.replace(/\s+/gu, " ").trim())
    .filter(Boolean);
}

function connectedDateFromLines(lines: string[]): string {
  return lines.find((line) => /\bconnected\s+on\b/iu.test(line))?.replace(/^.*?\bconnected\s+on\s*/iu, "").trim() || "";
}

function connectionFromCard(card: Element, origin: string): LinkedInConnectionRow | null {
  const profileAnchors = [...card.querySelectorAll("a[href]")]
    .map((anchor) => ({ anchor, url: profileUrlFrom(anchor, origin) }))
    .filter((entry) => entry.url);
  const profileAnchor = profileAnchors.find((entry) => textFrom(entry.anchor)) || profileAnchors[0];
  if (!profileAnchor) return null;

  const name = textFrom(
    card.querySelector(
      ".mn-connection-card__name, [data-view-name='connection-card-name'], .t-16, h3, h2",
    ),
  ) || textFrom(profileAnchor.anchor);
  if (!name) return null;

  const occupation = textFrom(
    card.querySelector(
      ".mn-connection-card__occupation, [data-view-name='connection-card-occupation'], .t-14",
    ),
  ) || textLinesFrom(card).find((line) => line !== name && !/\bconnected\s+on\b/iu.test(line)) || "";
  const connectedOn = textFrom(
    card.querySelector("time, .mn-connection-card__connection-date, [data-view-name*='connected' i]"),
  ) || connectedDateFromLines(textLinesFrom(card));
  const { firstName, lastName } = splitName(name);
  const { company, position } = splitOccupation(occupation);
  return {
    firstName,
    lastName,
    profileUrl: profileAnchor.url,
    email: "",
    company,
    position,
    connectedOn,
  };
}

export function extractLinkedInConnections(
  documentRef: Document,
  sourceUrl = documentRef.location?.href || "",
): LinkedInConnectionsSnapshot {
  const origin = documentRef.location?.origin || "https://www.linkedin.com";
  const cards = new Set<Element>();
  for (const selector of CARD_SELECTORS) {
    documentRef.querySelectorAll(selector).forEach((card) => cards.add(card));
  }
  documentRef.querySelectorAll("main a[href*='/in/']").forEach((anchor) => {
    const card = anchor.closest("li, article, [role='listitem'], [class*='connection-card' i]") || anchor.parentElement;
    if (card) cards.add(card);
  });

  const rows: LinkedInConnectionRow[] = [];
  const seen = new Set<string>();
  cards.forEach((card) => {
    const row = connectionFromCard(card, origin);
    if (!row || seen.has(row.profileUrl)) return;
    seen.add(row.profileUrl);
    rows.push(row);
  });
  return {
    sourceUrl,
    extractedAt: new Date().toISOString(),
    rows: rows.slice(0, 10000),
  };
}

function escapeCsv(value: string): string {
  const normalized = String(value || "");
  return /[",\r\n]/u.test(normalized) ? `"${normalized.replace(/"/gu, '""')}"` : normalized;
}

export function linkedInConnectionsCsv(rows: LinkedInConnectionRow[]): string {
  const header = "First Name,Last Name,URL,Email Address,Company,Position,Connected On";
  const body = rows.map((row) => [
    row.firstName,
    row.lastName,
    row.profileUrl,
    row.email,
    row.company,
    row.position,
    row.connectedOn,
  ].map(escapeCsv).join(","));
  return [header, ...body].join("\n");
}
