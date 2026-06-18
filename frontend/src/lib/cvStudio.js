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

export const PLAIN_RESUME_DEFAULT_PALETTE = {
  primary: "2A7B88",
  accent: "39A5B7",
  surface: "FFFFFF",
  text: "262626",
  muted: "4B5563",
  border: "39A5B7",
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
    id: "resume_teal",
    label: "Resume Teal",
    palette: { ...PLAIN_RESUME_DEFAULT_PALETTE },
  },
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
  {
    id: "plain",
    label: "Plain",
    shortLabel: "Plain",
    description: "Photo-free classic resume with a configurable name rule and compact skills.",
    mood: "Classic, polished, approachable",
  },
];

const DOCX_TO_WEB_TEMPLATE_MAP = {
  teal_resume: "plain",
  classic: "ats_single_column",
  modern: "signal_header",
  compact: "mono_nav",
  europass: "europass_lite",
  plain: "plain",
};

const DOCX_COLOR_SCHEME_TO_WEB_PALETTE = {
  classic_navy: {
    primary: "1F3A5F",
    accent: "2EC4B6",
    surface: "EAF3FF",
    text: "0F172A",
    muted: "475569",
    border: "CBD5E1",
  },
  ocean_teal: {
    primary: "006B5F",
    accent: "14B8A6",
    surface: "E5FFFB",
    text: "10231E",
    muted: "42756E",
    border: "B8E9E2",
  },
  forest: {
    primary: "2F5D50",
    accent: "8AA06F",
    surface: "F0F7F3",
    text: "13201A",
    muted: "4C675B",
    border: "CFE0D4",
  },
  slate: {
    primary: "334155",
    accent: "60A5FA",
    surface: "EEF2FF",
    text: "0F172A",
    muted: "5B6472",
    border: "D4DBF3",
  },
  burgundy: {
    primary: "7C2D12",
    accent: "EA580C",
    surface: "FFF1EB",
    text: "2B1711",
    muted: "7B5B51",
    border: "F2D3C6",
  },
  charcoal: {
    primary: "111827",
    accent: "6B7280",
    surface: "F3F4F6",
    text: "111827",
    muted: "4B5563",
    border: "D1D5DB",
  },
};

const CV_EXPORT_LABELS = {
  English: {
    additional: "Additional",
    availability: "Availability",
    browserCvStudio: "Browser CV Studio",
    contact: "Contact",
    coreSkills: "Core Skills",
    editableHtmlCv: "Editable HTML CV",
    education: "Education",
    europassInspired: "Europass-inspired",
    experience: "Experience",
    experienceItem: "Experience Item",
    inBrowserEditableCv: "In-browser editable CV",
    languages: "Languages",
    optionalPhoto: "Optional photo",
    profile: "Profile",
    skills: "Skills",
    summary: "Summary",
    tailoredProfile: "Tailored profile",
    tailoredRole: "Tailored role",
  },
  German: {
    additional: "Weitere Informationen",
    availability: "Verfuegbarkeit",
    browserCvStudio: "Browser CV Studio",
    contact: "Kontakt",
    coreSkills: "Kernkompetenzen",
    editableHtmlCv: "Editierbarer HTML-CV",
    education: "Ausbildung",
    europassInspired: "Europass-inspiriert",
    experience: "Berufserfahrung",
    experienceItem: "Berufserfahrung",
    inBrowserEditableCv: "Editierbarer CV",
    languages: "Sprachen",
    optionalPhoto: "Optionales Foto",
    profile: "Profil",
    skills: "Kompetenzen",
    summary: "Profil",
    tailoredProfile: "Zielprofil",
    tailoredRole: "Zielrolle",
  },
};

function normalizeOutputLanguage(value) {
  const normalized = String(value || "").trim().toLowerCase();
  if (normalized.startsWith("de") || normalized === "german") {
    return "German";
  }
  return "English";
}

function labelFor(model, key) {
  const language = normalizeOutputLanguage(model?.outputLanguage || "English");
  return CV_EXPORT_LABELS[language]?.[key] || CV_EXPORT_LABELS.English[key] || key;
}

function emptyExperienceItem() {
  return {
    title: "",
    company: "",
    period: "",
    bulletsText: "",
  };
}

