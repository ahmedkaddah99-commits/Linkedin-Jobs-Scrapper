const TONE_BY_KIND = {
  employer: "employer",
  profile: "profile",
  inference: "inference",
  uncertain: "uncertain",
  missing: "missing",
  preview: "preview",
};

export default function ProvenanceTag({ children, kind = "preview" }) {
  return <span className={["preview-provenance", `preview-provenance--${TONE_BY_KIND[kind] || "preview"}`].join(" ")}>{children}</span>;
}
