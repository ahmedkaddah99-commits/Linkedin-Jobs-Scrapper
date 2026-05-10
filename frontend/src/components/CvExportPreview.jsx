const PROFILE_PLACEHOLDER_URL =
  "https://lh3.googleusercontent.com/aida-public/AB6AXuCEbDDRgu4_REnkpR4gbSify0khawEFxHuQHLBm7Xbd6BmM7LDM-dlp8wOKL0QkSDuiFg7g9UDpYPZnV2uV8Qmu5cxn1MBriXeVmXUz8EGMsgieO36lJEpcY5FCDph2ooQGzwpKRq5qwQluOCY4JB_gfySIUY2T0ozlVp3DEmdnT9aCfADFkC1BXeteFPTxYhtUsABzZLWUOD6fNpuVFVFLjuxpQaEgkpVd_bvuz61H_FfJkq5V_4CESVQjz3tEa3rwtGfzcKHXwJE";

const DEFAULT_TEMPLATE = {
  id: "classic",
  label: "Classic",
};

const DEFAULT_SCHEME = {
  primary: "1F3A5F",
  accent: "2EC4B6",
  surface: "EAF3FF",
};

const PLAIN_SCHEME = {
  primary: "111111",
  accent: "111111",
  surface: "FFFFFF",
};

