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
    id: "plain",
    label: "Plain",
    shortLabel: "Plain",
    description: "Classic resume with a configurable name rule, compact skills, and optional profile photo.",
    mood: "Classic, polished, approachable",
    supportsPhoto: true,
  },
  {
    id: "section_bars",
    label: "Section Bars",
    shortLabel: "Bars",
    description: "Centered header, compact contact line, and pale section bars similar to a traditional Word resume.",
    mood: "Formal, compact, familiar",
    supportsPhoto: true,
  },
  {
    id: "modern_minimal",
    label: "Modern Minimal",
    shortLabel: "Minimal",
    description: "Clean one-column layout inspired by the modern minimal reference template.",
    mood: "Modern, crisp, direct",
    supportsPhoto: true,
  },
  {
    id: "modern_sidebar",
    label: "Modern Sidebar",
    shortLabel: "Sidebar",
    description: "Two-column layout inspired by the modern sidebar reference template.",
    mood: "Structured, modern, compact",
    supportsPhoto: true,
  },
  {
    id: "classic_executive",
    label: "Classic Executive",
    shortLabel: "Executive",
    description: "Formal executive layout inspired by the classic executive reference template.",
    mood: "Classic, senior, conservative",
    supportsPhoto: true,
  },
  {
    id: "europass_lite",
    label: "Europass",
    shortLabel: "Europass",
    description: "Clean Europass-inspired layout with optional profile photo. Grid-based, structured, and widely recognized in Europe.",
    mood: "Structured, professional, European",
    supportsPhoto: true,
  },
];

const DOCX_TO_WEB_TEMPLATE_MAP = {
  teal_resume: "plain",
  classic: "plain",
  modern: "plain",
  compact: "plain",
  europass: "europass_lite",
  plain: "plain",
  section_bars: "section_bars",
  simple: "section_bars",
  simple_resume: "section_bars",
  blue_bars: "section_bars",
  modern_minimal: "modern_minimal",
  minimal: "modern_minimal",
  modern_sidebar: "modern_sidebar",
  sidebar: "modern_sidebar",
  classic_executive: "classic_executive",
  executive: "classic_executive",
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
    projects: "Projects",
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
    projects: "Projekte",
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
    id: "experience-1",
    title: "",
    company: "",
    location: "",
    startDate: "",
    endDate: "",
    period: "",
    bullets: [],
  };
}

function stripLegacyBulletMarker(value) {
  return String(value || "").replace(/^\s*[-*•]\s*/, "").trim();
}

function clampListLevel(value) {
  return Math.max(0, Math.min(2, Number.parseInt(value, 10) || 0));
}

export function normalizeCvListItems(rawItems, fallbackText = "", idPrefix = "bullet") {
  const sourceItems = Array.isArray(rawItems)
    ? rawItems
    : String(fallbackText || "").split(/\r?\n/);
  return sourceItems
    .map((item, index) => {
      const isObject = item && typeof item === "object";
      const text = stripLegacyBulletMarker(
        isObject ? item.text || item.value || item.label || "" : item,
      );
      if (!text) return null;
      return {
        id: String((isObject && item.id) || `${idPrefix}-${index + 1}`),
        text,
        level: clampListLevel(isObject ? item.level : 0),
      };
    })
    .filter(Boolean);
}

function splitExperiencePeriod(item) {
  const explicitStart = String(item.startDate || item.start_date || item.start || "").trim();
  const explicitEnd = String(item.endDate || item.end_date || item.end || "").trim();
  if (explicitStart || explicitEnd) {
    return { startDate: explicitStart, endDate: explicitEnd };
  }
  const period = String(item.period || item.date_range || "").trim();
  const spacedParts = period.split(/\s+(?:-|–|—|to)\s+/i);
  const compactYearRange = period.match(/^(\d{4})-(\d{4}|present|current)$/i);
  const parts = spacedParts.length > 1
    ? spacedParts
    : compactYearRange
      ? [compactYearRange[1], compactYearRange[2]]
      : [period];
  return {
    startDate: String(parts[0] || "").trim(),
    endDate: String(parts.slice(1).join(" - ") || "").trim(),
  };
}