function educationItemToLine(item) {
  if (!item || typeof item !== "object") {
    return String(item || "").trim();
  }
  const head = [item.degree_title, item.institution, item.period]
    .map((value) => String(value || "").trim())
    .filter(Boolean)
    .join(" | ");
  const details = Array.isArray(item.details)
    ? item.details.map((value) => String(value || "").trim()).filter(Boolean)
    : String(item.detailsText || "")
        .split(/\r?\n/)
        .map((value) => value.trim())
        .filter(Boolean);
  return [head, details[0]].filter(Boolean).join(" - ");
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
  const normalizedTemplateId = templateId === "teal_resume" ? "plain" : templateId;
  return (
    WEB_CV_TEMPLATES.find((template) => template.id === normalizedTemplateId) ||
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
      title: String(item.title || item.role || ""),
      company: String(item.company || ""),
      period: String(item.period || ""),
      bulletsText:
        Array.isArray(item.bullets) && item.bullets.length
          ? item.bullets.map((entry) => String(entry || "").trim()).filter(Boolean).join("\n")
          : String(item.bulletsText || ""),
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
    outputLanguage: normalizeOutputLanguage(
      profile.cv_output_language ||
        profile.output_language ||
        normalizedDocuments.cv_output_language ||
        normalizedDocuments.output_language ||
        "English",
    ),
    location: String(profile.location || ""),
    email: String(profile.email || ""),
    website: String(profile.website || ""),
    linkedin: String(profile.linkedin_url || ""),
    github: String(profile.github_url || ""),
    summary: String(profile.summary || ""),
    skillsText: Array.isArray(profile.competencies) ? profile.competencies.join("\n") : "",
    languagesText: Array.isArray(profile.languages) ? profile.languages.join("\n") : "",
    availability: "Available immediately for tailored roles.",
    educationText: Array.isArray(profile.education)
      ? profile.education
          .map((item) => educationItemToLine(item))
          .filter(Boolean)
          .join("\n")
      : "",
    experience: normalizeExperienceItems(
      Array.isArray(profile.recent_experience)
        ? profile.recent_experience.map((item) => ({
            title: item.title || item.role || "",
            company: item.company || "",
            period: item.period || "",
            bulletsText:
              Array.isArray(item.bullets) && item.bullets.length
                ? item.bullets.join("\n")
                : item.bulletsText || "",
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
    outputLanguage: normalizeOutputLanguage(normalizedSession.outputLanguage || baseState.outputLanguage),
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

function workspaceDocxTemplateToWebTemplate(templateId, fallbackTemplateId = "") {
  const mappedTemplateId =
    DOCX_TO_WEB_TEMPLATE_MAP[String(templateId || "").trim().toLowerCase()] ||
    String(fallbackTemplateId || "").trim() ||
    WEB_CV_TEMPLATES[0].id;
  return findCvTemplate(mappedTemplateId).id;
}

function workspaceDocxColorSchemeToPalette(colorSchemeId) {
  const normalizedId = String(colorSchemeId || "").trim();
  const mappedPalette = DOCX_COLOR_SCHEME_TO_WEB_PALETTE[normalizedId];
  if (mappedPalette) {
    return normalizePalette(mappedPalette);
  }
  const customHex = normalizedId.replace(/^#/, "").toUpperCase();
  if (/^[0-9A-F]{6}$/.test(customHex)) {
    return normalizePalette({
      primary: customHex,
      accent: customHex,
      surface: "F4F7FB",
      text: "0F172A",
      muted: "475569",
      border: "CBD5E1",
    });
  }
  return normalizePalette(DOCX_COLOR_SCHEME_TO_WEB_PALETTE.classic_navy);
}

export function buildWorkspacePreviewDocuments(sharedDocuments = {}, workspaceSettings = {}) {
  const baseDocuments = sharedDocuments && typeof sharedDocuments === "object" ? sharedDocuments : {};
  const normalizedSettings =
    workspaceSettings && typeof workspaceSettings === "object" ? workspaceSettings : {};
  const rawCvTemplate = String(
    normalizedSettings.cv_template || baseDocuments.cv_template || "classic",
  );
  const cvTemplate = rawCvTemplate === "teal_resume" ? "plain" : rawCvTemplate;
  const cvColorScheme = String(
    normalizedSettings.cv_color_scheme || baseDocuments.cv_color_scheme || "classic_navy",
  );
  const cvFont = String(normalizedSettings.cv_font || baseDocuments.cv_font || "Calibri");
  const includePhoto = normalizedSettings.include_photo ?? baseDocuments.include_photo ?? true;
  const effectiveIncludePhoto = cvTemplate === "plain" ? false : Boolean(includePhoto);
  const cvOutputLanguage = normalizeOutputLanguage(
    normalizedSettings.cv_output_language ||
      baseDocuments.cv_output_language ||
      normalizedSettings.output_language ||
      baseDocuments.output_language ||
      "English",
  );
  const webPalette = workspaceDocxColorSchemeToPalette(cvColorScheme);

  return {
    ...baseDocuments,
    cv_template: cvTemplate,
    cv_color_scheme: cvColorScheme,
    cv_font: cvFont,
    cv_output_language: cvOutputLanguage,
    include_photo: effectiveIncludePhoto,
    web_cv_template: workspaceDocxTemplateToWebTemplate(
      cvTemplate,
      baseDocuments.web_cv_template,
    ),
    web_cv_font: cvFont,
    web_cv_show_photo: effectiveIncludePhoto,
    web_cv_palette: webPalette,
  };
}

export function buildWorkspacePreviewState(
  profile = {},
  sharedDocuments = {},
  workspaceSettings = {},
) {
  return buildCvStudioState(
    profile,
    buildWorkspacePreviewDocuments(sharedDocuments, workspaceSettings),
  );
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

  const template = findCvTemplate(state.templateId);
  const isPlainResume = template.id === "plain";
  return {
    templateId: template.id,
    template,
    palette: normalizePalette(state.palette || {}),
    fontFamily: String(state.fontFamily || "Aptos"),
    showPhoto: isPlainResume ? false : Boolean(state.showPhoto),
    outputLanguage: normalizeOutputLanguage(state.outputLanguage || "English"),
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
  return `<div class="${photoClass} cv-photo-placeholder"><span>${escapeHtml(labelFor(model, "optionalPhoto"))}</span></div>`;
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
      <div class="mini-label">${escapeHtml(labelFor(model, "languages"))}</div>
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
                  <h3>${escapeHtml(heading || labelFor(model, "experienceItem"))}</h3>
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
      <span>${escapeHtml(model.targetRole || labelFor(model, "tailoredRole"))}</span>
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
        <div class="mini-label">${escapeHtml(labelFor(model, "availability"))}</div>
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
          <div class="eyebrow">${escapeHtml(labelFor(model, "browserCvStudio"))}</div>
          <h1>${escapeHtml(model.name)}</h1>
          <p class="headline">${escapeHtml(model.headline)}</p>
          ${buildTargetBanner(model)}
        </div>
        ${buildPhotoMarkup(model, "cv-photo-shell rounded-photo")}
      </header>
      ${buildContactLinks(model)}
      ${buildSection(labelFor(model, "profile"), buildSummaryMarkup(model))}
      ${buildSection(labelFor(model, "coreSkills"), buildSkillsMarkup(model))}
      ${buildSection(labelFor(model, "experience"), buildExperienceMarkup(model))}
      <div class="two-up">
        ${buildSection(labelFor(model, "education"), buildEducationMarkup(model))}
        ${buildSection(labelFor(model, "additional"), buildFooterMeta(model) || `<p class="empty-note">Add languages or availability.</p>`)}
      </div>
    </main>
  `;
}

function templatePlainResume(model) {
  const skillsHeading =
    model.outputLanguage === "German"
      ? labelFor(model, "skills")
      : `${labelFor(model, "skills")} & Abilities`;
  const skills = model.skills.length
    ? `<p>${model.skills.map((skill) => escapeHtml(skill)).join(" | ")}</p>`
    : `<p class="empty-note">Add skills or keywords in the editor.</p>`;
  const experience = model.experience
    .map((item) => {
      const heading = [item.title, item.company, item.period].filter(Boolean).join(" | ");
      const bullets = item.bullets.length
        ? `<ul>${item.bullets.map((bullet) => `<li>${escapeHtml(bullet)}</li>`).join("")}</ul>`
        : `<p class="empty-note">Add tailored achievement bullets for this role.</p>`;
      return `
        <article class="plain-resume-entry">
          <h3>${escapeHtml(heading || labelFor(model, "experienceItem"))}</h3>
          ${bullets}
        </article>
      `;
    })
    .join("");
  const additional = buildLanguagesMarkup(model);
  return `
    <main class="cv-sheet template-plain-resume">
      <header class="plain-resume-head">
        <h1>${escapeHtml(model.name)}</h1>
      </header>
      ${buildContactLinks(model, "plain-resume-contact")}
      <section class="plain-resume-section">
        <h2>${escapeHtml(labelFor(model, "profile"))}</h2>
        ${buildSummaryMarkup(model)}
      </section>
      <section class="plain-resume-section">
        <h2>${escapeHtml(labelFor(model, "experience"))}</h2>
        <div class="plain-resume-experience">${experience}</div>
      </section>
      <section class="plain-resume-section">
        <h2>${escapeHtml(labelFor(model, "education"))}</h2>
        <div class="plain-resume-education">${buildEducationMarkup(model)}</div>
      </section>
      <section class="plain-resume-section">
        <h2>${escapeHtml(skillsHeading)}</h2>
        <div class="plain-resume-skills">${skills}</div>
      </section>
      ${
        additional
          ? `<section class="plain-resume-section"><h2>${escapeHtml(labelFor(model, "additional"))}</h2>${additional}</section>`
          : ""
      }
    </main>
  `;
}

function templateEditorialSidebar(model) {
  return `
    <main class="cv-sheet template-editorial">
      <aside class="editorial-rail">
        ${buildPhotoMarkup(model, "cv-photo-shell editorial-photo")}
        <div class="eyebrow">${escapeHtml(labelFor(model, "tailoredProfile"))}</div>
        <h1>${escapeHtml(model.name)}</h1>
        <p class="headline">${escapeHtml(model.headline)}</p>
        ${buildTargetBanner(model)}
        ${buildContactLinks(model, "contact-list contact-list-column")}
        ${buildSection(labelFor(model, "skills"), buildSkillsMarkup(model, "pill rail-pill"))}
        ${buildSection(labelFor(model, "additional"), buildFooterMeta(model) || `<p class="empty-note">Add languages or availability.</p>`)}
      </aside>
      <section class="editorial-main">
        ${buildSection(labelFor(model, "summary"), buildSummaryMarkup(model))}
        ${buildSection(labelFor(model, "experience"), buildExperienceMarkup(model))}
        ${buildSection(labelFor(model, "education"), buildEducationMarkup(model))}
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
            <div class="eyebrow">${escapeHtml(labelFor(model, "inBrowserEditableCv"))}</div>
            <h1>${escapeHtml(model.name)}</h1>
            <p class="headline">${escapeHtml(model.headline)}</p>
          </div>
          ${buildTargetBanner(model)}
        </div>
        ${buildSection(labelFor(model, "summary"), buildSummaryMarkup(model))}
        <div class="two-up mono-grid">
          ${buildSection(labelFor(model, "skills"), buildSkillsMarkup(model))}
          ${buildSection(labelFor(model, "education"), buildEducationMarkup(model))}
        </div>
        ${buildSection(labelFor(model, "experience"), buildExperienceMarkup(model))}
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
          <div class="eyebrow">${escapeHtml(labelFor(model, "europassInspired"))}</div>
          <h1>${escapeHtml(model.name)}</h1>
          <p class="headline">${escapeHtml(model.headline)}</p>
          ${buildTargetBanner(model)}
        </div>
        ${buildPhotoMarkup(model, "cv-photo-shell europass-photo")}
      </header>
      <div class="europass-grid">
        <div class="label-col">${escapeHtml(labelFor(model, "contact"))}</div>
        <div>${buildContactLinks(model)}</div>
        <div class="label-col">${escapeHtml(labelFor(model, "profile"))}</div>
        <div>${buildSummaryMarkup(model)}</div>
        <div class="label-col">${escapeHtml(labelFor(model, "skills"))}</div>
        <div>${buildSkillsMarkup(model)}</div>
        <div class="label-col">${escapeHtml(labelFor(model, "experience"))}</div>
        <div>${buildExperienceMarkup(model)}</div>
        <div class="label-col">${escapeHtml(labelFor(model, "education"))}</div>
        <div>${buildEducationMarkup(model)}</div>
        <div class="label-col">${escapeHtml(labelFor(model, "additional"))}</div>
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
          <div class="eyebrow light">${escapeHtml(labelFor(model, "browserCvStudio"))}</div>
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
          ${buildSection(labelFor(model, "summary"), buildSummaryMarkup(model))}
          ${buildSection(labelFor(model, "skills"), buildSkillsMarkup(model))}
          ${buildSection(labelFor(model, "education"), buildEducationMarkup(model))}
        </div>
        <div>
          ${buildSection(labelFor(model, "experience"), buildExperienceMarkup(model))}
          ${buildSection(labelFor(model, "additional"), buildFooterMeta(model) || `<p class="empty-note">Add languages or availability.</p>`)}
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
          <div class="eyebrow">${escapeHtml(labelFor(model, "editableHtmlCv"))}</div>
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
          ${buildSection(labelFor(model, "summary"), buildSummaryMarkup(model))}
          ${buildSection(labelFor(model, "skills"), buildSkillsMarkup(model))}
          ${buildSection(labelFor(model, "additional"), buildFooterMeta(model) || `<p class="empty-note">Add languages or availability.</p>`)}
        </div>
        <div>
          ${buildSection(labelFor(model, "experience"), buildExperienceMarkup(model))}
          ${buildSection(labelFor(model, "education"), buildEducationMarkup(model))}
        </div>
      </div>
    </main>
  `;
}

function renderTemplate(model) {
  switch (model.templateId) {
    case "plain":
      return templatePlainResume(model);
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
  const printPageSize = model.templateId === "plain" ? "Letter" : "A4";
  const printPageMargin = model.templateId === "plain" ? "0" : "10mm";
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
    .template-plain-resume {
      width: 215.9mm;
      min-height: 279.4mm;
      padding: 17.78mm 20.32mm 15.24mm;
      color: var(--cv-text);
      font-size: 10.5pt;
      line-height: 1.2;
    }
    .plain-resume-head {
      padding-bottom: 1.5mm;
      border-bottom: 1.5pt solid var(--cv-accent);
    }
    .plain-resume-head h1 {
      color: var(--cv-primary);
      font-size: 28pt;
      font-weight: 400;
      line-height: 1;
      letter-spacing: -0.02em;
    }
    .plain-resume-contact {
      display: flex;
      flex-wrap: wrap;
      gap: 0;
      margin-top: 6pt;
      font-size: 10pt;
      color: var(--cv-text);
    }
    .plain-resume-contact > * + *::before {
      content: " | ";
      white-space: pre;
    }
    .plain-resume-section {
      margin-top: 16pt;
    }
    .plain-resume-section h2 {
      margin-bottom: 5pt;
      color: var(--cv-primary);
      font-size: 14pt;
      line-height: 1.1;
    }
    .plain-resume-section .summary-copy,
    .plain-resume-section .education-line,
    .plain-resume-section .meta-stack p {
      font-size: 10.5pt;
      line-height: 1.2;
    }
    .plain-resume-experience {
      display: grid;
      gap: 8pt;
    }
    .plain-resume-entry h3 {
      margin-bottom: 2pt;
      color: var(--cv-text);
      font-size: 12pt;
      line-height: 1.15;
      text-transform: uppercase;
    }
    .plain-resume-entry ul {
      margin: 0;
      padding-left: 18px;
    }
    .plain-resume-entry li {
      font-size: 10.5pt;
      line-height: 1.2;
    }
    .plain-resume-entry li + li {
      margin-top: 2pt;
    }
    .plain-resume-education {
      display: grid;
      gap: 4pt;
    }
    .plain-resume-education .education-line {
      font-size: 12pt;
      font-weight: 700;
      text-transform: uppercase;
    }
    .plain-resume-skills {
      font-size: 10.5pt;
      line-height: 1.35;
    }
    .plain-resume-skills p {
      margin: 0;
    }
    .template-plain-resume .meta-stack + .meta-stack {
      margin-top: 6pt;
    }
    .template-plain-resume .pill-row {
      gap: 4pt 12pt;
    }
    .template-plain-resume .pill {
      padding: 0;
      border: 0;
      border-radius: 0;
      background: transparent;
      font-size: 10.5pt;
      font-weight: 400;
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
        size: ${printPageSize};
        margin: ${printPageMargin};
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