function hexToRgb(value) {
  const normalized = String(value || "")
    .replace(/^#/, "")
    .trim();
  if (!/^[0-9a-fA-F]{6}$/.test(normalized)) {
    return { r: 17, g: 24, b: 39 };
  }
  return {
    r: parseInt(normalized.slice(0, 2), 16),
    g: parseInt(normalized.slice(2, 4), 16),
    b: parseInt(normalized.slice(4, 6), 16),
  };
}

function withAlpha(hex, alpha) {
  const { r, g, b } = hexToRgb(hex);
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

function previewPalette(template, rawScheme) {
  const scheme = template.id === "plain" ? PLAIN_SCHEME : { ...DEFAULT_SCHEME, ...(rawScheme || {}) };
  return {
    primary: `#${scheme.primary}`,
    accent: `#${scheme.accent}`,
    surface: `#${scheme.surface}`,
    text: template.id === "plain" ? "#111111" : "#111827",
    muted: template.id === "plain" ? "#444444" : "#475569",
    border: template.id === "plain" ? "#111111" : withAlpha(scheme.primary, 0.18),
    softBorder: template.id === "plain" ? "#D4D4D4" : withAlpha(scheme.primary, 0.1),
    tint: template.id === "plain" ? "#F7F7F7" : withAlpha(scheme.primary, 0.05),
  };
}

function firstNonEmpty(...values) {
  for (const value of values) {
    if (String(value || "").trim()) {
      return String(value).trim();
    }
  }
  return "";
}

function normalizeBullets(item) {
  if (Array.isArray(item?.bullets) && item.bullets.length) {
    return item.bullets.map((entry) => String(entry || "").trim()).filter(Boolean);
  }
  return String(item?.bulletsText || "")
    .split(/\r?\n/)
    .map((entry) => entry.replace(/^\s*[-*]\s*/, "").trim())
    .filter(Boolean);
}

function buildPreviewModel(profile = {}, documents = {}, options = {}) {
  const template =
    (options.cv_templates || []).find((item) => item.id === documents.cv_template) || DEFAULT_TEMPLATE;
  const scheme =
    (options.cv_color_schemes || []).find((item) => item.id === documents.cv_color_scheme) ||
    DEFAULT_SCHEME;
  const experience = (Array.isArray(profile.recent_experience) ? profile.recent_experience : [])
    .map((item) => ({
      title: firstNonEmpty(item?.title, item?.role, "Role Title"),
      company: firstNonEmpty(item?.company, "Company"),
      period: firstNonEmpty(item?.period, "2023 - Present"),
      bullets: normalizeBullets(item).slice(0, 2),
    }))
    .slice(0, 2);
  const skills = (Array.isArray(profile.competencies) ? profile.competencies : [])
    .map((item) => String(item || "").trim())
    .filter(Boolean)
    .slice(0, 8);
  const languages = (Array.isArray(profile.languages) ? profile.languages : [])
    .map((item) => String(item || "").trim())
    .filter(Boolean)
    .slice(0, 4);
  const contacts = [
    profile.location,
    profile.email,
    profile.website,
    profile.linkedin_url,
  ]
    .map((item) => String(item || "").trim())
    .filter(Boolean)
    .slice(0, 4);
  const education = (Array.isArray(profile.education) ? profile.education : [])
    .map((item) => {
      if (item && typeof item === "object") {
        const head = [
          firstNonEmpty(item.degree_title, item.title),
          firstNonEmpty(item.institution, item.school),
          firstNonEmpty(item.period),
        ]
          .filter(Boolean)
          .join(" | ");
        const details = Array.isArray(item.details)
          ? item.details.filter(Boolean)
          : String(item.detailsText || "")
              .split(/\r?\n/)
              .map((entry) => entry.trim())
              .filter(Boolean);
        return [head, details[0]].filter(Boolean).join(" - ");
      }
      return String(item || "").trim();
    })
    .filter(Boolean)
    .slice(0, 2);

  return {
    template,
    palette: previewPalette(template, scheme),
    fontFamily: documents.cv_font || "Calibri",
    showPhoto: Boolean(documents.include_photo),
    name: firstNonEmpty(profile.name, "Candidate Name"),
    headline: firstNonEmpty(profile.role_title, template.label),
    summary: firstNonEmpty(
      profile.summary,
      "Tailored summary preview for the selected export template.",
    ),
    experience:
      experience.length > 0
        ? experience
        : [
            {
              title: "Role Title",
              company: "Company",
              period: "2023 - Present",
              bullets: [
                "Highlights tailored achievements for the role.",
                "Keeps structure readable after PDF export.",
              ],
            },
          ],
    skills:
      skills.length > 0
        ? skills
        : ["Stakeholder management", "Process design", "Analytics", "Communication"],
    languages,
    contacts,
    education:
      education.length > 0 ? education : ["Education and certifications appear here"],
    photoUrl: firstNonEmpty(profile.photo_data_url, profile.avatar_url, PROFILE_PLACEHOLDER_URL),
  };
}

function SectionHeading({ label, templateId, palette }) {
  const text =
    templateId === "classic" || templateId === "compact" || templateId === "plain"
      ? label.toUpperCase()
      : label;
  return (
    <div className="mb-2">
      <div
        className="text-[11px] font-bold tracking-[0.18em]"
        style={{ color: palette.primary }}
      >
        {text}
      </div>
      <div
        className="mt-1 h-px w-full"
        style={{ backgroundColor: templateId === "plain" ? "#111111" : palette.primary }}
      />
    </div>
  );
}

function PreviewPhoto({ model, roundedClass = "rounded-full", sizeClass = "h-16 w-16" }) {
  if (!model.showPhoto) {
    return null;
  }
  return (
    <img
      alt="Profile preview"
      className={`${sizeClass} ${roundedClass} border object-cover`}
      src={model.photoUrl}
      style={{ borderColor: model.palette.softBorder }}
    />
  );
}

function ExperienceList({ model, compact = false }) {
  return (
    <div className={compact ? "space-y-3" : "space-y-4"}>
      {model.experience.map((item, index) => (
        <div key={`${item.title}-${index}`}>
          <div
            className={compact ? "text-xs font-semibold" : "text-sm font-semibold"}
            style={{ color: model.palette.text }}
          >
            {[item.title, item.company].filter(Boolean).join(" | ")}
          </div>
          <div className="text-[11px]" style={{ color: model.palette.muted }}>
            {item.period}
          </div>
          <div className="mt-1 space-y-1.5">
            {(item.bullets.length ? item.bullets : ["Role-specific accomplishment preview"]).map(
              (bullet, bulletIndex) => (
                <div
                  className={compact ? "text-[11px] leading-5" : "text-xs leading-5"}
                  key={`${item.title}-${bulletIndex}`}
                  style={{ color: model.palette.text }}
                >
                  - {bullet}
                </div>
              ),
            )}
          </div>
        </div>
      ))}
    </div>
  );
}

function ClassicPreview({ model }) {
  return (
    <div className="space-y-4" style={{ fontFamily: model.fontFamily }}>
      <div
        className="flex items-start justify-between gap-4 border-b-[3px] pb-3"
        style={{ borderColor: model.palette.primary }}
      >
        <div>
          <div className="text-xl font-bold" style={{ color: model.palette.primary }}>
            {model.name}
          </div>
          <div className="text-sm" style={{ color: model.palette.accent }}>
            {model.headline}
          </div>
          {model.contacts.length ? (
            <div className="mt-2 text-xs leading-5" style={{ color: model.palette.muted }}>
              {model.contacts.join(" | ")}
            </div>
          ) : null}
        </div>
        <PreviewPhoto model={model} />
      </div>

      <div className="space-y-4">
        <div>
          <SectionHeading label="Professional Summary" palette={model.palette} templateId={model.template.id} />
          <div className="text-xs leading-6" style={{ color: model.palette.text }}>
            {model.summary}
          </div>
        </div>
        <div>
          <SectionHeading label="Experience" palette={model.palette} templateId={model.template.id} />
          <ExperienceList model={model} />
        </div>
        <div>
          <SectionHeading label="Skills" palette={model.palette} templateId={model.template.id} />
          <div className="text-xs leading-6" style={{ color: model.palette.text }}>
            {model.skills.join(", ")}
          </div>
        </div>
      </div>
    </div>
  );
}

function ModernPreview({ model }) {
  return (
    <div className="space-y-4" style={{ fontFamily: model.fontFamily }}>
      <div
        className="rounded-2xl border p-4"
        style={{
          borderColor: model.palette.softBorder,
          background: `linear-gradient(135deg, ${model.palette.surface} 0%, #FFFFFF 100%)`,
        }}
      >
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0">
            <div className="text-[11px] font-bold uppercase tracking-[0.22em]" style={{ color: model.palette.accent }}>
              Modern
            </div>
            <div className="mt-2 text-[22px] font-bold leading-tight" style={{ color: model.palette.primary }}>
              {model.name}
            </div>
            <div className="mt-1 text-sm" style={{ color: model.palette.text }}>
              {model.headline}
            </div>
          </div>
          <PreviewPhoto model={model} roundedClass="rounded-2xl" sizeClass="h-20 w-20" />
        </div>
        {model.contacts.length ? (
          <div className="mt-4 flex flex-wrap gap-2">
            {model.contacts.map((item) => (
              <span
                className="rounded-full px-2.5 py-1 text-[11px]"
                key={item}
                style={{
                  color: model.palette.primary,
                  backgroundColor: withAlpha(model.palette.primary.replace(/^#/, ""), 0.08),
                }}
              >
                {item}
              </span>
            ))}
          </div>
        ) : null}
      </div>

      <div className="space-y-3">
        <div
          className="rounded-xl border p-4"
          style={{ borderColor: model.palette.softBorder, backgroundColor: "#FFFFFF" }}
        >
          <div className="text-sm font-semibold" style={{ color: model.palette.primary }}>
            Professional Summary
          </div>
          <div className="mt-2 text-xs leading-6" style={{ color: model.palette.text }}>
            {model.summary}
          </div>
        </div>
        <div
          className="rounded-xl border p-4"
          style={{ borderColor: model.palette.softBorder, backgroundColor: "#FFFFFF" }}
        >
          <div className="text-sm font-semibold" style={{ color: model.palette.primary }}>
            Experience
          </div>
          <div className="mt-3">
            <ExperienceList model={model} />
          </div>
        </div>
        <div className="grid gap-3" style={{ gridTemplateColumns: "minmax(0, 1fr) minmax(0, 1fr)" }}>
          <div
            className="rounded-xl border p-4"
            style={{ borderColor: model.palette.softBorder, backgroundColor: "#FFFFFF" }}
          >
            <div className="text-sm font-semibold" style={{ color: model.palette.primary }}>
              Skills
            </div>
            <div className="mt-2 text-xs leading-6" style={{ color: model.palette.text }}>
              {model.skills.join(", ")}
            </div>
          </div>
          <div
            className="rounded-xl border p-4"
            style={{ borderColor: model.palette.softBorder, backgroundColor: "#FFFFFF" }}
          >
            <div className="text-sm font-semibold" style={{ color: model.palette.primary }}>
              Education
            </div>
            <div className="mt-2 space-y-1 text-xs leading-6" style={{ color: model.palette.text }}>
              {model.education.map((item) => (
                <div key={item}>{item}</div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function CompactPreview({ model }) {
  return (
    <div
      className="grid gap-4"
      style={{ fontFamily: model.fontFamily, gridTemplateColumns: "112px minmax(0, 1fr)" }}
    >
      <div
        className="rounded-xl border p-3"
        style={{ borderColor: model.palette.softBorder, backgroundColor: model.palette.surface }}
      >
        <div className="space-y-3">
          <PreviewPhoto model={model} roundedClass="rounded-xl" sizeClass="h-20 w-full" />
          <div>
            <div className="text-xs font-bold tracking-[0.18em]" style={{ color: model.palette.primary }}>
              {model.name}
            </div>
            <div className="mt-1 text-[11px] leading-5" style={{ color: model.palette.muted }}>
              {model.contacts.join(" | ") || model.headline}
            </div>
          </div>
          <div>
            <div className="text-[10px] font-bold tracking-[0.18em]" style={{ color: model.palette.primary }}>
              SKILLS
            </div>
            <div className="mt-1 space-y-1 text-[11px] leading-5" style={{ color: model.palette.text }}>
              {model.skills.slice(0, 5).map((item) => (
                <div key={item}>{item}</div>
              ))}
            </div>
          </div>
          {model.languages.length ? (
            <div>
              <div className="text-[10px] font-bold tracking-[0.18em]" style={{ color: model.palette.primary }}>
                LANG
              </div>
              <div className="mt-1 space-y-1 text-[11px] leading-5" style={{ color: model.palette.text }}>
                {model.languages.map((item) => (
                  <div key={item}>{item}</div>
                ))}
              </div>
            </div>
          ) : null}
        </div>
      </div>

      <div className="space-y-4">
        <div>
          <SectionHeading label="Summary" palette={model.palette} templateId={model.template.id} />
          <div className="text-xs leading-6" style={{ color: model.palette.text }}>
            {model.summary}
          </div>
        </div>
        <div>
          <SectionHeading label="Experience" palette={model.palette} templateId={model.template.id} />
          <ExperienceList compact model={model} />
        </div>
        <div>
          <SectionHeading label="Education" palette={model.palette} templateId={model.template.id} />
          <div className="space-y-1 text-xs leading-6" style={{ color: model.palette.text }}>
            {model.education.map((item) => (
              <div key={item}>{item}</div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

function EuropassPreview({ model }) {
  const rows = [
    { label: "Profile", content: <div className="text-xs leading-6">{model.summary}</div> },
    {
      label: "Experience",
      content: <ExperienceList compact model={model} />,
    },
    {
      label: "Skills",
      content: <div className="text-xs leading-6">{model.skills.join(", ")}</div>,
    },
    {
      label: "Education",
      content: (
        <div className="space-y-1 text-xs leading-6">
          {model.education.map((item) => (
            <div key={item}>{item}</div>
          ))}
        </div>
      ),
    },
  ];

  return (
    <div className="space-y-4" style={{ fontFamily: model.fontFamily }}>
      <div className="flex items-start justify-between gap-4">
        <div>
          <div className="text-xl font-bold" style={{ color: model.palette.primary }}>
            {model.name}
          </div>
          <div className="mt-1 text-sm" style={{ color: model.palette.text }}>
            {model.headline}
          </div>
          {model.contacts.length ? (
            <div className="mt-2 text-xs leading-5" style={{ color: model.palette.muted }}>
              {model.contacts.join(" | ")}
            </div>
          ) : null}
        </div>
        <PreviewPhoto model={model} roundedClass="rounded-lg" sizeClass="h-20 w-16" />
      </div>

      <div className="space-y-2">
        {rows.map((row) => (
          <div
            className="grid gap-3 border-t pt-2"
            key={row.label}
            style={{
              borderColor: model.palette.softBorder,
              gridTemplateColumns: "88px minmax(0, 1fr)",
            }}
          >
            <div
              className="text-[11px] font-bold uppercase tracking-[0.18em]"
              style={{ color: model.palette.muted }}
            >
              {row.label}
            </div>
            <div style={{ color: model.palette.text }}>{row.content}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

function PlainPreview({ model }) {
  return (
    <div className="space-y-4" style={{ fontFamily: model.fontFamily }}>
      <div className="flex items-start justify-between gap-4 border-b pb-3" style={{ borderColor: "#111111" }}>
        <div>
          <div className="text-xl font-bold tracking-[0.08em]" style={{ color: "#111111" }}>
            {model.name}
          </div>
          <div className="mt-1 text-sm" style={{ color: "#111111" }}>
            {model.headline}
          </div>
          {model.contacts.length ? (
            <div className="mt-2 text-xs leading-5" style={{ color: "#444444" }}>
              {model.contacts.join(" | ")}
            </div>
          ) : null}
        </div>
        <PreviewPhoto model={model} roundedClass="rounded-none" sizeClass="h-16 w-16" />
      </div>

      <div className="space-y-4">
        <div>
          <SectionHeading label="Professional Summary" palette={model.palette} templateId={model.template.id} />
          <div className="text-xs leading-6" style={{ color: "#111111" }}>
            {model.summary}
          </div>
        </div>
        <div>
          <SectionHeading label="Experience" palette={model.palette} templateId={model.template.id} />
          <ExperienceList model={model} />
        </div>
        <div>
          <SectionHeading label="Skills" palette={model.palette} templateId={model.template.id} />
          <div className="text-xs leading-6" style={{ color: "#111111" }}>
            {model.skills.join(" | ")}
          </div>
        </div>
      </div>
    </div>
  );
}

export function CvExportPreview({ documents = {}, profile = {}, options = {}, className = "" }) {
  const model = buildPreviewModel(profile, documents, options);

  let content = <ClassicPreview model={model} />;
  if (model.template.id === "modern") {
    content = <ModernPreview model={model} />;
  } else if (model.template.id === "compact") {
    content = <CompactPreview model={model} />;
  } else if (model.template.id === "europass") {
    content = <EuropassPreview model={model} />;
  } else if (model.template.id === "plain") {
    content = <PlainPreview model={model} />;
  }

  return (
    <div
      className={[
        "overflow-hidden rounded-xl border bg-white p-5 shadow-sm",
        className,
      ].join(" ")}
      style={{ borderColor: model.template.id === "plain" ? "#111111" : model.palette.softBorder }}
    >
      {content}
    </div>
  );
}
