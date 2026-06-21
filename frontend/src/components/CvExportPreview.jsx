export const PROFILE_PLACEHOLDER_URL =
  "https://lh3.googleusercontent.com/aida-public/AB6AXuCEbDDRgu4_REnkpR4gbSify0khawEFxHuQHLBm7Xbd6BmM7LDM-dlp8wOKL0QkSDuiFg7g9UDpYPZnV2uV8Qmu5cxn1MBriXeVmXUz8EGMsgieO36lJEpcY5FCDph2ooQGzwpKRq5qwQluOCY4JB_gfySIUY2T0ozlVp3DEmdnT9aCfADFkC1BXeteFPTxYhtUsABzZLWUOD6fNpuVFVFLjuxpQaEgkpVd_bvuz61H_FfJkq5V_4CESVQjz3tEa3rwtGfzcKHXwJE";

const DEFAULT_TEMPLATE = {
  id: "plain",
  label: "Plain",
};

const PLAIN_TEMPLATE = {
  id: "plain",
  label: "Plain",
};

const TEMPLATE_ALIASES = {
  classic: "plain",
  modern: "plain",
  compact: "plain",
  europass: "plain",
  teal_resume: "plain",
};

const DEFAULT_SCHEME = {
  primary: "1F3A5F",
  accent: "2EC4B6",
  surface: "EAF3FF",
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

function previewPalette(rawScheme) {
  const scheme = { ...DEFAULT_SCHEME, ...(rawScheme || {}) };
  return {
    primary: `#${scheme.primary}`,
    accent: `#${scheme.accent}`,
    surface: `#${scheme.surface}`,
    text: "#111827",
    muted: "#475569",
    border: withAlpha(scheme.primary, 0.18),
    softBorder: withAlpha(scheme.primary, 0.1),
    tint: withAlpha(scheme.primary, 0.05),
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

function normalizeTemplateId(value) {
  const normalizedValue = String(value || "").trim().toLowerCase();
  return TEMPLATE_ALIASES[normalizedValue] || normalizedValue || "plain";
}

function normalizeBullets(item) {
  if (Array.isArray(item?.bullets) && item.bullets.length) {
    return item.bullets.map((entry) => String(entry || "").trim()).filter(Boolean);
  }
  if (Array.isArray(item?.details) && item.details.length) {
    return item.details.map((entry) => String(entry || "").trim()).filter(Boolean);
  }
  return String(item?.bulletsText || item?.detailsText || item?.description || item?.content || item?.text || "")
    .split(/\r?\n/)
    .map((entry) => entry.replace(/^\s*[-*]\s*/, "").trim())
    .filter(Boolean);
}

function buildPreviewModel(profile = {}, documents = {}, options = {}) {
  const templateId = normalizeTemplateId(documents.cv_template);
  const template =
    (options.cv_templates || []).find((item) => item.id === templateId) ||
    (templateId === "plain" ? PLAIN_TEMPLATE : DEFAULT_TEMPLATE);
  const scheme =
    (options.cv_color_schemes || []).find((item) => item.id === documents.cv_color_scheme) ||
    DEFAULT_SCHEME;
  const experience = (Array.isArray(profile.recent_experience) ? profile.recent_experience : [])
    .map((item) => ({
      title: firstNonEmpty(item?.title, item?.role, "Role Title"),
      company: firstNonEmpty(item?.company, "Company"),
      period: firstNonEmpty(item?.period, "2023 - Present"),
      bullets: normalizeBullets(item),
    }));
  const projects = (Array.isArray(profile.projects) ? profile.projects : [])
    .map((item) => ({
      title: firstNonEmpty(item?.title, item?.name, item?.project, "Project"),
      period: firstNonEmpty(item?.period, item?.date, item?.year),
      bullets: normalizeBullets(item),
    }))
    .filter((item) => item.title || item.period || item.bullets.length);
  const customSections = (Array.isArray(profile.custom_sections) ? profile.custom_sections : [])
    .map((item, index) => ({
      id: firstNonEmpty(item?.section_id, item?.id, `custom-section-${index}`),
      heading: firstNonEmpty(item?.heading, item?.title, item?.label, "Additional Information"),
      bullets: normalizeBullets(item),
    }))
    .filter((item) => item.heading || item.bullets.length);
  const skills = (Array.isArray(profile.competencies) ? profile.competencies : [])
    .map((item) => String(item || "").trim())
    .filter(Boolean);
  const languages = (Array.isArray(profile.languages) ? profile.languages : [])
    .map((item) => String(item || "").trim())
    .filter(Boolean);
  const contacts = [
    profile.location,
    profile.email,
    profile.website,
    profile.linkedin_url,
    profile.github_url,
  ]
    .map((item) => String(item || "").trim())
    .filter(Boolean);
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
        return [head, ...details].filter(Boolean).join(" - ");
      }
      return String(item || "").trim();
    })
    .filter(Boolean);

  return {
    template,
    palette: previewPalette(scheme),
    fontFamily: documents.cv_font || "Calibri",
    showPhoto: template.id === "plain" ? false : Boolean(documents.include_photo),
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
    projects,
    customSections,
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

function parseNumber(value) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function buildAtsPreviewState(documents = {}) {
  const nestedGate =
    documents?.ats_export_gate && typeof documents.ats_export_gate === "object"
      ? documents.ats_export_gate
      : null;
  const targetScore = parseNumber(nestedGate?.target_score ?? documents?.ats_target_score);
  const bestScore = parseNumber(
    nestedGate?.best_score ?? documents?.ats_best_score ?? documents?.ats_score,
  );
  const attemptCount = parseNumber(nestedGate?.attempt_count ?? documents?.ats_attempt_count);
  const maxAttempts = parseNumber(nestedGate?.max_attempts ?? documents?.ats_max_attempts);
  const gateState = String(
    nestedGate?.gate_state ?? documents?.ats_gate_state ?? "",
  )
    .trim()
    .toLowerCase();
  const missingRequirements = (
    Array.isArray(nestedGate?.missing_requirements)
      ? nestedGate.missing_requirements
      : Array.isArray(documents?.ats_missing_requirements)
        ? documents.ats_missing_requirements
        : []
  )
    .map((entry) => String(entry || "").trim())
    .filter(Boolean);
  const hasLiveGate =
    Boolean(nestedGate) ||
    targetScore !== null ||
    bestScore !== null ||
    attemptCount !== null ||
    maxAttempts !== null ||
    Boolean(gateState);

  if (!hasLiveGate) {
    return {
      badge: "ATS loop before export",
      callout:
        "Before the final DOCX or PDF is delivered, the tailored CV goes through repeated ATS scoring and improvement passes.",
      metrics: ["Up to 3 ATS passes", "Final export waits for the target score"],
      missingRequirements: [],
      state: "preview",
      steps: [
        {
          id: "tailor",
          label: "Tailor draft",
          copy: "Role-specific content is assembled from the baseline CV.",
          status: "complete",
        },
        {
          id: "ats",
          label: "ATS review loop",
          copy: "Score, refine, and retry until the draft is export-ready.",
          status: "running",
        },
        {
          id: "final",
          label: "Final DOCX/PDF",
          copy: "The final file is released only after ATS review finishes.",
          status: "pending",
        },
      ],
    };
  }

  const state =
    gateState === "passed"
      ? "passed"
      : gateState === "exported_anyway"
        ? "warning"
        : gateState === "blocked"
          ? "blocked"
          : "running";
  const badge =
    state === "passed"
      ? "ATS cleared for export"
      : state === "warning"
        ? "Export allowed with warning"
        : state === "blocked"
          ? "ATS gate blocking export"
          : "ATS review in progress";
  const scoreLabel =
    bestScore !== null && targetScore !== null
      ? `Best score ${bestScore}% of ${targetScore}% target`
      : targetScore !== null
        ? `Target score ${targetScore}%`
        : "ATS review attached";
  const attemptLabel =
    attemptCount !== null && maxAttempts !== null
      ? `Attempt ${attemptCount} of ${maxAttempts}`
      : maxAttempts !== null
        ? `Up to ${maxAttempts} passes`
        : "Repeated review loop";
  const callout =
    state === "passed"
      ? "This draft already cleared the ATS export gate and can be released as the final CV."
      : state === "warning"
        ? "The ATS target was not fully reached, but export was explicitly allowed after the warning state."
        : state === "blocked"
          ? "The final CV is still held back until ATS gaps are fixed or the export warning is acknowledged."
          : "The tailored CV is still being scored and improved before final export is released.";

  return {
    badge,
    callout,
    metrics: [scoreLabel, attemptLabel],
    missingRequirements,
    state,
    steps: [
      {
        id: "tailor",
        label: "Tailor draft",
        copy: "Role-specific content is generated from the source CV.",
        status: "complete",
      },
      {
        id: "ats",
        label: "ATS review loop",
        copy:
          state === "passed"
            ? "The ATS target has been met."
            : state === "warning"
              ? "The loop finished with a warning override."
              : state === "blocked"
                ? "The loop stopped below the target and blocked export."
                : "The draft is still being scored and improved.",
        status: state === "passed" || state === "warning" ? "complete" : state === "blocked" ? "blocked" : "running",
      },
      {
        id: "final",
        label: "Final DOCX/PDF",
        copy:
          state === "passed" || state === "warning"
            ? "Final export can be delivered."
            : "Final export stays locked until ATS review is resolved.",
        status: state === "passed" || state === "warning" ? "complete" : "pending",
      },
    ],
  };
}

function atsStepStyles(stepState, palette) {
  if (stepState === "complete") {
    return {
      backgroundColor: withAlpha(palette.accent, 0.1),
      borderColor: withAlpha(palette.accent, 0.22),
      circleBackground: palette.accent,
      circleColor: "#FFFFFF",
      headingColor: palette.primary,
      bodyColor: palette.text,
    };
  }
  if (stepState === "blocked") {
    return {
      backgroundColor: "rgba(239, 68, 68, 0.08)",
      borderColor: "rgba(239, 68, 68, 0.2)",
      circleBackground: "#EF4444",
      circleColor: "#FFFFFF",
      headingColor: "#B91C1C",
      bodyColor: palette.text,
    };
  }
  if (stepState === "running") {
    return {
      backgroundColor: withAlpha(palette.primary, 0.08),
      borderColor: withAlpha(palette.primary, 0.2),
      circleBackground: palette.primary,
      circleColor: "#FFFFFF",
      headingColor: palette.primary,
      bodyColor: palette.text,
    };
  }
  return {
    backgroundColor: "#FFFFFF",
    borderColor: palette.softBorder,
    circleBackground: withAlpha(palette.primary, 0.08),
    circleColor: palette.primary,
    headingColor: palette.muted,
    bodyColor: palette.muted,
  };
}

function AtsStep({ index, step, palette }) {
  const styles = atsStepStyles(step.status, palette);
  return (
    <div
      className="rounded-2xl border p-3"
      style={{
        backgroundColor: styles.backgroundColor,
        borderColor: styles.borderColor,
      }}
    >
      <div className="flex items-start gap-3">
        <div
          className={[
            "inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-[11px] font-bold",
            step.status === "running" ? "animate-pulse" : "",
          ].join(" ")}
          style={{
            backgroundColor: styles.circleBackground,
            color: styles.circleColor,
          }}
        >
          {index + 1}
        </div>
        <div className="min-w-0">
          <div
            className="text-[11px] font-bold uppercase tracking-[0.18em]"
            style={{ color: styles.headingColor }}
          >
            {step.label}
          </div>
          <div className="mt-1 text-xs leading-5" style={{ color: styles.bodyColor }}>
            {step.copy}
          </div>
        </div>
      </div>
    </div>
  );
}

function AtsExportFlow({ model, documents }) {
  const atsState = buildAtsPreviewState(documents);
  const badgeStyles =
    atsState.state === "passed"
      ? {
          backgroundColor: withAlpha(model.palette.accent, 0.12),
          color: model.palette.primary,
        }
      : atsState.state === "warning"
        ? {
            backgroundColor: "rgba(245, 158, 11, 0.12)",
            color: "#B45309",
          }
        : atsState.state === "blocked"
          ? {
              backgroundColor: "rgba(239, 68, 68, 0.1)",
              color: "#B91C1C",
            }
          : {
              backgroundColor: withAlpha(model.palette.primary, 0.1),
              color: model.palette.primary,
            };

  return (
    <div
      className="mb-5 rounded-2xl border p-4"
      style={{
        borderColor: model.palette.softBorder,
        background: `linear-gradient(135deg, ${withAlpha(model.palette.primary, 0.04)} 0%, #FFFFFF 100%)`,
      }}
    >
      <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
        <div className="min-w-0">
          <div
            className="text-[11px] font-bold uppercase tracking-[0.2em]"
            style={{ color: model.palette.primary }}
          >
            Pre-export pipeline
          </div>
          <div className="mt-1 text-sm font-semibold" style={{ color: model.palette.text }}>
            ATS review keeps running before the final CV is released
          </div>
          <div className="mt-1 text-xs leading-5" style={{ color: model.palette.muted }}>
            {atsState.callout}
          </div>
        </div>
        <span
          className="inline-flex w-fit rounded-full px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.14em]"
          style={badgeStyles}
        >
          {atsState.badge}
        </span>
      </div>

      <div className="mt-4 grid gap-3 md:grid-cols-3">
        {atsState.steps.map((step, index) => (
          <AtsStep index={index} key={step.id} palette={model.palette} step={step} />
        ))}
      </div>

      <div className="mt-4 flex flex-wrap gap-2">
        {atsState.metrics.map((metric) => (
          <span
            className="rounded-full px-2.5 py-1 text-[11px] font-medium"
            key={metric}
            style={{
              color: model.palette.primary,
              backgroundColor: withAlpha(model.palette.primary, 0.08),
            }}
          >
            {metric}
          </span>
        ))}
      </div>

      {atsState.missingRequirements.length ? (
        <div className="mt-3 flex flex-wrap gap-2">
          {atsState.missingRequirements.slice(0, 3).map((requirement) => (
            <span
              className="rounded-full px-2.5 py-1 text-[11px]"
              key={requirement}
              style={{
                color: model.palette.text,
                backgroundColor: withAlpha(model.palette.primary, 0.06),
              }}
            >
              {requirement}
            </span>
          ))}
          {atsState.missingRequirements.length > 3 ? (
            <span
              className="rounded-full px-2.5 py-1 text-[11px]"
              style={{
                color: model.palette.muted,
                backgroundColor: withAlpha(model.palette.primary, 0.04),
              }}
            >
              +{atsState.missingRequirements.length - 3} more gaps
            </span>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

function SectionHeading({ label, templateId, palette }) {
  const text =
    templateId === "classic" || templateId === "compact"
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
        style={{ backgroundColor: palette.primary }}
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

function ProjectList({ model, compact = false }) {
  if (!model.projects.length) {
    return null;
  }
  return (
    <div className={compact ? "space-y-3" : "space-y-4"}>
      {model.projects.map((item, index) => (
        <div key={`${item.title}-${index}`}>
          <div
            className={compact ? "text-xs font-semibold" : "text-sm font-semibold"}
            style={{ color: model.palette.text }}
          >
            {item.title}
          </div>
          {item.period ? (
            <div className="text-[11px]" style={{ color: model.palette.muted }}>
              {item.period}
            </div>
          ) : null}
          {item.bullets.length ? (
            <div className="mt-1 space-y-1.5">
              {item.bullets.map((bullet, bulletIndex) => (
                <div
                  className={compact ? "text-[11px] leading-5" : "text-xs leading-5"}
                  key={`${item.title}-${bulletIndex}`}
                  style={{ color: model.palette.text }}
                >
                  - {bullet}
                </div>
              ))}
            </div>
          ) : null}
        </div>
      ))}
    </div>
  );
}

function CustomSectionList({ section, model, compact = false }) {
  if (!section?.bullets?.length) {
    return null;
  }
  return (
    <div className={compact ? "space-y-1" : "space-y-1.5"}>
      {section.bullets.map((line, index) => (
        <div
          className={compact ? "text-[11px] leading-5" : "text-xs leading-5"}
          key={`${section.id}-${index}`}
          style={{ color: model.palette.text }}
        >
          - {line}
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
        {model.projects.length ? (
          <div>
            <SectionHeading label="Projects" palette={model.palette} templateId={model.template.id} />
            <ProjectList model={model} />
          </div>
        ) : null}
        {model.customSections.map((section) => (
          <div key={section.id}>
            <SectionHeading label={section.heading} palette={model.palette} templateId={model.template.id} />
            <CustomSectionList model={model} section={section} />
          </div>
        ))}
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
        {model.projects.length ? (
          <div
            className="rounded-xl border p-4"
            style={{ borderColor: model.palette.softBorder, backgroundColor: "#FFFFFF" }}
          >
            <div className="text-sm font-semibold" style={{ color: model.palette.primary }}>
              Projects
            </div>
            <div className="mt-3">
              <ProjectList model={model} />
            </div>
          </div>
        ) : null}
        {model.customSections.map((section) => (
          <div
            className="rounded-xl border p-4"
            key={section.id}
            style={{ borderColor: model.palette.softBorder, backgroundColor: "#FFFFFF" }}
          >
            <div className="text-sm font-semibold" style={{ color: model.palette.primary }}>
              {section.heading}
            </div>
            <div className="mt-3">
              <CustomSectionList model={model} section={section} />
            </div>
          </div>
        ))}
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
              {model.skills.map((item) => (
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
        {model.projects.length ? (
          <div>
            <SectionHeading label="Projects" palette={model.palette} templateId={model.template.id} />
            <ProjectList compact model={model} />
          </div>
        ) : null}
        {model.customSections.map((section) => (
          <div key={section.id}>
            <SectionHeading label={section.heading} palette={model.palette} templateId={model.template.id} />
            <CustomSectionList compact model={model} section={section} />
          </div>
        ))}
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
    ...(model.projects.length
      ? [
          {
            label: "Projects",
            content: <ProjectList compact model={model} />,
          },
        ]
      : []),
    ...model.customSections.map((section) => ({
      label: section.heading,
      content: <CustomSectionList compact model={model} section={section} />,
    })),
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
      <div className="border-b-[3px] pb-2" style={{ borderColor: model.palette.accent }}>
        <div className="text-[28px] font-normal leading-none" style={{ color: model.palette.primary }}>
          {model.name}
        </div>
      </div>
      {model.contacts.length ? (
        <div className="text-[11px] leading-5" style={{ color: model.palette.text }}>
          {model.contacts.join(" | ")}
        </div>
      ) : null}

      <div>
        <div className="mb-2 text-base font-bold" style={{ color: model.palette.primary }}>
          Profile
        </div>
        <div className="text-xs leading-5" style={{ color: model.palette.text }}>
          {model.summary}
        </div>
      </div>
      <div>
        <div className="mb-2 text-base font-bold" style={{ color: model.palette.primary }}>
          Experience
        </div>
        <div className="space-y-3">
          {model.experience.map((item, index) => (
            <div key={`${item.title}-${index}`}>
              <div className="text-xs font-bold uppercase" style={{ color: model.palette.text }}>
                {[item.title, item.company, item.period].filter(Boolean).join(" | ")}
              </div>
              <div className="mt-1 space-y-1">
                {(item.bullets.length ? item.bullets : ["Role-specific accomplishment preview"]).map((bullet) => (
                  <div className="text-[11px] leading-5" key={bullet} style={{ color: model.palette.text }}>
                    - {bullet}
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>
      <div>
        <div className="mb-2 text-base font-bold" style={{ color: model.palette.primary }}>
          Education
        </div>
        <div className="space-y-1 text-xs font-semibold uppercase leading-5" style={{ color: model.palette.text }}>
          {model.education.map((item) => (
            <div key={item}>{item}</div>
          ))}
        </div>
      </div>
      <div>
        <div className="mb-2 text-base font-bold" style={{ color: model.palette.primary }}>
          Skills &amp; Abilities
        </div>
        <div className="text-xs leading-5" style={{ color: model.palette.text }}>
          {model.skills.join(" | ")}
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
      style={{ borderColor: model.palette.softBorder }}
    >
      <AtsExportFlow documents={documents} model={model} />
      {content}
    </div>
  );
}
