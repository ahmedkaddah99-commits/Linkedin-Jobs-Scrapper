export const CV_STUDIO_ROUTE = "/cv-studio";
export const CV_STUDIO_SETTINGS_SEED_KEY = "runr.cvStudio.seed";
export const CV_STUDIO_SESSION_KEY = "runr.cvStudio.session";

export const DEFAULT_WEB_CV_PALETTE = {
  primary: "17324D",
  accent: "D97706",
  surface: "F8FAFC",
  text: "0F172A",
  muted: "475569",
  border: "CBD5E1",
};

export const WEB_CV_COLOR_FIELDS = [
  { id: "primary", label: "Primary", description: "Headers and dividers" },
  { id: "accent", label: "Accent", description: "Highlights and badges" },
  { id: "surface", label: "Surface", description: "Cards and soft backgrounds" },
  { id: "text", label: "Text", description: "Main body text" },
  { id: "muted", label: "Muted", description: "Secondary labels" },
  { id: "border", label: "Border", description: "Rules and outlines" },
];

export const WEB_CV_COLOR_PRESETS = [
  {
    id: "navy_amber",
    label: "Navy and Amber",
    palette: {
      primary: "17324D",
      accent: "D97706",
      surface: "F8FAFC",
      text: "0F172A",
      muted: "475569",
      border: "CBD5E1",
    },
  },
  {
    id: "forest_mint",
    label: "Forest and Mint",
    palette: {
      primary: "1F4D3B",
      accent: "2BB5A8",
      surface: "F3FBF8",
      text: "10231E",
      muted: "42695C",
      border: "C8E4D8",
    },
  },
  {
    id: "ink_coral",
    label: "Ink and Coral",
    palette: {
      primary: "1E293B",
      accent: "F97360",
      surface: "FFF7F5",
      text: "0F172A",
      muted: "5B6472",
      border: "FED7D2",
    },
  },
  {
    id: "stone_blue",
    label: "Stone and Blue",
    palette: {
      primary: "334155",
      accent: "3B82F6",
      surface: "F8FAFC",
      text: "111827",
      muted: "667085",
      border: "D7E2F1",
    },
  },
  {
    id: "sand_burgundy",
    label: "Sand and Burgundy",
    palette: {
      primary: "6B2230",
      accent: "C77852",
      surface: "FFF8F2",
      text: "22161A",
      muted: "6E5459",
      border: "E8D5CB",
    },
  },
];

export const WEB_CV_TEMPLATES = [
  {
    id: "ats_single_column",
    label: "ATS Single Column",
    shortLabel: "ATS",
    description: "Clean linear structure for fast tailoring and ATS-safe export.",
    mood: "Direct, robust, low-risk",
  },
  {
    id: "editorial_sidebar",
    label: "Editorial Sidebar",
    shortLabel: "Sidebar",
    description: "Elegant left rail with a soft editorial hierarchy.",
    mood: "Balanced, polished, readable",
  },
  {
    id: "mono_nav",
    label: "Mono Nav",
    shortLabel: "Mono",
    description: "Modern left navigation strip with a compact content flow.",
    mood: "Modern, compact, focused",
  },
  {
    id: "europass_lite",
    label: "Europass Lite",
    shortLabel: "EU",
    description: "Europe-friendly structure without the heavy default Europass look.",
    mood: "Familiar, structured, practical",
  },
  {
    id: "signal_header",
    label: "Signal Header",
    shortLabel: "Signal",
    description: "Bold banner header with confident section grouping.",
    mood: "Strong, modern, expressive",
  },
  {
    id: "ledger_split",
    label: "Ledger Split",
    shortLabel: "Ledger",
    description: "Asymmetric grid with compact detail blocks and dense experience flow.",
    mood: "Sharp, technical, dense",
  },
];

function emptyExperienceItem() {
  return {
    title: "",
    company: "",
    period: "",
    bulletsText: "",
  };
}

function safeJsonParse(rawValue, fallback) {
  try {
    return rawValue ? JSON.parse(rawValue) : fallback;
  } catch {
    return fallback;
  }
}

