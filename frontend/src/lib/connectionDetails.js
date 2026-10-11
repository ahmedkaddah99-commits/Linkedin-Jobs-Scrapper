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
    jobTitle: companies.map((entry) => entry.role_title).filter(Boolean).join(" · ") || occupation?.[1] || headline,
    company: companies.map((entry) => entry.company_name || entry.company).filter(Boolean).join(" · ") || contact.company || occupation?.[2] || "",
    strength: contact.metadata?.connection_strength || (["Close", "Strong", "Familiar", "Acquaintance"].includes(contact.relationship_note) ? contact.relationship_note : ""),
    notes: contact.metadata?.notes ?? (contact.source_kind === "manual" && !["Close", "Strong", "Familiar", "Acquaintance"].includes(contact.relationship_note) ? contact.relationship_note : ""),
  };
}

export function filterConnections(contacts, filters) {
  return contacts.filter((contact) => {
    const details = connectionDetails(contact);
    return Object.entries(filters).every(([field, value]) => !value || String(details[field] || "").toLocaleLowerCase().includes(value.trim().toLocaleLowerCase()));
  });
}
