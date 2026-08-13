export const ADMIN_NAV_GROUPS = [
  {
    label: "Command center",
    items: [
      { label: "Overview", icon: "space_dashboard", to: "/admin", end: true },
      { label: "Analytics", icon: "monitoring", to: "/admin/analytics" },
    ],
  },
  {
    label: "Acquisition",
    items: [
      { label: "Sources", icon: "hub", to: "/admin/acquisition/sources" },
      { label: "Imports", icon: "download", to: "/admin/acquisition/imports" },
      { label: "Jobs", icon: "work", to: "/admin/acquisition/jobs" },
      { label: "Companies", icon: "domain", to: "/admin/acquisition/companies" },
    ],
  },
  {
    label: "Quality",
    items: [
      { label: "Enrichment", icon: "auto_awesome", to: "/admin/acquisition/enrichment" },
      { label: "Data quality", icon: "fact_check", to: "/admin/acquisition/data-quality" },
      { label: "Quality rules", icon: "rule", to: "/admin/acquisition/rules" },
      { label: "Reprocessing", icon: "replay", to: "/admin/acquisition/reprocessing" },
      { label: "Duplicates", icon: "content_copy", to: "/admin/acquisition/duplicates" },
    ],
  },
  {
    label: "Release",
    items: [
      { label: "Publication", icon: "publish", to: "/admin/acquisition/publication" },
      { label: "Live catalog", icon: "language", to: "/admin/acquisition/live-catalog" },
      { label: "Acquisition audit", icon: "manage_search", to: "/admin/acquisition/audit" },
    ],
  },
  {
    label: "Platform",
    items: [
      { label: "System health", icon: "monitor_heart", to: "/admin/system" },
      { label: "Provider policy", icon: "policy", to: "/admin/provider-policy" },
      { label: "General events", icon: "event_note", to: "/admin/events" },
      { label: "Promotions", icon: "sell", to: "/admin/promotions" },
      { label: "Access and permissions", icon: "admin_panel_settings", to: "/admin/access" },
    ],
  },
];

export const ADMIN_NAV_ITEMS = ADMIN_NAV_GROUPS.flatMap((group) => group.items);

const ACQUISITION_SECTION_TITLES = {
  imports: "Imports",
  companies: "Companies",
  enrichment: "Enrichment",
  "data-quality": "Data quality",
  rules: "Quality rules",
  reprocessing: "Reprocessing",
  duplicates: "Duplicates",
  publication: "Publication",
  "live-catalog": "Live catalog",
  audit: "Acquisition audit",
};

export function getAdminPageMeta(pathname) {
  if (pathname === "/admin") return { group: "Command center", title: "Operations overview" };
  const item = ADMIN_NAV_ITEMS
    .filter((candidate) => candidate.to !== "/admin")
    .sort((left, right) => right.to.length - left.to.length)
    .find((candidate) => pathname === candidate.to || pathname.startsWith(`${candidate.to}/`));
  if (item) {
    const group = ADMIN_NAV_GROUPS.find((candidate) => candidate.items.includes(item));
    const detail = pathname !== item.to;
    return { group: group?.label || "Admin", title: detail ? `${item.label} detail` : item.label };
  }
  return { group: "Admin", title: "Page not found" };
}

export function canonicalAcquisitionPath(section, suffix = "") {
  const normalized = String(section || "").replace(/^\/+|\/+$/g, "");
  if (!ACQUISITION_SECTION_TITLES[normalized]) return "/admin";
  return `/admin/acquisition/${normalized}${suffix}`;
}

export function preserveSafeQuery(search, allowedKeys) {
  const current = new URLSearchParams(String(search || "").replace(/^\?/, ""));
  const next = new URLSearchParams();
  allowedKeys.forEach((key) => {
    current.getAll(key).forEach((value) => next.append(key, value));
  });
  const query = next.toString();
  return query ? `?${query}` : "";
}

export function compatibilityTarget(pathname, search = "") {
  if (pathname === "/admin/acquisition") return "/admin";
  if (pathname === "/admin/acquisition/analytics") {
    return `/admin/analytics${preserveSafeQuery(search, ["range", "timezone", "start", "end"])}`;
  }
  if (pathname === "/admin/job-import") {
    const query = preserveSafeQuery(search, [
      "canonical_job_id", "job_id", "source_id", "status", "page", "page_size", "search",
    ]);
    const params = new URLSearchParams(query);
    const selectedId = params.get("canonical_job_id") || params.get("job_id");
    if (selectedId) return `/admin/acquisition/jobs/${encodeURIComponent(selectedId)}`;
    return `/admin/acquisition/jobs${query}`;
  }
  if (pathname === "/admin/scrapeops") {
    return `/admin/provider-policy${preserveSafeQuery(search, [
      "user_id", "workspace_id", "run_id", "occurred_from", "occurred_to", "date",
    ])}`;
  }
  return "";
}
