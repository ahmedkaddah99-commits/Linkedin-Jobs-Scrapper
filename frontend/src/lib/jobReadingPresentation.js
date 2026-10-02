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
