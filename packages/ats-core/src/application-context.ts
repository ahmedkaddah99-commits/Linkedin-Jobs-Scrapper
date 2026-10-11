import type { PageContext } from "./index";

/**
 * Provider-neutral application detection.
 *
 * Two questions are answered here, and they are deliberately separate:
 *
 *   1. Which ATS is this?  (`detectApplicationProvider`)
 *   2. Is this page an application the user can fill, a gateway step, an
 *      ordinary posting, or none of the above?  (`classifyApplicationPage`)
 *
 * Question 2 is the one that governs automatic panel display. A posting page
 * on a supported ATS host must NOT raise the panel; only a page carrying
 * fillable application controls may. Host recognition alone is never
 * sufficient evidence.
 */

export const APPLICATION_CONTEXT_ALGORITHM_VERSION = "1.0.0";

export type ApplicationProvider =
  | "greenhouse"
  | "lever"
  | "workday"
  | "icims"
  | "taleo"
  | "smartrecruiters"
  | "ashby"
  | "bamboohr"
  | "jobvite"
  | "recruitee"
  | "avature"
  | "generic"
  | "unknown";

/**
 * `application_form` is the only kind that may raise the assistant panel
 * automatically. `application_gateway` covers login, registration-method, and
 * consent interstitials that belong to the application flow but hold nothing
 * worth filling; `job_detail` covers ordinary postings.
 */
export type ApplicationPageKind =
  | "application_form"
  | "application_gateway"
  | "job_detail"
  | "unsupported";

export interface ApplicationJobContext {
  provider: string;
  employer: string;
  jobId?: string;
  title: string;
  location?: string;
  employmentType?: string;
  workMode?: string;
  postedAt?: string;
  jobUrl: string;
  applicationUrl: string;
  description?: string;
  keywords: string[];
  detectedAt: string;
  confidence: number;
}

export interface ProviderIdentity {
  provider: ApplicationProvider;
  /** Stable employer slug used to build the provider marker, e.g. `siemens`. */
  employerSlug: string;
  /** Provider marker in the form `<provider>:<employer>/<jobId>`, when a job id is known. */
  marker: string | null;
  reasons: string[];
}

export interface ApplicationPageDetection {
  kind: ApplicationPageKind;
  provider: ApplicationProvider;
  confidence: number;
  /** Visible, enabled, non-credential controls a user would be expected to complete. */
  fillableFieldCount: number;
  /** True when the page exposes a resume/CV upload control. */
  hasDocumentUpload: boolean;
  /** True when the page exposes repeated work-experience or education sections. */
  hasRepeatedSections: boolean;
  reasons: string[];
  algorithmVersion: string;
}

/** Minimum non-credential fillable controls before a page can be an application form. */
const MIN_APPLICATION_FIELDS = 3;

/** Controls that never count toward `fillableFieldCount`. */
const CREDENTIAL_INPUT_TYPES = new Set(["password", "hidden", "submit", "button", "reset", "image", "search"]);

const PROVIDER_HOST_RULES: ReadonlyArray<{
  provider: ApplicationProvider;
  test: (hostname: string) => boolean;
  reason: string;
}> = [
  { provider: "greenhouse", test: (h) => h === "boards.greenhouse.io" || h === "job-boards.greenhouse.io" || h.endsWith(".greenhouse.io"), reason: "Host is a Greenhouse-owned domain." },
  { provider: "lever", test: (h) => h.endsWith(".lever.co"), reason: "Host is a Lever-owned domain." },
  { provider: "workday", test: (h) => h.endsWith(".myworkdayjobs.com") || h.endsWith(".myworkdaysite.com"), reason: "Host is a Workday-owned domain." },
  { provider: "icims", test: (h) => h.endsWith(".icims.com"), reason: "Host is an iCIMS-owned domain." },
  { provider: "taleo", test: (h) => h.endsWith(".taleo.net") || h.endsWith(".oraclecloud.com"), reason: "Host is a Taleo or Oracle Recruiting domain." },
  { provider: "smartrecruiters", test: (h) => h.endsWith(".smartrecruiters.com"), reason: "Host is a SmartRecruiters-owned domain." },
  { provider: "ashby", test: (h) => h === "jobs.ashbyhq.com" || h.endsWith(".ashbyhq.com"), reason: "Host is an Ashby-owned domain." },
  { provider: "bamboohr", test: (h) => h.endsWith(".bamboohr.com") || h.endsWith(".bamboohr.co.uk"), reason: "Host is a BambooHR-owned domain." },
  { provider: "jobvite", test: (h) => h.endsWith(".jobvite.com"), reason: "Host is a Jobvite-owned domain." },
  { provider: "recruitee", test: (h) => h.endsWith(".recruitee.com"), reason: "Host is a Recruitee-owned domain." },
  { provider: "avature", test: (h) => h.endsWith(".avature.net"), reason: "Host is an Avature-owned domain." },
];

