export const CONNECTION_STRENGTHS = ["Know well", "Know", "Met", "LinkedIn only"];

export function normalizedConnectionStrength(value) {
  const strength = String(value || "").trim();
  return ({ Close: "Know well", Strong: "Know well", Familiar: "Know", Acquaintance: "Met" })[strength]
    || (CONNECTION_STRENGTHS.includes(strength) ? strength : "");
}

function shortRole(value, name = "") {
  let role = String(value || "").replace(/Connected on\b.*$/iu, "").replace(/Message$/u, "").trim();
  if (name && role.startsWith(name)) role = role.slice(name.length).trim();
  role = role.split(/\s*[|\u2022]\s*/u).find(Boolean) || "";
  return role.length > 70 ? `${role.slice(0, 67).trimEnd()}…` : role;
}

export function connectionDetails(contact) {
  const row = contact.metadata?.import_source_row || {};
  const companies = contact.companies || [];
  let headline = String(contact.metadata?.headline ?? row.position ?? row.headline ?? "").trim();
  let name = String(contact.name || "").trim();
  if (contact.source_kind === "linkedin_extension") {
    if (headline.startsWith(name)) headline = headline.slice(name.length);
    headline = headline.replace(/Connected on\b.*$/iu, "").replace(/Message$/u, "").trim();
    // Repair only a joined boundary corroborated by the saved profile URL.
    const slug = String(contact.linkedin_url || "").split("/in/")[1]?.split("/")[0] || "";
    const normalize = (value) => value.normalize("NFKD").replace(/[^a-z0-9]/giu, "").toLowerCase();
    for (const match of name.matchAll(/\p{Ll}(?=\p{Lu}\p{Ll})/gu)) {
      const boundary = match.index + match[0].length;
      const candidate = name.slice(0, boundary);
      const suffix = normalize(slug).slice(normalize(candidate).length);
      if (normalize(slug).startsWith(normalize(candidate)) && (!suffix || /^\d[a-z0-9]*$/u.test(suffix))) {
        headline = name.slice(boundary).trim();
        name = candidate.trim();
        break;
      }
    }
  }
  // Older extension versions included the occupation inside the profile link.
  if (headline && name.endsWith(headline) && name.length > headline.length) {
    name = name.slice(0, -headline.length).trim();
  }
  const occupation = headline.match(/^(.+?)\s+(?:at|@)\s+(.+)$/iu);
  return {
    name,
    headline,
    jobTitle: shortRole(companies.map((entry) => entry.role_title).find(Boolean) || occupation?.[1] || headline, name),
    company: companies.map((entry) => entry.company_name || entry.company).find(Boolean) || contact.company || occupation?.[2] || "",
    strength: normalizedConnectionStrength(contact.metadata?.connection_strength || contact.relationship_note),
    notes: contact.metadata?.notes ?? (contact.source_kind === "manual" && !normalizedConnectionStrength(contact.relationship_note) ? contact.relationship_note : ""),
  };
}

export function filterConnections(contacts, filters) {
  return contacts.filter((contact) => {
    const details = connectionDetails(contact);
    if (filters.query) {
      const haystack = [details.name, details.jobTitle, details.company].join(" ").toLocaleLowerCase();
      return haystack.includes(filters.query.trim().toLocaleLowerCase());
    }
    return Object.entries(filters).every(([field, value]) => !value || String(details[field] || "").toLocaleLowerCase().includes(value.trim().toLocaleLowerCase()));
  });
}