export function formatCvExperiencePeriod(item) {
  const values = [item?.startDate, item?.endDate]
    .map((value) => String(value || "").trim())
    .filter(Boolean);
  return values.length ? values.join(" - ") : String(item?.period || "").trim();
}

function normalizeProjectItems(rawItems) {
  return (Array.isArray(rawItems) ? rawItems : [])
    .filter((item) => item && typeof item === "object")
    .map((item, index) => ({
      id: String(item.id || `project-${index + 1}`),
      title: String(item.title || item.name || ""),
      period: String(item.period || item.date || item.year || ""),
      bullets: normalizeCvListItems(item.bullets, item.bulletsText, `project-${index + 1}-bullet`),
    }));
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
  const normalizedTemplateId =
    DOCX_TO_WEB_TEMPLATE_MAP[String(templateId || "").trim().toLowerCase()] || templateId;
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

export function normalizeExperienceItems(rawItems) {
  const items = Array.isArray(rawItems) ? rawItems : [];
  const normalizedItems = items
    .filter((item) => item && typeof item === "object")
    .map((item, index) => {
      const dates = splitExperiencePeriod(item);
      return {
        id: String(item.id || `experience-${index + 1}`),
        title: String(item.title || item.role || item.role_title || ""),
        company: String(item.company || item.employer || ""),
        location: String(item.location || item.city || ""),
        startDate: dates.startDate,
        endDate: dates.endDate,
        period: String(item.period || item.date_range || ""),
        bullets: normalizeCvListItems(
          item.bullets,
          item.bulletsText,
          `experience-${index + 1}-bullet`,
        ),
      };
    });
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
    targetRole: String(profile.target_role || ""),
    targetCompany: String(profile.target_company || ""),
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
        ? profile.recent_experience
        : [],
    ),
    projects: normalizeProjectItems(profile.projects),
    photoDataUrl: String(profile.photo_data_url || profile.avatar_url || ""),
  };

  const normalizedSession = sessionDraft && typeof sessionDraft === "object" ? sessionDraft : {};

  return {
    ...baseState,
    ...normalizedSession,
    templateId: findCvTemplate(normalizedSession.templateId || baseState.templateId).id,
    fontFamily: String(normalizedSession.fontFamily || baseState.fontFamily || "Aptos"),
    showPhoto: findCvTemplate(normalizedSession.templateId || baseState.templateId).supportsPhoto
      ? typeof normalizedSession.showPhoto === "boolean"
        ? normalizedSession.showPhoto
        : Boolean(baseState.showPhoto)
      : false,
    palette: normalizePalette(normalizedSession.palette || baseState.palette),
    outputLanguage: normalizeOutputLanguage(normalizedSession.outputLanguage || baseState.outputLanguage),
    experience: normalizeExperienceItems(normalizedSession.experience || baseState.experience),
    projects: normalizeProjectItems(normalizedSession.projects || baseState.projects),
  };
}

