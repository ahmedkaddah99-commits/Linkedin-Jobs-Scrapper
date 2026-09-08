const LINK_DEFINITIONS = [
  { kind: "linkedin", field: "linkedin_url", alias: "linkedin", label: "LinkedIn" },
  { kind: "github", field: "github_url", alias: "github", label: "GitHub" },
  { kind: "website", field: "website", alias: "portfolio_url", label: "Website" },
];

export function normalizeCvLink(value) {
  const raw = String(value || "").trim();
  if (!raw || /^(?:javascript|data|vbscript):/i.test(raw)) {
    return "";
  }
  if (/^[a-z][a-z\d+.-]*:\/\//i.test(raw)) {
    return raw;
  }
  return `https://${raw.replace(/^\/\//, "")}`;
}

export function buildCvSocialLinks(source = {}) {
  const profile = source && typeof source === "object" ? source : {};
  const links = [];
  for (const definition of LINK_DEFINITIONS) {
    const rawValue =
      profile[definition.field] ||
      profile[definition.alias] ||
      (definition.kind === "website" && typeof profile.portfolio === "string" ? profile.portfolio : "");
    const href = normalizeCvLink(rawValue);
    if (!href) continue;
    links.push({
      ...definition,
      label:
        definition.kind === "website" && (profile.portfolio_url || profile.portfolio)
          ? "Portfolio"
          : definition.label,
      href,
    });
  }
  return links;
}

export function hasCvContactDetails(source = {}) {
  return Boolean(
    [source.email, source.location].some((value) => String(value || "").trim()) ||
      buildCvSocialLinks(source).length,
  );
}

export function socialLinkIconSvg(kind, className = "cv-social-icon") {
  const safeClassName = String(className || "cv-social-icon");
  const shared = `class="${safeClassName}" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true" focusable="false"`;
  if (kind === "linkedin") {
    return `<svg ${shared}><path d="M5.1 3.7a2.1 2.1 0 1 1-4.2 0 2.1 2.1 0 0 1 4.2 0ZM1.2 7h3.8v12H1.2V7Zm6.1 0h3.6v1.6h.1c.5-.9 1.7-1.9 3.6-1.9 3.8 0 4.5 2.5 4.5 5.8V19h-3.8v-5.7c0-1.4 0-3.2-2-3.2s-2.3 1.5-2.3 3.1V19H7.3V7Z"/></svg>`;
  }
  if (kind === "github") {
    return `<svg ${shared}><path d="M12 .5a12 12 0 0 0-3.8 23.4c.6.1.8-.3.8-.6v-2.2c-3.3.7-4-1.4-4-1.4-.5-1.3-1.3-1.7-1.3-1.7-1.1-.8.1-.8.1-.8 1.2.1 1.8 1.3 1.8 1.3 1.1 1.8 2.8 1.3 3.5 1 .1-.8.4-1.3.8-1.6-2.7-.3-5.5-1.3-5.5-5.9 0-1.3.5-2.4 1.3-3.2-.1-.3-.6-1.6.1-3.2 0 0 1-.3 3.3 1.2a11.5 11.5 0 0 1 6 0c2.3-1.5 3.3-1.2 3.3-1.2.7 1.6.2 2.9.1 3.2.8.8 1.3 1.9 1.3 3.2 0 4.6-2.8 5.6-5.5 5.9.4.4.8 1.1.8 2.2v3.2c0 .3.2.7.8.6A12 12 0 0 0 12 .5Z"/></svg>`;
  }
  return `<svg ${shared}><circle cx="12" cy="12" r="8.7" fill="none" stroke="currentColor" stroke-width="1.8"/><path d="M3.7 12h16.6M12 3.3c2.3 2.4 3.4 5.3 3.4 8.7s-1.1 6.3-3.4 8.7c-2.3-2.4-3.4-5.3-3.4-8.7S9.7 5.7 12 3.3Z" fill="none" stroke="currentColor" stroke-width="1.4"/></svg>`;
}
