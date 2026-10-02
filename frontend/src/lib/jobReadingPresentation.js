export function formatPostingAge(value, now = Date.now()) {
  const timestamp = Date.parse(String(value || ""));
  if (!Number.isFinite(timestamp)) return "";
  const hours = Math.max(1, Math.floor(Math.max(0, now - timestamp) / 3600000));
  if (hours < 24) return `${hours} ${hours === 1 ? "hour" : "hours"} ago`;
  const days = Math.floor(hours / 24);
  return `${days} ${days === 1 ? "day" : "days"} ago`;
}

export function seniorityFromYears(minimum) {
  if (typeof minimum !== "number" || !Number.isFinite(minimum) || minimum < 0) return null;
  if (minimum < 3) return "Entry level";
  if (minimum < 6) return "Mid level";
  if (minimum < 10) return "Senior level";
  return "Lead level";
}

export function alternativeSeniority(requiredItems, sourcePassages) {
  if (!Array.isArray(requiredItems) || !Array.isArray(sourcePassages)) return null;
  const byId = new Map(sourcePassages.map((passage) => [passage.id, passage.text]));
  const order = ["Entry level", "Mid level", "Senior level", "Lead level"];
  const matches = [];
  for (const item of requiredItems) {
    for (const sourceId of item?.source_ids || []) {
      const source = byId.get(sourceId);
      if (typeof source !== "string") continue;
      const alternatives = source.split(/\bor\b/i);
      if (alternatives.length !== 2) continue;
      const levels = alternatives.map((part) => {
        if (!/\bexperience\b/i.test(part)) return null;
        const years = [...part.matchAll(/\b(\d+(?:\.\d+)?)(?:\s*[-–]\s*\d+(?:\.\d+)?)?\s*\+?\s*years?\b/gi)];
        return years.length === 1 ? seniorityFromYears(Number(years[0][1])) : null;
      });
      if (levels.every(Boolean)) matches.push(levels);
    }
  }
  if (matches.length !== 1) return null;
  const [first, second] = matches[0];
  const [lower, higher] = [first, second].sort((a, b) => order.indexOf(a) - order.indexOf(b));
  if (lower === higher) return higher;
  if (order.indexOf(higher) - order.indexOf(lower) > 1) return higher;
  return `${lower.replace(/ level$/, "")}, ${higher.replace(/ level$/, "")} Level`;
}

export function employmentTypeLabel(scraped, extracted, title = "") {
  const labels = {
    full_time: "Full-time", part_time: "Part-time", contract: "Contract",
    temporary: "Temporary", internship: "Internship", apprenticeship: "Apprenticeship",
    working_student: "Working student",
  };
  for (const value of [scraped, extracted]) {
    const normalized = String(value || "").toLowerCase().replace(/[\s-]+/g, "_");
    if (labels[normalized] && normalized !== "full_time") return labels[normalized];
  }
  const wording = String(title || "").toLowerCase();
  if (/\b(working student|werkstudent(?:in)?|werkstudent:in)\b/.test(wording)) return "Working student";
  if (/\b(intern|internship|praktikum|praktikant(?:in)?)\b/.test(wording)) return "Internship";
  if (/\b(part[ -]?time|teilzeit)\b/.test(wording)) return "Part-time";
  if (/\b(temporary|fixed[ -]term|contractor|contract role|contract position|\d+\s*(?:month|year)s?\s+contract)\b/.test(wording)) return "Contract";
  return "Full-time";
}

export function descriptionLines(items) {
  return items.flatMap((item) => String(typeof item === "string" ? item : item?.text || "")
    .split(/\r?\n/)
    .map((line) => line.replace(/^\s*(?:[•*-]|\d+[.)])\s*/, "").trim())
    .filter(Boolean));
}