/**
 * Path shapes that identify a provider on an employer-hosted (white-labelled)
 * deployment, where the hostname carries no provider evidence at all.
 * Every pattern here must be specific enough that an ordinary corporate site
 * cannot match it by accident.
 */
const PROVIDER_PATH_RULES: ReadonlyArray<{
  provider: ApplicationProvider;
  pattern: RegExp;
  reason: string;
}> = [
  { provider: "avature", pattern: /\/(?:externaljobs|internaljobs|careers)\/(?:JobDetail|ApplicationMethods|Register|SelfService)\b/u, reason: "Path matches the Avature candidate-portal route shape." },
  { provider: "workday", pattern: /\/(?:en-US|[a-z]{2}-[A-Z]{2})\/[^/]+\/job\/[^/]+\/[^/]*_R-?\d+/u, reason: "Path matches the Workday requisition route shape." },
  { provider: "taleo", pattern: /\/hcmUI\/CandidateExperience\//u, reason: "Path matches the Oracle Recruiting candidate-experience route shape." },
];

/**
 * DOM markers for employer-hosted deployments. Kept deliberately loose: these
 * only ever *raise* confidence in a provider already suggested by a path rule,
 * or supply a provider when the path is inconclusive.
 */
function providerFromDomMarkers(document: Document): { provider: ApplicationProvider; reason: string } | null {
  if (document.querySelector("#grnhse_app, [id^='grnhse']")) {
    return { provider: "greenhouse", reason: "Page embeds the Greenhouse application widget." };
  }
  if (document.querySelector("[data-automation-id]")) {
    return { provider: "workday", reason: "Page uses Workday automation-id attributes." };
  }
  if (document.querySelector("#icims_content_iframe, [id^='icims_']")) {
    return { provider: "icims", reason: "Page embeds an iCIMS content frame." };
  }
  const referencesAvature = Array.from(document.querySelectorAll<HTMLElement>("script[src], link[href], body"))
    .some((element) => {
      const source = element.getAttribute("src") || element.getAttribute("href") || element.className || "";
      return typeof source === "string" && /avature/iu.test(source);
    });
  if (referencesAvature) {
    return { provider: "avature", reason: "Page references Avature portal assets." };
  }
  return null;
}

function safeUrl(value: string): URL | null {
  try {
    return new URL(value);
  } catch {
    return null;
  }
}

/**
 * Derives an employer slug from the host. `jobs.siemens.com` yields `siemens`;
 * `example.avature.net` yields `example`; `boards.greenhouse.io/acme` yields
 * `acme` from the first path segment when the host is a shared provider domain.
 */
function employerSlugFrom(parsed: URL, provider: ApplicationProvider): string {
  const hostname = parsed.hostname.toLowerCase();
  const labels = hostname.split(".").filter(Boolean);
  const sharedProviderHost = PROVIDER_HOST_RULES.some((rule) => rule.provider === provider && rule.test(hostname));

  if (sharedProviderHost) {
    const [firstSegment] = parsed.pathname.split("/").filter(Boolean);
    const subdomain = labels.length > 2 ? labels[0] : undefined;
    if (provider === "avature" || provider === "workday" || provider === "bamboohr" || provider === "recruitee") {
      // Employer is the subdomain on these providers.
      if (subdomain) return subdomain;
    }
    if (firstSegment && !/^(en|en_US|[a-z]{2}(?:[-_][A-Z]{2})?|jobs?|careers?|search)$/u.test(firstSegment)) {
      return firstSegment.toLowerCase();
    }
    return subdomain || labels[0] || hostname;
  }

  // Employer-hosted deployment: use the registrable label, skipping common
  // service subdomains.
  const meaningful = labels.filter((label) => !["www", "jobs", "careers", "career", "apply", "recruiting"].includes(label));
  return meaningful[meaningful.length - 2] || meaningful[0] || labels[0] || hostname;
}

/** Extracts a job identifier from the URL, covering the observed provider route shapes. */
export function jobIdFromUrl(url: string): string | undefined {
  const parsed = safeUrl(url);
  if (!parsed) return undefined;
  const queryKeys = ["folderId", "gh_jid", "jobId", "job_id", "requisitionId", "posting_id", "id"];
  for (const key of queryKeys) {
    const value = parsed.searchParams.get(key);
    if (value && /^[A-Za-z0-9_-]{1,64}$/u.test(value)) return value;
  }
  const pathPatterns = [
    /\/JobDetail\/(\d+)/u,
    /\/jobs?\/(\d{3,})/u,
    /\/postings?\/[^/]+\/([0-9a-f-]{8,})/iu,
    /_(R-?\d+)\b/u,
  ];
  for (const pattern of pathPatterns) {
    const match = pattern.exec(parsed.pathname);
    if (match) return match[1];
  }
  return undefined;
}

/**
 * Loopback hosts are permitted over plain HTTP so local fixtures exercise the
 * same code path as production. No public host can resolve to loopback, so this
 * cannot widen the production surface.
 */
function isLoopbackHost(hostname: string): boolean {
  return hostname === "127.0.0.1" || hostname === "localhost" || hostname === "[::1]";
}

export function detectApplicationProvider(url: string, document: Document | null = null): ProviderIdentity {
  const reasons: string[] = [];
  const parsed = safeUrl(url);
  const secure = parsed?.protocol === "https:" || (parsed?.protocol === "http:" && isLoopbackHost(parsed.hostname));
  if (!parsed || !secure) {
    return {
      provider: "unknown",
      employerSlug: "",
      marker: null,
      reasons: ["URL is not an HTTPS page."],
    };
  }

  const hostname = parsed.hostname.toLowerCase();
  let provider: ApplicationProvider = "unknown";

  const hostRule = PROVIDER_HOST_RULES.find((rule) => rule.test(hostname));
  if (hostRule) {
    provider = hostRule.provider;
    reasons.push(hostRule.reason);
  }

  if (provider === "unknown") {
    const pathRule = PROVIDER_PATH_RULES.find((rule) => rule.pattern.test(parsed.pathname));
    if (pathRule) {
      provider = pathRule.provider;
      reasons.push(pathRule.reason);
    }
  }

  if (document) {
    const marker = providerFromDomMarkers(document);
    if (marker && (provider === "unknown" || provider === marker.provider)) {
      provider = marker.provider;
      reasons.push(marker.reason);
    }
  }

  const employerSlug = employerSlugFrom(parsed, provider);
  const jobId = jobIdFromUrl(url);
  return {
    provider,
    employerSlug,
    marker: provider !== "unknown" && jobId ? `${provider}:${employerSlug}/${jobId}` : null,
    reasons: reasons.length ? reasons : ["No provider evidence found on this host or path."],
  };
}

function elementIsVisible(element: Element): boolean {
  if (element.hasAttribute("hidden")) return false;
  if (element.closest('[hidden], [aria-hidden="true"]')) return false;
  const view = element.ownerDocument.defaultView;
  if (!view) return true;
  for (let current: Element | null = element; current; current = current.parentElement) {
    const style = view.getComputedStyle(current);
    if (style.display === "none" || style.visibility === "hidden" || style.visibility === "collapse") {
      return false;
    }
  }
  return true;
}

function controlIsFillable(control: Element): boolean {
  if (control instanceof HTMLInputElement && CREDENTIAL_INPUT_TYPES.has(control.type.toLowerCase())) return false;
  const disabled = (control as HTMLInputElement).disabled;
  if (disabled) return false;
  if (control.getAttribute("readonly") !== null) return false;
  return elementIsVisible(control);
}

function accessibleText(element: Element): string {
  const id = element.getAttribute("id");
  const root = element.ownerDocument;
  const explicit = id
    ? Array.from(root.querySelectorAll("label")).find((label) => label.htmlFor === id)?.textContent
    : null;
  return [
    explicit,
    element.closest("label")?.textContent,
    element.getAttribute("aria-label"),
    element.getAttribute("placeholder"),
    element.getAttribute("name"),
  ]
    .filter(Boolean)
    .join(" ")
    .trim()
    .toLowerCase();
}

const RESUME_LABEL = /\b(?:cv|resume|r??sum??|lebenslauf|curriculum vitae)\b/iu;
const REPEATED_SECTION_LABEL = /\b(?:work experience|employment history|education|berufserfahrung|ausbildung)\b/iu;
const APPLICATION_FIELD_LABEL =
  /\b(?:first name|last name|given name|family name|surname|phone|postal code|zip code|street address|cover letter|work authorization|sponsorship|citizenship|country of residence|current position|notice period)\b/iu;
const GATEWAY_TEXT =
  /\b(?:already registered|sign in|log in|login|create an account|register|forgot your password|password)\b/iu;

/**
 * Classifies the page. The decision order matters: an application form is
 * recognised on positive field evidence first, so a multi-step flow that also
 * shows a "log in" link is not demoted to a gateway.
 */
export function classifyApplicationPage(context: PageContext): ApplicationPageDetection {
  const { document, url } = context;
  const identity = detectApplicationProvider(url, document);
  const reasons: string[] = [...identity.reasons];

  const controls = Array.from(
    document.querySelectorAll<HTMLElement>("input, textarea, select, [role='combobox'], [role='listbox']"),
  );
  const fillable = controls.filter(controlIsFillable);
  const fillableFieldCount = fillable.filter((control) => !(control instanceof HTMLInputElement && control.type === "file")).length;

  const fileInputs = fillable.filter((control): control is HTMLInputElement =>
    control instanceof HTMLInputElement && control.type === "file");
  const hasDocumentUpload = fileInputs.some((control) => RESUME_LABEL.test(accessibleText(control)));

  const bodyText = document.body?.textContent || "";
  const hasRepeatedSections = REPEATED_SECTION_LABEL.test(bodyText) &&
    fillable.some((control) => REPEATED_SECTION_LABEL.test(accessibleText(control))) ||
    Boolean(document.querySelector("[data-repeat], [data-repeatable], [data-section='experience'], [data-section='education']"));

  const hasApplicationLabels = fillable.some((control) => APPLICATION_FIELD_LABEL.test(accessibleText(control)));
  const parsed = safeUrl(url);
  const pathLooksLikeApplication = Boolean(parsed && /\/(?:apply|application|register|candidate|submit|externaljobs)\b/iu.test(parsed.pathname));
  const hasCredentialInput = Boolean(document.querySelector('input[type="password"]'));

  if (identity.provider === "unknown" && !hasApplicationLabels && !hasDocumentUpload) {
    return {
      kind: "unsupported",
      provider: identity.provider,
      confidence: 0,
      fillableFieldCount,
      hasDocumentUpload,
      hasRepeatedSections,
      reasons: [...reasons, "No application fields or recognised provider were found on this page."],
      algorithmVersion: APPLICATION_CONTEXT_ALGORITHM_VERSION,
    };
  }

  // Positive application-form evidence, weighted. A page needs both enough
  // controls to be worth filling and at least one application-shaped signal,
  // so a posting page carrying a search box and a locale picker cannot qualify.
  const supportingSignals = [
    hasApplicationLabels && "Page exposes recognised application field labels.",
    hasDocumentUpload && "Page exposes a CV or resume upload control.",
    hasRepeatedSections && "Page exposes repeated work-experience or education sections.",
    pathLooksLikeApplication && "URL path matches an application route.",
  ].filter((reason): reason is string => typeof reason === "string");

  // The URL path alone is never enough. A posting page on an application route
  // that happens to carry a few filter controls must not qualify, so at least
  // one signal has to come from the fields themselves.
  const fieldEvidence = hasApplicationLabels || hasDocumentUpload || hasRepeatedSections;
  const enoughFields = fillableFieldCount >= MIN_APPLICATION_FIELDS;
  if (enoughFields && fieldEvidence) {
    const confidence = Math.min(
      0.99,
      0.5 + 0.12 * supportingSignals.length + (identity.provider === "unknown" ? 0 : 0.15),
    );
    return {
      kind: "application_form",
      provider: identity.provider,
      confidence,
      fillableFieldCount,
      hasDocumentUpload,
      hasRepeatedSections,
      reasons: [...reasons, `Page exposes ${fillableFieldCount} fillable controls.`, ...supportingSignals],
      algorithmVersion: APPLICATION_CONTEXT_ALGORITHM_VERSION,
    };
  }

  // A credential form on an application route is a gateway step, not an
  // application. Runr must stay silent here ??? the user is signing in.
  if (hasCredentialInput && GATEWAY_TEXT.test(bodyText) && pathLooksLikeApplication) {
    return {
      kind: "application_gateway",
      provider: identity.provider,
      confidence: 0.8,
      fillableFieldCount,
      hasDocumentUpload,
      hasRepeatedSections,
      reasons: [...reasons, "Page is a sign-in or registration step in the application flow."],
      algorithmVersion: APPLICATION_CONTEXT_ALGORITHM_VERSION,
    };
  }

  if (identity.provider !== "unknown") {
    return {
      kind: "job_detail",
      provider: identity.provider,
      confidence: 0.7,
      fillableFieldCount,
      hasDocumentUpload,
      hasRepeatedSections,
      reasons: [
        ...reasons,
        `Page exposes ${fillableFieldCount} fillable controls, below the ${MIN_APPLICATION_FIELDS} required for an application form.`,
      ],
      algorithmVersion: APPLICATION_CONTEXT_ALGORITHM_VERSION,
    };
  }

  return {
    kind: "unsupported",
    provider: identity.provider,
    confidence: 0,
    fillableFieldCount,
    hasDocumentUpload,
    hasRepeatedSections,
    reasons: [...reasons, "Page did not meet the application-form threshold on an unrecognised provider."],
    algorithmVersion: APPLICATION_CONTEXT_ALGORITHM_VERSION,
  };
}

/**
 * Strips trailing gender-notation suffixes used in German-language and EU
 * postings ??? `(m/w/d)`, `(f/m/x)`, `(all genders)` ??? which carry no meaning for
 * matching and are not shown in the assistant's job header.
 */
export function normalizeJobTitle(value: string): string {
  return value
    .replace(/\(\s*(?:[mwfdxa](?:\s*\/\s*[mwfdxa])+|all\s+genders?|any\s+gender)\s*\)/giu, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function metaContent(document: Document, selectors: string[]): string | undefined {
  for (const selector of selectors) {
    const value = document.querySelector<HTMLMetaElement>(selector)?.content?.trim();
    if (value) return value;
  }
  return undefined;
}

interface JobPostingLd {
  "@type"?: string | string[];
  title?: string;
  datePosted?: string;
  employmentType?: string | string[];
  description?: string;
  identifier?: string | { value?: string | number };
  hiringOrganization?: { name?: string };
  jobLocation?: unknown;
  jobLocationType?: string;
}

function readJobPostingLd(document: Document): JobPostingLd | null {
  const scripts = Array.from(document.querySelectorAll<HTMLScriptElement>('script[type="application/ld+json"]'));
  for (const script of scripts) {
    let parsed: unknown;
    try {
      parsed = JSON.parse(script.textContent || "");
    } catch {
      continue;
    }
    const candidates = Array.isArray(parsed) ? parsed : [parsed];
    for (const candidate of candidates) {
      const record = candidate as JobPostingLd;
      const type = record?.["@type"];
      const types = Array.isArray(type) ? type : [type];
      if (types.includes("JobPosting")) return record;
    }
  }
  return null;
}

/**
 * Reads `Label: value` metadata rows, the pattern used by most employer-hosted
 * posting pages. Matching is label-driven rather than positional so a layout
 * change does not silently shift every value by one row.
 */
function labelledMetadata(document: Document): Map<string, string> {
  const rows = new Map<string, string>();
  const text = document.body?.textContent || "";
  const pattern = /([A-Za-z][A-Za-z /()]{2,40}?)\s*:\s*([^\n:]{1,160}?)(?=\s{2,}[A-Z]|\n|$)/gu;
  for (const match of text.matchAll(pattern)) {
    const key = (match[1] || "").trim().toLowerCase().replace(/\s+/g, " ");
    const value = (match[2] || "").trim();
    if (key && value && !rows.has(key)) rows.set(key, value);
  }
  return rows;
}

const STOP_WORDS = new Set([
  "and", "the", "for", "with", "you", "your", "our", "are", "will", "that", "this", "have", "has",
  "from", "not", "???", "als", "und", "der", "die", "das", "ein", "eine", "wir", "auf", "den", "des",
  "job", "role", "team", "work", "working", "years", "experience", "including", "ability", "strong",
]);

/**
 * First-pass keyword extraction. Deliberately simple and unversioned for
 * scoring purposes ??? the explainable resume-match algorithm and its own
 * versioned normalisation land in a later slice and will supersede this.
 */
export function extractKeywords(description: string, limit = 40): string[] {
  const tokens = description
    .toLowerCase()
    .replace(/[^a-z0-9+#./ -]/gu, " ")
    .split(/\s+/u)
    .map((token) => token.replace(/^[-./]+|[-./]+$/gu, ""))
    .filter((token) => token.length >= 3 && token.length <= 32 && !STOP_WORDS.has(token) && !/^\d+$/u.test(token));

  const counts = new Map<string, number>();
  for (const token of tokens) counts.set(token, (counts.get(token) || 0) + 1);
  return Array.from(counts.entries())
    .sort((left, right) => right[1] - left[1] || left[0].localeCompare(right[0]))
    .slice(0, limit)
    .map(([token]) => token);
}

export function extractApplicationJobContext(
  context: PageContext,
  detection: ApplicationPageDetection,
  detectedAt: string,
): ApplicationJobContext | null {
  if (detection.kind === "unsupported") return null;
  const { document, url } = context;
  const identity = detectApplicationProvider(url, document);
  const ld = readJobPostingLd(document);
  const rows = labelledMetadata(document);

  const rawTitle =
    ld?.title ||
    metaContent(document, ['meta[property="og:title"]']) ||
    document.querySelector("h1")?.textContent ||
    "";
  const title = normalizeJobTitle(rawTitle);

  const employer =
    ld?.hiringOrganization?.name ||
    rows.get("company") ||
    metaContent(document, ['meta[property="og:site_name"]']) ||
    (identity.employerSlug ? identity.employerSlug.charAt(0).toUpperCase() + identity.employerSlug.slice(1) : "");

  const ldIdentifier = typeof ld?.identifier === "object" ? ld?.identifier?.value : ld?.identifier;
  const jobId = jobIdFromUrl(url) || rows.get("job id") || (ldIdentifier != null ? String(ldIdentifier) : undefined);

  const description =
    ld?.description ||
    document.querySelector("[data-job-description], .job-description, #job-description")?.textContent?.trim() ||
    undefined;

  const employmentType = Array.isArray(ld?.employmentType)
    ? ld?.employmentType.join(", ")
    : ld?.employmentType || rows.get("employment type") || rows.get("job type");

  return {
    provider: identity.provider,
    employer: employer.trim(),
    jobId,
    title,
    location: rows.get("location") || rows.get("location(s)"),
    employmentType,
    workMode: rows.get("work mode") || ld?.jobLocationType,
    postedAt: ld?.datePosted || rows.get("posted since") || rows.get("posted on") || rows.get("posted"),
    jobUrl: url,
    applicationUrl: url,
    description,
    keywords: description ? extractKeywords(description) : [],
    detectedAt,
    confidence: detection.confidence,
  };
}
