import { buildCvSocialLinks, hasCvContactDetails } from "../lib/cvSocialLinks.js";

function SocialIcon({ kind, className = "h-3.5 w-3.5" }) {
  if (kind === "linkedin") {
    return <svg aria-hidden="true" className={className} fill="currentColor" viewBox="0 0 24 24"><path d="M5.1 3.7a2.1 2.1 0 1 1-4.2 0 2.1 2.1 0 0 1 4.2 0ZM1.2 7h3.8v12H1.2V7Zm6.1 0h3.6v1.6h.1c.5-.9 1.7-1.9 3.6-1.9 3.8 0 4.5 2.5 4.5 5.8V19h-3.8v-5.7c0-1.4 0-3.2-2-3.2s-2.3 1.5-2.3 3.1V19H7.3V7Z" /></svg>;
  }
  if (kind === "github") {
    return <svg aria-hidden="true" className={className} fill="currentColor" viewBox="0 0 24 24"><path d="M12 .5a12 12 0 0 0-3.8 23.4c.6.1.8-.3.8-.6v-2.2c-3.3.7-4-1.4-4-1.4-.5-1.3-1.3-1.7-1.3-1.7-1.1-.8.1-.8.1-.8 1.2.1 1.8 1.3 1.8 1.3 1.1 1.8 2.8 1.3 3.5 1 .1-.8.4-1.3.8-1.6-2.7-.3-5.5-1.3-5.5-5.9 0-1.3.5-2.4 1.3-3.2-.1-.3-.6-1.6.1-3.2 0 0 1-.3 3.3 1.2a11.5 11.5 0 0 1 6 0c2.3-1.5 3.3-1.2 3.3-1.2.7 1.6.2 2.9.1 3.2.8.8 1.3 1.9 1.3 3.2 0 4.6-2.8 5.6-5.5 5.9.4.4.8 1.1.8 2.2v3.2c0 .3.2.7.8.6A12 12 0 0 0 12 .5Z" /></svg>;
  }
  return <svg aria-hidden="true" className={className} fill="none" stroke="currentColor" strokeWidth="1.8" viewBox="0 0 24 24"><circle cx="12" cy="12" r="8.7" /><path d="M3.7 12h16.6M12 3.3c2.3 2.4 3.4 5.3 3.4 8.7s-1.1 6.3-3.4 8.7c-2.3-2.4-3.4-5.3-3.4-8.7S9.7 5.7 12 3.3Z" /></svg>;
}

export function CvContactLinks({
  source = {},
  className = "",
  detailClassName = "",
  detailStyle,
  linkClassName = "",
  linkStyle,
  limit,
}) {
  const details = [
    source.location ? { key: "location", value: source.location } : null,
    source.email ? { key: "email", value: source.email, href: `mailto:${source.email}` } : null,
  ].filter(Boolean);
  const links = buildCvSocialLinks(source).slice(0, limit || Number.MAX_SAFE_INTEGER);
  if (!details.length && !links.length) return null;

  return (
    <div className={className}>
      {details.map((item) => (
        item.href ? (
          <a className={detailClassName} href={item.href} key={item.key} style={detailStyle}>{item.value}</a>
        ) : (
          <span className={detailClassName} key={item.key} style={detailStyle}>{item.value}</span>
        )
      ))}
      {links.map((link) => (
        <a
          aria-label={link.label}
          className={`inline-flex items-center gap-1 ${linkClassName}`}
          href={link.href}
          key={link.kind}
          rel="noreferrer"
          style={linkStyle}
          target="_blank"
        >
          <SocialIcon kind={link.kind} />
          <span>{link.label}</span>
        </a>
      ))}
    </div>
  );
}

export { buildCvSocialLinks, hasCvContactDetails };