export function buildStudioDocumentPatch(state) {
  const template = findCvTemplate(state.templateId);
  return {
    web_cv_template: template.id,
    web_cv_font: String(state.fontFamily || "Aptos"),
    web_cv_show_photo: Boolean(template.supportsPhoto && state.showPhoto),
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
    normalizedSettings.cv_template || baseDocuments.cv_template || "plain",
  );
  const cvTemplate =
    DOCX_TO_WEB_TEMPLATE_MAP[rawCvTemplate.trim().toLowerCase()] || rawCvTemplate;
  const cvColorScheme = String(
    normalizedSettings.cv_color_scheme || baseDocuments.cv_color_scheme || "classic_navy",
  );
  const cvFont = String(normalizedSettings.cv_font || baseDocuments.cv_font || "Calibri");
  const includePhoto = normalizedSettings.include_photo ?? baseDocuments.include_photo ?? true;
  const effectiveIncludePhoto = Boolean(includePhoto);
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
  const experience = normalizeExperienceItems(state.experience)
    .map((item) => ({
      title: String(item.title || ""),
      company: String(item.company || ""),
      location: String(item.location || ""),
      period: formatCvExperiencePeriod(item),
      bullets: normalizeCvListItems(item.bullets),
    }))
    .filter((item) => item.title || item.company || item.location || item.period || item.bullets.length);
  const projects = normalizeProjectItems(state.projects);

  const template = findCvTemplate(state.templateId);
  return {
    templateId: template.id,
    template,
    palette: normalizePalette(state.palette || {}),
    fontFamily: String(state.fontFamily || "Aptos"),
    showPhoto: Boolean(template.supportsPhoto && state.showPhoto),
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
    projects,
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

export function buildStructuredListMarkup(items) {
  const normalizedItems = normalizeCvListItems(items);
  if (!normalizedItems.length) return "";
  let markup = "";
  let currentLevel = -1;
  normalizedItems.forEach((item, index) => {
    const targetLevel = Math.min(item.level, currentLevel + 1);
    const previousLevel = currentLevel;
    while (currentLevel < targetLevel) {
      markup += "<ul>";
      currentLevel += 1;
    }
    while (currentLevel > targetLevel) {
      markup += "</li></ul>";
      currentLevel -= 1;
    }
    if (index > 0 && targetLevel <= previousLevel) {
      markup += "</li>";
    }
    markup += `<li>${escapeHtml(item.text)}`;
  });
  while (currentLevel >= 0) {
    markup += "</li></ul>";
    currentLevel -= 1;
  }
  return markup;
}

function buildExperienceMarkup(model, className = "experience-stack") {
  return `
    <div class="${className}">
      ${model.experience
        .map((item) => {
          const heading = [item.title, item.company, item.location].filter(Boolean).join(" - ");
          const bullets = item.bullets.length
            ? buildStructuredListMarkup(item.bullets)
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
      const heading = [item.title, item.company, item.location, item.period].filter(Boolean).join(" | ");
      const bullets = item.bullets.length
        ? buildStructuredListMarkup(item.bullets)
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
        <div>
          <h1>${escapeHtml(model.name)}</h1>
        </div>
        ${buildPhotoMarkup(model, "cv-photo-shell plain-resume-photo")}
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
      ${
        model.projects.length
          ? `<section class="plain-resume-section"><h2>${escapeHtml(labelFor(model, "projects"))}</h2>${buildProjectsMarkup(model)}</section>`
          : ""
      }
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

function templateSectionBars(model) {
  const experience = model.experience
    .map((item) => {
      const employerLine = [item.company, item.location].filter(Boolean).join(" / ");
      const bullets = item.bullets.length
        ? buildStructuredListMarkup(item.bullets)
        : `<p class="empty-note">Add tailored achievement bullets for this role.</p>`;
      return `
        <article class="bar-resume-entry">
          <div class="bar-resume-entry-head">
            <div>
              <h3>${escapeHtml(item.title || labelFor(model, "experienceItem"))}</h3>
              ${employerLine ? `<p>${escapeHtml(employerLine)}</p>` : ""}
            </div>
            ${item.period ? `<span>${escapeHtml(item.period)}</span>` : ""}
          </div>
          ${bullets}
        </article>
      `;
    })
    .join("");
  const skills = model.skills.length
    ? `<p>${model.skills.map((skill) => escapeHtml(skill)).join(", ")}</p>`
    : `<p class="empty-note">Add skills or keywords in the editor.</p>`;
  const additional = buildFooterMeta(model);
  return `
    <main class="cv-sheet template-section-bars">
      <header class="bar-resume-head">
        <div class="bar-resume-title">
          <h1>${escapeHtml(model.name)}</h1>
          ${buildContactLinks(model, "bar-resume-contact")}
        </div>
        ${buildPhotoMarkup(model, "cv-photo-shell bar-resume-photo")}
      </header>
      <section class="bar-resume-section">
        <h2>${escapeHtml(labelFor(model, "summary"))}</h2>
        ${buildSummaryMarkup(model)}
      </section>
      <section class="bar-resume-section">
        <h2>${escapeHtml(labelFor(model, "experience"))}</h2>
        <div class="bar-resume-experience">${experience}</div>
      </section>
      ${
        model.projects.length
          ? `<section class="bar-resume-section"><h2>${escapeHtml(labelFor(model, "projects"))}</h2>${buildProjectsMarkup(model)}</section>`
          : ""
      }
      <section class="bar-resume-section">
        <h2>${escapeHtml(labelFor(model, "education"))}</h2>
        <div class="bar-resume-education">${buildEducationMarkup(model)}</div>
      </section>
      <section class="bar-resume-section">
        <h2>${escapeHtml(labelFor(model, "skills"))}</h2>
        <div class="bar-resume-skills">${skills}</div>
      </section>
      ${
        additional
          ? `<section class="bar-resume-section"><h2>${escapeHtml(labelFor(model, "additional"))}</h2>${additional}</section>`
          : ""
      }
    </main>
  `;
}

function templateModernMinimal(model) {
  const experience = buildExperienceMarkup(model, "minimal-experience-stack");
  return `
    <main class="cv-sheet template-modern-minimal">
      <header class="minimal-head">
        <div class="minimal-title">
          <h1>${escapeHtml(model.name)}</h1>
          <p>${escapeHtml(model.headline)}</p>
          ${buildContactLinks(model, "minimal-contact")}
        </div>
        ${buildPhotoMarkup(model, "cv-photo-shell minimal-photo")}
      </header>
      <section class="minimal-section">
        <h2>${escapeHtml(labelFor(model, "profile"))}</h2>
        ${buildSummaryMarkup(model)}
      </section>
      <section class="minimal-section">
        <h2>${escapeHtml(labelFor(model, "coreSkills"))}</h2>
        ${buildSkillsMarkup(model, "minimal-skill")}
      </section>
      <section class="minimal-section">
        <h2>${escapeHtml(labelFor(model, "experience"))}</h2>
        ${experience}
      </section>
      ${
        model.projects.length
          ? `<section class="minimal-section"><h2>${escapeHtml(labelFor(model, "projects"))}</h2>${buildProjectsMarkup(model)}</section>`
          : ""
      }
      <section class="minimal-section">
        <h2>${escapeHtml(labelFor(model, "education"))}</h2>
        ${buildEducationMarkup(model)}
      </section>
      ${buildFooterMeta(model) ? `<section class="minimal-section"><h2>${escapeHtml(labelFor(model, "additional"))}</h2>${buildFooterMeta(model)}</section>` : ""}
    </main>
  `;
}

function templateModernSidebar(model) {
  return `
    <main class="cv-sheet template-modern-sidebar">
      <aside class="sidebar-rail">
        ${buildPhotoMarkup(model, "cv-photo-shell sidebar-photo")}
        <section>
          <h2>${escapeHtml(labelFor(model, "contact"))}</h2>
          ${buildContactLinks(model, "sidebar-contact")}
        </section>
        <section>
          <h2>${escapeHtml(labelFor(model, "skills"))}</h2>
          ${buildSkillsMarkup(model, "sidebar-skill")}
        </section>
        <section>
          <h2>${escapeHtml(labelFor(model, "education"))}</h2>
          ${buildEducationMarkup(model)}
        </section>
        ${buildFooterMeta(model) ? `<section><h2>${escapeHtml(labelFor(model, "additional"))}</h2>${buildFooterMeta(model)}</section>` : ""}
      </aside>
      <section class="sidebar-main">
        <header>
          <h1>${escapeHtml(model.name)}</h1>
          <p>${escapeHtml(model.headline)}</p>
          ${buildTargetBanner(model)}
        </header>
        <section class="sidebar-section">
          <h2>${escapeHtml(labelFor(model, "profile"))}</h2>
          ${buildSummaryMarkup(model)}
        </section>
        <section class="sidebar-section">
          <h2>${escapeHtml(labelFor(model, "experience"))}</h2>
          ${buildExperienceMarkup(model, "sidebar-experience-stack")}
        </section>
        ${
          model.projects.length
            ? `<section class="sidebar-section"><h2>${escapeHtml(labelFor(model, "projects"))}</h2>${buildProjectsMarkup(model)}</section>`
            : ""
        }
      </section>
    </main>
  `;
}

function templateClassicExecutive(model) {
  return `
    <main class="cv-sheet template-classic-executive">
      <header class="executive-head">
        <div>
          <h1>${escapeHtml(model.name)}</h1>
          <p>${escapeHtml(model.headline)}</p>
        </div>
        <div class="executive-contact-wrap">
          ${buildPhotoMarkup(model, "cv-photo-shell executive-photo")}
          ${buildContactLinks(model, "executive-contact")}
        </div>
      </header>
      <section class="executive-section">
        <h2>${escapeHtml(model.outputLanguage === "German" ? labelFor(model, "profile") : "Executive Summary")}</h2>
        ${buildSummaryMarkup(model)}
      </section>
      <section class="executive-section">
        <h2>${escapeHtml(model.outputLanguage === "German" ? labelFor(model, "experience") : "Career Experience")}</h2>
        ${buildExperienceMarkup(model, "executive-experience-stack")}
      </section>
      ${
        model.projects.length
          ? `<section class="executive-section"><h2>${escapeHtml(labelFor(model, "projects"))}</h2>${buildProjectsMarkup(model)}</section>`
          : ""
      }
      <div class="executive-two-col">
        <section class="executive-section">
          <h2>${escapeHtml(labelFor(model, "skills"))}</h2>
          ${buildSkillsMarkup(model, "executive-skill")}
        </section>
        <section class="executive-section">
          <h2>${escapeHtml(labelFor(model, "education"))}</h2>
          ${buildEducationMarkup(model)}
        </section>
      </div>
      ${buildFooterMeta(model) ? `<section class="executive-section"><h2>${escapeHtml(labelFor(model, "additional"))}</h2>${buildFooterMeta(model)}</section>` : ""}
    </main>
  `;
}

function buildProjectsMarkup(model) {
  if (!model.projects.length) {
    return `<p class="empty-note">Add relevant projects or initiatives in the editor.</p>`;
  }
  return model.projects
    .map((item) => `
      <article class="experience-card">
        <div class="experience-head">
          <h3>${escapeHtml(item.title || "Project")}</h3>
          ${item.period ? `<span class="period">${escapeHtml(item.period)}</span>` : ""}
        </div>
        ${
          item.bullets.length
            ? buildStructuredListMarkup(item.bullets)
            : `<p class="empty-note">Add project outcomes or responsibilities.</p>`
        }
      </article>
    `)
    .join("");
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
    case "section_bars":
      return templateSectionBars(model);
    case "modern_minimal":
      return templateModernMinimal(model);
    case "modern_sidebar":
      return templateModernSidebar(model);
    case "classic_executive":
      return templateClassicExecutive(model);
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
  const usesLetterPage = model.templateId === "plain" || model.templateId === "section_bars";
  const printPageSize = usesLetterPage ? "Letter" : "A4";
  const printPageMargin = usesLetterPage ? "0" : "10mm";
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
      padding: 14.5mm 17.5mm 12mm;
      color: var(--cv-text);
      font-size: 9.8pt;
      line-height: 1.15;
    }
    .plain-resume-head {
      display: flex;
      justify-content: space-between;
      gap: 14pt;
      align-items: flex-start;
      padding-bottom: 1.5mm;
      border-bottom: 1.5pt solid var(--cv-accent);
    }
    .plain-resume-head h1 {
      color: var(--cv-primary);
      font-size: 24pt;
      font-weight: 400;
      line-height: 1;
      letter-spacing: 0;
    }
    .plain-resume-photo {
      width: 26mm;
      min-width: 26mm;
      height: 31mm;
      border-radius: 6px;
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
      margin-top: 10pt;
    }
    .plain-resume-section h2 {
      margin-bottom: 3pt;
      color: var(--cv-primary);
      font-size: 12.5pt;
      line-height: 1.1;
    }
    .plain-resume-section .summary-copy,
    .plain-resume-section .education-line,
    .plain-resume-section .meta-stack p {
      font-size: 9.8pt;
      line-height: 1.15;
    }
    .plain-resume-experience {
      display: grid;
      gap: 5pt;
    }
    .plain-resume-entry h3 {
      margin-bottom: 1pt;
      color: var(--cv-text);
      font-size: 10.5pt;
      line-height: 1.1;
      text-transform: uppercase;
    }
    .plain-resume-entry ul {
      margin: 0;
      padding-left: 18px;
    }
    .plain-resume-entry li {
      font-size: 9.6pt;
      line-height: 1.14;
    }
    .plain-resume-entry li + li {
      margin-top: 1pt;
    }
    .plain-resume-education {
      display: grid;
      gap: 4pt;
    }
    .plain-resume-education .education-line {
      font-size: 10.5pt;
      font-weight: 700;
      text-transform: uppercase;
    }
    .plain-resume-skills {
      font-size: 9.6pt;
      line-height: 1.22;
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
    .template-section-bars {
      width: 215.9mm;
      min-height: 279.4mm;
      padding: 14mm 17.5mm 12mm;
      color: var(--cv-text);
      font-family: Georgia, ${JSON.stringify(model.fontFamily)}, "Times New Roman", serif;
      font-size: 9.6pt;
      line-height: 1.22;
    }
    .bar-resume-head {
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 12mm;
      align-items: start;
      padding-bottom: 7pt;
    }
    .bar-resume-title {
      text-align: center;
    }
    .bar-resume-title h1 {
      padding-bottom: 5pt;
      border-bottom: 1.5pt solid #B8C7D9;
      color: #111827;
      font-size: 18pt;
      font-weight: 800;
      line-height: 1;
      letter-spacing: 0.02em;
      text-transform: uppercase;
    }
    .bar-resume-contact {
      display: flex;
      flex-wrap: wrap;
      justify-content: center;
      gap: 0;
      margin-top: 6pt;
      color: var(--cv-muted);
      font-size: 8.7pt;
      font-weight: 700;
      line-height: 1.2;
    }
    .bar-resume-contact > * + *::before {
      content: " | ";
      white-space: pre;
    }
    .bar-resume-photo {
      width: 24mm;
      min-width: 24mm;
      height: 29mm;
      border-radius: 4px;
    }
    .bar-resume-section {
      margin-top: 10pt;
    }
    .bar-resume-section h2 {
      margin-bottom: 6pt;
      padding: 2pt 6pt 2.5pt;
      background: var(--cv-surface);
      color: #4B5563;
      font-family: Georgia, "Times New Roman", serif;
      font-size: 11.5pt;
      font-weight: 400;
      line-height: 1.05;
      text-align: center;
      text-transform: uppercase;
    }
    .bar-resume-section .summary-copy,
    .bar-resume-section .education-line,
    .bar-resume-section .meta-stack p {
      font-size: 9.6pt;
      line-height: 1.24;
    }
    .bar-resume-experience {
      display: grid;
      gap: 8pt;
    }
    .bar-resume-entry-head {
      display: flex;
      justify-content: space-between;
      gap: 12pt;
      align-items: baseline;
      margin-bottom: 3pt;
    }
    .bar-resume-entry-head h3 {
      color: #111827;
      font-size: 9.8pt;
      font-weight: 800;
      line-height: 1.15;
    }
    .bar-resume-entry-head p {
      margin-top: 2pt;
      color: #111827;
      font-size: 9.4pt;
      font-style: italic;
      font-weight: 700;
    }
    .bar-resume-entry-head span {
      color: #111827;
      font-size: 9.3pt;
      font-weight: 800;
      white-space: nowrap;
    }
    .template-section-bars ul {
      margin: 0;
      padding-left: 18px;
    }
    .template-section-bars li {
      font-size: 9.4pt;
      line-height: 1.22;
    }
    .template-section-bars li + li {
      margin-top: 1.5pt;
    }
    .bar-resume-education {
      display: grid;
      gap: 5pt;
    }
    .bar-resume-education .education-line {
      font-weight: 700;
    }
    .bar-resume-skills p {
      font-size: 9.5pt;
      line-height: 1.24;
    }
    .template-modern-minimal {
      width: 210mm;
      min-height: 297mm;
      padding: 14mm 17mm 13mm;
      color: #1D252C;
      font-size: 9pt;
      line-height: 1.35;
    }
    .minimal-head {
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 12mm;
      align-items: start;
      padding-bottom: 8pt;
      border-bottom: 1.5pt solid color-mix(in srgb, var(--cv-primary) 18%, white);
    }
    .minimal-title h1 {
      color: #203040;
      font-size: 24pt;
      font-weight: 900;
      line-height: 1;
      text-transform: uppercase;
    }
    .minimal-title > p {
      margin-top: 5pt;
      color: var(--cv-primary);
      font-size: 10.5pt;
      font-weight: 900;
      text-transform: uppercase;
    }
    .minimal-contact {
      display: flex;
      flex-wrap: wrap;
      gap: 0;
      margin-top: 7pt;
      color: #5D6670;
      font-size: 8.5pt;
    }
    .minimal-contact > * + *::before {
      content: "  •  ";
      white-space: pre;
    }
    .minimal-photo {
      width: 25mm;
      min-width: 25mm;
      height: 30mm;
      border-radius: 5px;
    }
    .minimal-section {
      margin-top: 13pt;
    }
    .minimal-section h2 {
      margin-bottom: 6pt;
      padding-bottom: 3pt;
      border-bottom: 1pt solid color-mix(in srgb, var(--cv-primary) 28%, white);
      color: var(--cv-primary);
      font-size: 10pt;
      font-weight: 900;
      text-transform: uppercase;
    }
    .minimal-section .summary-copy,
    .minimal-section .education-line,
    .minimal-section .meta-stack p {
      font-size: 9pt;
      line-height: 1.35;
    }
    .minimal-section .experience-card {
      padding: 0;
      border: 0;
      border-radius: 0;
      background: transparent;
    }
    .minimal-section .experience-head h3 {
      color: #1D252C;
      font-size: 9.5pt;
      font-weight: 900;
    }
    .minimal-section .period {
      color: #5D6670;
      font-size: 8.5pt;
    }
    .minimal-experience-stack {
      display: grid;
      gap: 9pt;
    }
    .minimal-skill {
      display: inline-flex;
      min-width: 30%;
      padding: 5pt 6pt;
      border: 1pt solid color-mix(in srgb, var(--cv-primary) 18%, white);
      color: #1D252C;
      font-size: 8.7pt;
      font-weight: 800;
    }
    .template-modern-sidebar {
      display: grid;
      grid-template-columns: 64mm minmax(0, 1fr);
      width: 210mm;
      min-height: 297mm;
      padding: 8mm;
      color: #1D252C;
      font-size: 9pt;
      line-height: 1.35;
    }
    .sidebar-rail {
      padding: 10mm 8mm;
      background: #203040;
      color: rgba(255, 255, 255, 0.86);
    }
    .sidebar-rail section + section {
      margin-top: 15pt;
    }
    .sidebar-rail h2 {
      margin-bottom: 7pt;
      color: white;
      font-size: 9pt;
      font-weight: 900;
      text-transform: uppercase;
    }
    .sidebar-photo {
      width: 32mm;
      min-width: 32mm;
      height: 36mm;
      margin-bottom: 15pt;
      border-color: rgba(255, 255, 255, 0.28);
      border-radius: 6px;
      background: rgba(255, 255, 255, 0.08);
    }
    .sidebar-contact {
      display: grid;
      gap: 5pt;
      margin-top: 0;
      color: rgba(255, 255, 255, 0.82);
      font-size: 8.5pt;
      overflow-wrap: anywhere;
    }
    .sidebar-skill {
      display: block;
      padding: 0;
      border: 0;
      background: transparent;
      color: rgba(255, 255, 255, 0.88);
      font-size: 8.6pt;
      font-weight: 700;
    }
    .sidebar-rail .pill-row {
      display: grid;
      gap: 5pt;
    }
    .sidebar-rail .education-line,
    .sidebar-rail .meta-stack p,
    .sidebar-rail .mini-label {
      color: rgba(255, 255, 255, 0.84);
      font-size: 8.4pt;
    }
    .sidebar-main {
      padding: 11mm 10mm 9mm;
      background: white;
    }
    .sidebar-main > header h1 {
      color: #203040;
      font-size: 25pt;
      font-weight: 900;
      line-height: 1;
      text-transform: uppercase;
    }
    .sidebar-main > header p {
      margin-top: 6pt;
      color: var(--cv-primary);
      font-size: 10.5pt;
      font-weight: 900;
      text-transform: uppercase;
    }
    .sidebar-section {
      margin-top: 16pt;
    }
    .sidebar-section h2 {
      margin-bottom: 7pt;
      padding-bottom: 3pt;
      border-bottom: 1.2pt solid var(--cv-primary);
      color: #203040;
      font-size: 10pt;
      font-weight: 900;
      text-transform: uppercase;
    }
    .sidebar-section .experience-card {
      padding: 0;
      border: 0;
      border-radius: 0;
      background: transparent;
    }
    .sidebar-experience-stack {
      display: grid;
      gap: 10pt;
    }
    .template-classic-executive {
      width: 210mm;
      min-height: 297mm;
      padding: 15mm 18mm 13mm;
      color: #1D252C;
      font-size: 9pt;
      line-height: 1.35;
    }
    .executive-head {
      display: grid;
      grid-template-columns: minmax(0, 1fr) 64mm;
      gap: 14mm;
      align-items: start;
      padding-bottom: 10pt;
      border-bottom: 2pt solid #203040;
    }
    .executive-head h1 {
      color: #203040;
      font-size: 23pt;
      font-weight: 900;
      line-height: 1;
      text-transform: uppercase;
    }
    .executive-head > div > p {
      margin-top: 6pt;
      color: #5D6670;
      font-size: 10pt;
      font-weight: 800;
      text-transform: uppercase;
    }
    .executive-contact-wrap {
      display: grid;
      gap: 7pt;
      justify-items: end;
      color: #5D6670;
      text-align: right;
    }
    .executive-contact {
      display: grid;
      gap: 4pt;
      margin-top: 0;
      font-size: 8.5pt;
      overflow-wrap: anywhere;
    }
    .executive-photo {
      width: 25mm;
      min-width: 25mm;
      height: 30mm;
      border-radius: 5px;
    }
    .executive-section {
      margin-top: 14pt;
    }
    .executive-section h2 {
      margin-bottom: 7pt;
      padding-bottom: 3pt;
      border-bottom: 1pt solid color-mix(in srgb, #203040 22%, white);
      color: #203040;
      font-size: 9.5pt;
      font-weight: 900;
      text-transform: uppercase;
    }
    .executive-section .experience-card {
      padding: 0;
      border: 0;
      border-radius: 0;
      background: transparent;
    }
    .executive-experience-stack {
      display: grid;
      gap: 10pt;
    }
    .executive-skill {
      padding: 0;
      border: 0;
      background: transparent;
      color: #1D252C;
      font-size: 8.8pt;
      font-weight: 700;
    }
    .executive-two-col {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 12mm;
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
      .template-modern-sidebar,
      .ledger-grid,
      .template-europass .europass-grid,
      .two-up,
      .executive-two-col {
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
      .mono-hero,
      .plain-resume-head {
        flex-direction: column;
      }
      .bar-resume-head {
        grid-template-columns: 1fr;
      }
      .minimal-head,
      .executive-head {
        grid-template-columns: 1fr;
      }
      .bar-resume-photo {
        justify-self: center;
      }
      .executive-contact-wrap {
        justify-items: start;
        text-align: left;
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