export function normalizeHexColor(value, fallback = DEFAULT_WEB_CV_PALETTE.primary) {
  const normalized = String(value || "")
    .trim()
    .replace(/^#/, "")
    .toUpperCase();
  return /^[0-9A-F]{6}$/.test(normalized) ? normalized : fallback;
}

export function normalizePalette(value) {
  const rawPalette = value && typeof value === "object" ? value : {};
  return Object.fromEntries(
    WEB_CV_COLOR_FIELDS.map((field) => [
      field.id,
      normalizeHexColor(rawPalette[field.id], DEFAULT_WEB_CV_PALETTE[field.id]),
    ]),
  );
}

export function findCvTemplate(templateId) {
  return (
    WEB_CV_TEMPLATES.find((template) => template.id === templateId) ||
    WEB_CV_TEMPLATES[0]
  );
}

export function findColorPreset(presetId) {
  return (
    WEB_CV_COLOR_PRESETS.find((preset) => preset.id === presetId) ||
    WEB_CV_COLOR_PRESETS[0]
  );
}

export function matchPresetByPalette(palette) {
  const normalized = normalizePalette(palette);
  return (
    WEB_CV_COLOR_PRESETS.find((preset) =>
      WEB_CV_COLOR_FIELDS.every(
        (field) => preset.palette[field.id] === normalized[field.id],
      ),
    ) || null
  );
}

export function stashCvStudioSeed(seed) {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(
    CV_STUDIO_SETTINGS_SEED_KEY,
    JSON.stringify({
      savedAt: Date.now(),
      payload: seed,
    }),
  );
}

export function consumeCvStudioSeed(maxAgeMs = 10 * 60 * 1000) {
  if (typeof window === "undefined") return null;
  const parsed = safeJsonParse(
    window.localStorage.getItem(CV_STUDIO_SETTINGS_SEED_KEY),
    null,
  );
  window.localStorage.removeItem(CV_STUDIO_SETTINGS_SEED_KEY);
  if (!parsed || typeof parsed !== "object") return null;
  const savedAt = Number(parsed.savedAt || 0);
  if (!savedAt || Date.now() - savedAt > maxAgeMs) return null;
  return parsed.payload || null;
}

export function loadCvStudioSession() {
  if (typeof window === "undefined") return null;
  return safeJsonParse(window.localStorage.getItem(CV_STUDIO_SESSION_KEY), null);
}

export function saveCvStudioSession(session) {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(CV_STUDIO_SESSION_KEY, JSON.stringify(session));
}

function normalizeExperienceItems(rawItems) {
  const items = Array.isArray(rawItems) ? rawItems : [];
  const normalizedItems = items
    .filter((item) => item && typeof item === "object")
    .map((item) => ({
      title: String(item.title || ""),
      company: String(item.company || ""),
      period: String(item.period || ""),
      bulletsText: String(item.bulletsText || ""),
    }));
  return normalizedItems.length ? normalizedItems : [emptyExperienceItem()];
}

export function buildCvStudioState(profile = {}, documents = {}, sessionDraft = {}) {
  const normalizedDocuments = documents && typeof documents === "object" ? documents : {};
  const baseState = {
    templateId: String(
      normalizedDocuments.web_cv_template || normalizedDocuments.cv_template || WEB_CV_TEMPLATES[0].id,
    ),
    fontFamily: String(
      normalizedDocuments.web_cv_font || normalizedDocuments.cv_font || "Aptos",
    ),
    showPhoto:
      normalizedDocuments.web_cv_show_photo ??
      normalizedDocuments.include_photo ??
      true,
    palette: normalizePalette(normalizedDocuments.web_cv_palette || {}),
    name: String(profile.name || ""),
    headline: String(profile.role_title || ""),
    targetRole: "",
    targetCompany: "",
    location: String(profile.location || ""),
    email: String(profile.email || ""),
    website: String(profile.website || ""),
    linkedin: String(profile.linkedin_url || ""),
    github: String(profile.github_url || ""),
    summary: String(profile.summary || ""),
    skillsText: Array.isArray(profile.competencies) ? profile.competencies.join("\n") : "",
    languagesText: Array.isArray(profile.languages) ? profile.languages.join("\n") : "",
    availability: "Available immediately for tailored roles.",
    educationText: "",
    experience: normalizeExperienceItems(
      Array.isArray(profile.recent_experience)
        ? profile.recent_experience.map((item) => ({
            title: item.title || "",
            company: item.company || "",
            period: item.period || "",
            bulletsText: "",
          }))
        : [],
    ),
    photoDataUrl: String(profile.photo_data_url || profile.avatar_url || ""),
  };

  const normalizedSession = sessionDraft && typeof sessionDraft === "object" ? sessionDraft : {};

  return {
    ...baseState,
    ...normalizedSession,
    templateId: findCvTemplate(normalizedSession.templateId || baseState.templateId).id,
    fontFamily: String(normalizedSession.fontFamily || baseState.fontFamily || "Aptos"),
    showPhoto:
      typeof normalizedSession.showPhoto === "boolean"
        ? normalizedSession.showPhoto
        : Boolean(baseState.showPhoto),
    palette: normalizePalette(normalizedSession.palette || baseState.palette),
    experience: normalizeExperienceItems(normalizedSession.experience || baseState.experience),
  };
}

export function buildStudioDocumentPatch(state) {
  return {
    web_cv_template: findCvTemplate(state.templateId).id,
    web_cv_font: String(state.fontFamily || "Aptos"),
    web_cv_show_photo: Boolean(state.showPhoto),
    web_cv_palette: normalizePalette(state.palette || {}),
  };
}

function escapeHtml(value) {
  return String(value || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function toList(value) {
  if (Array.isArray(value)) {
    return value
      .map((item) => String(item || "").trim())
      .filter(Boolean);
  }
  return String(value || "")
    .split(/\r?\n|[,;|]/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function normalizeModel(state) {
  const experience = normalizeExperienceItems(state.experience).map((item) => ({
    title: String(item.title || ""),
    company: String(item.company || ""),
    period: String(item.period || ""),
    bullets: String(item.bulletsText || "")
      .split(/\r?\n/)
      .map((entry) => entry.replace(/^\s*[-*]\s*/, "").trim())
      .filter(Boolean),
  }));

  return {
    templateId: findCvTemplate(state.templateId).id,
    template: findCvTemplate(state.templateId),
    palette: normalizePalette(state.palette || {}),
    fontFamily: String(state.fontFamily || "Aptos"),
    showPhoto: Boolean(state.showPhoto),
    name: String(state.name || "Candidate Name"),
    headline: String(state.headline || "Target Role"),
    targetRole: String(state.targetRole || ""),
    targetCompany: String(state.targetCompany || ""),
    location: String(state.location || ""),
    email: String(state.email || ""),
    website: String(state.website || ""),
    linkedin: String(state.linkedin || ""),
    github: String(state.github || ""),
    summary: String(state.summary || ""),
    skills: toList(state.skillsText),
    languages: toList(state.languagesText),
    availability: String(state.availability || ""),
    educationLines: String(state.educationText || "")
      .split(/\r?\n/)
      .map((entry) => entry.trim())
      .filter(Boolean),
    experience,
    photoDataUrl: String(state.photoDataUrl || ""),
  };
}

function buildContactLinks(model, className = "contact-list") {
  const items = [];
  if (model.location) items.push(`<span>${escapeHtml(model.location)}</span>`);
  if (model.email) {
    items.push(
      `<a href="mailto:${escapeHtml(model.email)}">${escapeHtml(model.email)}</a>`,
    );
  }
  if (model.website) {
    items.push(
      `<a href="${escapeHtml(model.website)}">${escapeHtml(model.website)}</a>`,
    );
  }
  if (model.linkedin) {
    items.push(`<a href="${escapeHtml(model.linkedin)}">LinkedIn</a>`);
  }
  if (model.github) {
    items.push(`<a href="${escapeHtml(model.github)}">GitHub</a>`);
  }
  return `<div class="${className}">${items.join("")}</div>`;
}

function buildPhotoMarkup(model, photoClass = "cv-photo-shell") {
  if (!model.showPhoto) return "";
  if (model.photoDataUrl) {
    return `<div class="${photoClass}"><img class="cv-photo" src="${escapeHtml(model.photoDataUrl)}" alt="Candidate profile photo"></div>`;
  }
  return `<div class="${photoClass} cv-photo-placeholder"><span>Optional photo</span></div>`;
}

function buildSection(title, content, subtitle = "") {
  return `
    <section class="cv-section">
      <div class="cv-section-head">
        <h2>${escapeHtml(title)}</h2>
        ${subtitle ? `<p>${escapeHtml(subtitle)}</p>` : ""}
      </div>
      <div class="cv-section-body">${content}</div>
    </section>
  `;
}

function buildSkillsMarkup(model, chipClass = "pill") {
  if (!model.skills.length) {
    return `<p class="empty-note">Add skills or keywords in the editor.</p>`;
  }
  return `<div class="pill-row">${model.skills
    .map((skill) => `<span class="${chipClass}">${escapeHtml(skill)}</span>`)
    .join("")}</div>`;
}

function buildLanguagesMarkup(model) {
  if (!model.languages.length) return "";
  return `
    <div class="meta-stack">
      <div class="mini-label">Languages</div>
      <div class="pill-row">
        ${model.languages
          .map((language) => `<span class="pill subtle-pill">${escapeHtml(language)}</span>`)
          .join("")}
      </div>
    </div>
  `;
}

function buildEducationMarkup(model) {
  if (!model.educationLines.length) {
    return `<p class="empty-note">Add education, certificates, or training lines.</p>`;
  }
  return model.educationLines
    .map((line) => `<p class="education-line">${escapeHtml(line)}</p>`)
    .join("");
}

function buildExperienceMarkup(model, className = "experience-stack") {
  return `
    <div class="${className}">
      ${model.experience
        .map((item) => {
          const heading = [item.title, item.company].filter(Boolean).join(" - ");
          const bullets = item.bullets.length
            ? `<ul>${item.bullets.map((bullet) => `<li>${escapeHtml(bullet)}</li>`).join("")}</ul>`
            : `<p class="empty-note">Add tailored achievement bullets for this role.</p>`;
          return `
            <article class="experience-card">
              <div class="experience-head">
                <div>
                  <h3>${escapeHtml(heading || "Experience Item")}</h3>
                  ${item.company && item.title ? "" : ""}
                </div>
                ${item.period ? `<span class="period">${escapeHtml(item.period)}</span>` : ""}
              </div>
              ${bullets}
            </article>
          `;
        })
        .join("")}
    </div>
  `;
}

function buildTargetBanner(model) {
  if (!model.targetRole && !model.targetCompany) return "";
  return `
    <div class="target-banner">
      <span>${escapeHtml(model.targetRole || "Tailored role")}</span>
      ${
        model.targetCompany
          ? `<span class="target-company">${escapeHtml(model.targetCompany)}</span>`
          : ""
      }
    </div>
  `;
}

function buildSummaryMarkup(model) {
  return model.summary
    ? `<p class="summary-copy">${escapeHtml(model.summary)}</p>`
    : `<p class="empty-note">Add a role-specific summary and value proposition.</p>`;
}

function buildFooterMeta(model) {
  const parts = [];
  if (model.availability) {
    parts.push(`
      <div class="meta-stack">
        <div class="mini-label">Availability</div>
        <p>${escapeHtml(model.availability)}</p>
      </div>
    `);
  }
  const languagesBlock = buildLanguagesMarkup(model);
  if (languagesBlock) parts.push(languagesBlock);
  return parts.join("");
}

function templateAtsSingleColumn(model) {
  return `
    <main class="cv-sheet template-ats">
      <header class="hero-row">
        <div class="hero-copy">
          <div class="eyebrow">Browser CV Studio</div>
          <h1>${escapeHtml(model.name)}</h1>
          <p class="headline">${escapeHtml(model.headline)}</p>
          ${buildTargetBanner(model)}
        </div>
        ${buildPhotoMarkup(model, "cv-photo-shell rounded-photo")}
      </header>
      ${buildContactLinks(model)}
      ${buildSection("Professional Summary", buildSummaryMarkup(model))}
      ${buildSection("Core Skills", buildSkillsMarkup(model))}
      ${buildSection("Experience", buildExperienceMarkup(model))}
      <div class="two-up">
        ${buildSection("Education", buildEducationMarkup(model))}
        ${buildSection("Additional", buildFooterMeta(model) || `<p class="empty-note">Add languages or availability.</p>`)}
      </div>
    </main>
  `;
}

function templateEditorialSidebar(model) {
  return `
    <main class="cv-sheet template-editorial">
      <aside class="editorial-rail">
        ${buildPhotoMarkup(model, "cv-photo-shell editorial-photo")}
        <div class="eyebrow">Tailored profile</div>
        <h1>${escapeHtml(model.name)}</h1>
        <p class="headline">${escapeHtml(model.headline)}</p>
        ${buildTargetBanner(model)}
        ${buildContactLinks(model, "contact-list contact-list-column")}
        ${buildSection("Skills", buildSkillsMarkup(model, "pill rail-pill"))}
        ${buildSection("Additional", buildFooterMeta(model) || `<p class="empty-note">Add languages or availability.</p>`)}
      </aside>
      <section class="editorial-main">
        ${buildSection("Summary", buildSummaryMarkup(model))}
        ${buildSection("Experience", buildExperienceMarkup(model))}
        ${buildSection("Education", buildEducationMarkup(model))}
      </section>
    </main>
  `;
}

function templateMonoNav(model) {
  return `
    <main class="cv-sheet template-mono">
      <div class="mono-rail">
        <div class="mono-badge">${escapeHtml(model.template.shortLabel)}</div>
        ${buildPhotoMarkup(model, "cv-photo-shell mono-photo")}
        <div class="mono-links">
          ${buildContactLinks(model, "contact-list contact-list-column")}
        </div>
      </div>
      <section class="mono-main">
        <div class="mono-hero">
          <div>
            <div class="eyebrow">In-browser editable CV</div>
            <h1>${escapeHtml(model.name)}</h1>
            <p class="headline">${escapeHtml(model.headline)}</p>
          </div>
          ${buildTargetBanner(model)}
        </div>
        ${buildSection("Summary", buildSummaryMarkup(model))}
        <div class="two-up mono-grid">
          ${buildSection("Skills", buildSkillsMarkup(model))}
          ${buildSection("Education", buildEducationMarkup(model))}
        </div>
        ${buildSection("Experience", buildExperienceMarkup(model))}
        ${buildFooterMeta(model) ? `<div class="mono-footer-meta">${buildFooterMeta(model)}</div>` : ""}
      </section>
    </main>
  `;
}

function templateEuropassLite(model) {
  return `
    <main class="cv-sheet template-europass">
      <header class="europass-head">
        <div>
          <div class="eyebrow">Europass-inspired</div>
          <h1>${escapeHtml(model.name)}</h1>
          <p class="headline">${escapeHtml(model.headline)}</p>
          ${buildTargetBanner(model)}
        </div>
        ${buildPhotoMarkup(model, "cv-photo-shell europass-photo")}
      </header>
      <div class="europass-grid">
        <div class="label-col">Contact</div>
        <div>${buildContactLinks(model)}</div>
        <div class="label-col">Profile</div>
        <div>${buildSummaryMarkup(model)}</div>
        <div class="label-col">Skills</div>
        <div>${buildSkillsMarkup(model)}</div>
        <div class="label-col">Experience</div>
        <div>${buildExperienceMarkup(model)}</div>
        <div class="label-col">Education</div>
        <div>${buildEducationMarkup(model)}</div>
        <div class="label-col">Additional</div>
        <div>${buildFooterMeta(model) || `<p class="empty-note">Add languages or availability.</p>`}</div>
      </div>
    </main>
  `;
}

function templateSignalHeader(model) {
  return `
    <main class="cv-sheet template-signal">
      <header class="signal-band">
        <div class="signal-copy">
          <div class="eyebrow light">Browser CV Studio</div>
          <h1>${escapeHtml(model.name)}</h1>
          <p class="headline light">${escapeHtml(model.headline)}</p>
          ${buildTargetBanner(model)}
        </div>
        ${buildPhotoMarkup(model, "cv-photo-shell signal-photo")}
      </header>
      <section class="signal-contact-wrap">
        ${buildContactLinks(model)}
      </section>
      <div class="two-up signal-body">
        <div>
          ${buildSection("Summary", buildSummaryMarkup(model))}
          ${buildSection("Skills", buildSkillsMarkup(model))}
          ${buildSection("Education", buildEducationMarkup(model))}
        </div>
        <div>
          ${buildSection("Experience", buildExperienceMarkup(model))}
          ${buildSection("Additional", buildFooterMeta(model) || `<p class="empty-note">Add languages or availability.</p>`)}
        </div>
      </div>
    </main>
  `;
}

function templateLedgerSplit(model) {
  return `
    <main class="cv-sheet template-ledger">
      <header class="ledger-head">
        <div>
          <div class="eyebrow">Editable HTML CV</div>
          <h1>${escapeHtml(model.name)}</h1>
          <p class="headline">${escapeHtml(model.headline)}</p>
          ${buildTargetBanner(model)}
        </div>
        <div class="ledger-side">
          ${buildPhotoMarkup(model, "cv-photo-shell ledger-photo")}
          ${buildContactLinks(model, "contact-list contact-list-column compact-links")}
        </div>
      </header>
      <div class="ledger-grid">
        <div>
          ${buildSection("Summary", buildSummaryMarkup(model))}
          ${buildSection("Skills", buildSkillsMarkup(model))}
          ${buildSection("Additional", buildFooterMeta(model) || `<p class="empty-note">Add languages or availability.</p>`)}
        </div>
        <div>
          ${buildSection("Experience", buildExperienceMarkup(model))}
          ${buildSection("Education", buildEducationMarkup(model))}
        </div>
      </div>
    </main>
  `;
}

function renderTemplate(model) {
  switch (model.templateId) {
    case "editorial_sidebar":
      return templateEditorialSidebar(model);
    case "mono_nav":
      return templateMonoNav(model);
    case "europass_lite":
      return templateEuropassLite(model);
    case "signal_header":
      return templateSignalHeader(model);
    case "ledger_split":
      return templateLedgerSplit(model);
    case "ats_single_column":
    default:
      return templateAtsSingleColumn(model);
  }
}

function buildBaseCss(model, { forIframe = false } = {}) {
  const palette = model.palette;
  const background = forIframe ? "#EEF3F8" : "#E8EEF5";
  return `
    :root {
      color-scheme: light;
      --cv-primary: #${palette.primary};
      --cv-accent: #${palette.accent};
      --cv-surface: #${palette.surface};
      --cv-text: #${palette.text};
      --cv-muted: #${palette.muted};
      --cv-border: #${palette.border};
    }
    * { box-sizing: border-box; }
    html, body {
      margin: 0;
      padding: 0;
      background: ${background};
      color: var(--cv-text);
      font-family: ${JSON.stringify(model.fontFamily)}, "Segoe UI", Arial, sans-serif;
      line-height: 1.55;
      -webkit-print-color-adjust: exact;
      print-color-adjust: exact;
    }
    body {
      padding: 18px;
    }
    a {
      color: inherit;
      text-decoration-thickness: 1px;
      text-underline-offset: 0.14em;
    }
    h1, h2, h3, p, ul {
      margin: 0;
    }
    .cv-sheet {
      width: 210mm;
      min-height: 297mm;
      margin: 0 auto;
      padding: 18mm 16mm;
      background: white;
      box-shadow: 0 28px 60px rgba(15, 23, 42, 0.12);
    }
    .hero-row,
    .ledger-head,
    .europass-head {
      display: flex;
      justify-content: space-between;
      gap: 18px;
      align-items: flex-start;
    }
    .hero-copy h1,
    .signal-copy h1,
    .mono-main h1,
    .ledger-head h1,
    .europass-head h1,
    .editorial-rail h1 {
      font-size: 2.15rem;
      line-height: 1;
      letter-spacing: -0.03em;
    }
    .eyebrow {
      margin-bottom: 10px;
      font-size: 0.72rem;
      font-weight: 800;
      letter-spacing: 0.18em;
      text-transform: uppercase;
      color: var(--cv-accent);
    }
    .eyebrow.light,
    .headline.light {
      color: rgba(255, 255, 255, 0.88);
    }
    .headline {
      margin-top: 10px;
      font-size: 1rem;
      color: var(--cv-muted);
    }
    .target-banner {
      display: inline-flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-top: 14px;
      padding: 8px 12px;
      border-radius: 999px;
      background: color-mix(in srgb, var(--cv-accent) 14%, white);
      color: var(--cv-primary);
      font-size: 0.82rem;
      font-weight: 700;
    }
    .target-company {
      color: var(--cv-muted);
    }
    .contact-list {
      display: flex;
      flex-wrap: wrap;
      gap: 10px 14px;
      margin-top: 14px;
      color: var(--cv-muted);
      font-size: 0.9rem;
    }
    .contact-list-column {
      display: grid;
      gap: 8px;
      margin-top: 14px;
    }
    .cv-photo-shell {
      width: 34mm;
      min-width: 34mm;
      height: 44mm;
      border-radius: 16px;
      overflow: hidden;
      border: 1px solid var(--cv-border);
      background: linear-gradient(180deg, var(--cv-surface), white);
      display: flex;
      align-items: center;
      justify-content: center;
    }
    .cv-photo {
      width: 100%;
      height: 100%;
      object-fit: cover;
      display: block;
    }
    .cv-photo-placeholder {
      border-style: dashed;
      color: var(--cv-muted);
      font-size: 0.72rem;
      font-weight: 800;
      text-transform: uppercase;
      letter-spacing: 0.12em;
      text-align: center;
      padding: 12px;
    }
    .rounded-photo,
    .signal-photo,
    .mono-photo {
      border-radius: 20px;
    }
    .cv-section {
      margin-top: 18px;
    }
    .cv-section-head {
      display: flex;
      flex-wrap: wrap;
      justify-content: space-between;
      gap: 10px;
      padding-bottom: 8px;
      border-bottom: 1px solid var(--cv-border);
    }
    .cv-section-head h2,
    .label-col {
      font-size: 0.76rem;
      font-weight: 900;
      letter-spacing: 0.18em;
      text-transform: uppercase;
      color: var(--cv-primary);
    }
    .cv-section-head p {
      color: var(--cv-muted);
      font-size: 0.82rem;
    }
    .cv-section-body {
      padding-top: 10px;
    }
    .summary-copy,
    .education-line,
    .meta-stack p {
      color: var(--cv-text);
      font-size: 0.95rem;
    }
    .empty-note {
      color: var(--cv-muted);
      font-style: italic;
    }
    .pill-row {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
    }
    .pill {
      display: inline-flex;
      align-items: center;
      padding: 6px 10px;
      border-radius: 999px;
      background: var(--cv-surface);
      border: 1px solid var(--cv-border);
      font-size: 0.82rem;
      font-weight: 700;
    }
    .subtle-pill {
      background: white;
    }
    .experience-stack {
      display: grid;
      gap: 14px;
    }
    .experience-card {
      padding: 12px 14px;
      border-radius: 14px;
      border: 1px solid var(--cv-border);
      background: linear-gradient(180deg, white, color-mix(in srgb, var(--cv-surface) 55%, white));
    }
    .experience-head {
      display: flex;
      justify-content: space-between;
      gap: 10px;
      align-items: baseline;
      margin-bottom: 8px;
    }
    .experience-head h3 {
      font-size: 1rem;
      color: var(--cv-primary);
    }
    .period {
      color: var(--cv-muted);
      font-size: 0.82rem;
      font-weight: 700;
      white-space: nowrap;
    }
    ul {
      padding-left: 18px;
    }
    li + li {
      margin-top: 5px;
    }
    .two-up {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 18px;
    }
    .mini-label {
      margin-bottom: 8px;
      color: var(--cv-primary);
      font-size: 0.72rem;
      font-weight: 800;
      letter-spacing: 0.12em;
      text-transform: uppercase;
    }
    .meta-stack + .meta-stack {
      margin-top: 14px;
    }
    .template-editorial {
      display: grid;
      grid-template-columns: 68mm minmax(0, 1fr);
      gap: 14mm;
      background:
        linear-gradient(90deg, color-mix(in srgb, var(--cv-surface) 85%, white) 0, color-mix(in srgb, var(--cv-surface) 85%, white) 68mm, white 68mm, white 100%);
    }
    .editorial-rail {
      padding-right: 6px;
    }
    .editorial-main {
      padding-top: 2px;
    }
    .rail-pill {
      background: white;
    }
    .template-mono {
      display: grid;
      grid-template-columns: 40mm minmax(0, 1fr);
      gap: 12mm;
    }
    .mono-rail {
      padding-right: 10px;
      border-right: 1px solid var(--cv-border);
    }
    .mono-badge {
      display: inline-flex;
      margin-bottom: 16px;
      padding: 6px 10px;
      border-radius: 999px;
      background: var(--cv-primary);
      color: white;
      font-size: 0.74rem;
      font-weight: 800;
      letter-spacing: 0.12em;
      text-transform: uppercase;
    }
    .mono-hero {
      display: flex;
      justify-content: space-between;
      gap: 16px;
      align-items: flex-start;
    }
    .mono-footer-meta {
      margin-top: 18px;
      padding-top: 14px;
      border-top: 1px solid var(--cv-border);
    }
    .template-europass .europass-grid {
      display: grid;
      grid-template-columns: 34mm minmax(0, 1fr);
      gap: 12px 18px;
      margin-top: 16px;
    }
    .template-europass .label-col {
      padding-top: 4px;
    }
    .template-europass .contact-list {
      margin-top: 0;
    }
    .template-signal {
      padding-top: 0;
      overflow: hidden;
    }
    .signal-band {
      display: flex;
      justify-content: space-between;
      gap: 18px;
      align-items: flex-start;
      margin: 0 -16mm 18px;
      padding: 18mm 16mm 14mm;
      background:
        radial-gradient(circle at top right, color-mix(in srgb, var(--cv-accent) 30%, transparent), transparent 36%),
        linear-gradient(135deg, var(--cv-primary), color-mix(in srgb, var(--cv-primary) 86%, black));
      color: white;
    }
    .signal-contact-wrap {
      margin-top: -2px;
    }
    .template-ledger .ledger-head {
      padding-bottom: 16px;
      border-bottom: 2px solid var(--cv-primary);
    }
    .ledger-side {
      display: grid;
      gap: 10px;
      justify-items: end;
    }
    .compact-links {
      margin-top: 0;
      text-align: right;
      font-size: 0.84rem;
    }
    .ledger-grid {
      display: grid;
      grid-template-columns: 0.85fr 1.15fr;
      gap: 18px;
      margin-top: 6px;
    }
    @media (max-width: 1000px) {
      body {
        padding: 0;
        background: white;
      }
      .cv-sheet {
        width: 100%;
        min-height: auto;
        box-shadow: none;
        padding: 24px 20px;
      }
      .template-editorial,
      .template-mono,
      .ledger-grid,
      .template-europass .europass-grid,
      .two-up {
        grid-template-columns: 1fr;
      }
      .template-editorial {
        background: white;
      }
      .mono-rail {
        border-right: 0;
        border-bottom: 1px solid var(--cv-border);
        padding-bottom: 14px;
      }
      .signal-band,
      .hero-row,
      .ledger-head,
      .europass-head,
      .mono-hero {
        flex-direction: column;
      }
      .compact-links {
        text-align: left;
      }
    }
    @media print {
      html, body {
        background: white;
      }
      body {
        padding: 0;
      }
      .cv-sheet {
        width: auto;
        min-height: auto;
        margin: 0;
        box-shadow: none;
      }
      @page {
        size: A4;
        margin: 10mm;
      }
    }
  `;
}

export function buildCvStudioHtml(state, options = {}) {
  const model = normalizeModel(state);
  const titleParts = [
    model.name,
    model.targetRole || model.headline || "CV",
    model.targetCompany,
  ].filter(Boolean);
  return `<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>${escapeHtml(titleParts.join(" - "))}</title>
  <style>
    ${buildBaseCss(model, options)}
  </style>
</head>
<body>
  ${renderTemplate(model)}
</body>
</html>`;
}
