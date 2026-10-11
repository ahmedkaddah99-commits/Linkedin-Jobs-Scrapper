import { SAMPLE_ENHANCEMENTS } from '../data/cvCustomizationSample.js';

export const SECTION_LABELS = { summary: 'Professional summary', experience: 'Professional experience', projects: 'Projects', skills: 'Skills', education: 'Education', languages: 'Languages', custom: 'Additional information' };
const clean = value => String(value ?? '').trim();
const list = value => Array.isArray(value) ? value : [];
const label = value => typeof value === 'string' ? value : clean(value?.name || value?.label || value?.text || value?.title);
const unique = values => [...new Map(values.filter(Boolean).map(v => [v.toLowerCase(), v])).values()];
const norm = text => clean(text).normalize('NFKC').toLowerCase().replace(/[–—]/g, '-');
const clone = value => JSON.parse(JSON.stringify(value));

export function normalizeCv(raw = {}) {
  const entries = values => list(values).map(v => ({ title: clean(v.title || v.role || v.degree_title || v.degree), company: clean(v.company || v.institution || v.school), period: clean(v.period || v.dates), bullets: list(v.bullets || v.details).map(label).filter(Boolean) }));
  return {
    ...Object.fromEntries(['name', 'email', 'phone', 'location', 'linkedin_url', 'website', 'github_url', 'summary'].map(k => [k, clean(raw[k])])),
    headline: clean(raw.headline || raw.role_title),
    experience: entries(raw.experience || raw.recent_experience), projects: entries(raw.projects), education: entries(raw.education),
    skills: unique(list(raw.skills || raw.competencies).map(label)), languages: list(raw.languages).map(label),
    custom: list(raw.custom || raw.custom_sections).map(v => ({ title: clean(v.title || v.heading), company: '', period: '', bullets: list(v.bullets || v.lines || v.items || v.details || (v.content ? v.content.split('\n') : [])).map(label) })),
    order: [...Object.keys(SECTION_LABELS)],
  };
}

export function termsIn(text, terms) {
  const source = norm(text);
  return terms.filter(term => [term.label, ...list(term.aliases)].some(alias => {
    const escaped = norm(alias).replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    return escaped && new RegExp(`(^|[^\\p{L}\\p{N}])${escaped}($|[^\\p{L}\\p{N}])`, 'u').test(source);
  }));
}

export function cvText(cv) {
  const shown = new Set(cv.order || Object.keys(SECTION_LABELS));
  return [cv.headline, shown.has('summary') ? cv.summary : '', ...shown.has('skills') ? list(cv.skills) : [], ...['experience', 'projects', 'education', 'custom'].filter(k => shown.has(k)).flatMap(k => list(cv[k]).flatMap(e => [e.title, e.company, ...list(e.bullets)]))].filter(Boolean).join('\n');
}

export function experienceYears(entries, now = new Date()) {
  const months = ['jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec'];
  const parse = (value, end) => {
    if (/present|current|now/i.test(value)) return now.getFullYear() * 12 + now.getMonth() + 1;
    const year = value.match(/\b(19\d{2}|20\d{2})\b/);
    if (!year) return null;
    const month = months.findIndex(m => norm(value).includes(m));
    return Number(year[1]) * 12 + (month < 0 ? (end ? 11 : 0) : month) + (end ? 1 : 0);
  };
  const ranges = list(entries).map(e => clean(e.period).split(/\s*[-–—]\s*|\s+to\s+/i)).filter(p => p.length === 2).map(([s, e]) => [parse(s, false), parse(e, true)]).filter(([s, e]) => s !== null && e !== null && e > s).sort((a, b) => a[0] - b[0]);
  if (!ranges.length) return null;
  const merged = [];
  for (const range of ranges) {
    const previous = merged.at(-1);
    if (previous && range[0] <= previous[1]) previous[1] = Math.max(previous[1], range[1]);
    else merged.push([...range]);
  }
  return Math.round(merged.reduce((sum, [s, e]) => sum + e - s, 0) / 12 * 10) / 10;
}

const VOCABULARY = ['SAP IBP', 'SAP', 'S&OP', 'Integrated business planning', 'Supply chain', 'Demand planning', 'Supply planning', 'Forecasting', 'ERP', 'Manufacturing', 'Consulting', 'Corporate strategy', 'Strategy consulting', 'Investment banking', 'Private equity', 'Enterprise software', 'SaaS', 'Strategic thinking', 'Strategic planning', 'Stakeholder management', 'Project management', 'Data analysis', 'Python', 'SQL', 'JavaScript', 'TypeScript', 'React', 'Java', 'AWS', 'Azure', 'Power BI', 'Excel', 'Agile', 'Scrum', 'Machine learning', 'Artificial intelligence', 'Business development', 'Product management', 'Communication', 'Leadership'];
export function requirementsForJob(job = {}) {
  if (Array.isArray(job.keywords)) return job;
  const summary = job.runrSummary || job.runr_summary || {};
  const qualifications = [...list(summary.required_qualifications), ...list(summary.preferred_qualifications)].map(label);
  const source = [job.description, job.title, ...list(summary.responsibilities).map(label), ...qualifications].filter(Boolean).join('\n');
  const explicit = list(job.skills).map(label);
  const found = termsIn(source, VOCABULARY.map(v => ({ label: v })));
  const keywords = unique([...explicit, ...found.map(v => v.label)]).map(v => ({ label: v, aliases: [], source: source.split(/[\n.!?]+/).find(q => termsIn(q, [{ label: v }]).length)?.trim() || 'Job skill requirement' }));
  const yearMatch = source.match(/(?:at least|minimum(?: of)?|mindestens)?\s*(\d+)\s*(?:\+|[-–]\s*\d+)?\s*(?:years?|jahre[n]?)\s*(?:(?:of|professional|relevant|berufs)\s*)?(?:experience|erfahrung)?/i);
  const explicitYears = job.requiredExperienceYears ?? job.required_experience_years ?? job.structuredDescription?.experience_years_min?.value ?? (yearMatch ? Number(yearMatch[1]) : null);
  const inferredYears = /senior|lead|principal|head/i.test(job.title || '') ? 5 : /junior|intern|graduate|entry/i.test(job.title || '') ? 0 : 3;
  const years = explicitYears ?? inferredYears;
  const industries = unique(list(job.industries || job.companyIndustries).map(label));
  if (!industries.length) industries.push(...termsIn(source, ['Consulting', 'Manufacturing', 'Supply chain', 'Software', 'Healthcare', 'Finance', 'Banking', 'Retail', 'Energy', 'Construction', 'Logistics'].map(v => ({ label: v }))).map(v => v.label));
  return { id: job.id, version: job.version || job.current_version_id || job.structuredDescription?.source_content_hash || '', title: job.title || '', company: job.company || '',
    years: typeof years === 'number' ? years : null, yearsBasis: explicitYears == null ? 'inferred' : 'explicit', experienceNote: explicitYears == null ? 'Seniority benchmark inferred from the role; not an employer-stated minimum. AI analysis refines this using the full description.' : (yearMatch?.[0] || qualifications.filter(q => /year|experience/i.test(q)).join(' ')),
    industries, industryBasis: job.industries?.length ? 'explicit' : 'inferred', keywords,
    roleTerms: unique(clean(job.title).split(/[\s,/&]+/).filter(t => t.length > 3 && !/senior|junior|associate|manager|lead/i.test(t))),
    priorities: keywords.slice(0, 6).map(k => k.label),
  };
}

export function assessCv(cv, job) {
  const full = cvText(cv), keywords = list(job.keywords);
  const matched = termsIn(full, keywords), missing = keywords.filter(k => !matched.includes(k));
  const ratio = (text, values) => values.length ? termsIn(text, values.map(v => ({ label: v }))).length / values.length : null;
  const shown = new Set(cv.order || Object.keys(SECTION_LABELS));
  const years = experienceYears(shown.has('experience') ? cv.experience : []);
  const roles = list(job.roleTerms), industries = list(job.industries), priorities = list(job.priorities);
  const workText = list(shown.has('experience') ? cv.experience : []).flatMap(e => [e.title, ...list(e.bullets)]).join(' ');
  const dimension = (key, title, weight, value, explanation) => ({ key, title, weight, value, status: value === null ? 'unknown' : value >= .8 ? 'matched' : value > 0 ? 'partial' : 'missing', explanation });
  const dimensions = [
    dimension('title', 'Job title', 20, ratio([cv.headline, workText].join(' '), roles), 'Compared with your headline, actual role titles and responsibilities. Historical titles stay unchanged.'),
    dimension('years', 'Years of experience', 20, job.years == null ? null : years == null ? 0 : Math.min(1, years / Math.max(job.years, 1)), job.years == null ? 'The job does not state a numeric experience requirement.' : `${years == null ? 'Dates not available' : `${years} years across dated roles (overlaps counted once)`}. ${job.experienceNote || ''} Total duration does not verify time in a specialty.`),
    dimension('industry', 'Industry experience', 15, ratio(full, industries), industries.length ? 'Only industry terms represented in your CV count. Employer industry alone does not establish specialist experience.' : 'No explicit industry requirements available.'),
    dimension('keywords', 'ATS keywords', 30, keywords.length ? matched.length / keywords.length : null, `${matched.length} of ${keywords.length} distinct job keywords appear in this CV. Repetition does not improve coverage.`),
    dimension('summary', 'Summary', 15, ratio(shown.has('summary') ? cv.summary : '', priorities), priorities.length ? 'Coverage of the job priorities in your professional summary. Include only strengths you can support.' : 'No explicit priorities available to assess the summary.'),
  ];
  const applicable = dimensions.filter(d => d.value !== null);
  const score = applicable.length ? Math.round(10 * applicable.reduce((s, d) => s + d.value * d.weight, 0) / applicable.reduce((s, d) => s + d.weight, 0) * 10) / 10 : null;
  return { score, dimensions, years, keywords: { matched, missing }, completeness: applicable.length, version: 'cv-alignment-v1' };
}

export function keywordEvidence(cv, term, confirmations = {}) {
  const confirmation = confirmations[term.label];
  if (confirmation?.confirmed === false) return '';
  if (confirmation?.confirmed && clean(confirmation.example)) return clean(confirmation.example);
  // Evidence is either curated sample text or a server-validated exact CV excerpt.
  if (term.evidence) return term.evidence;
  return cvText(cv).split('\n').find(line => termsIn(line, [term]).length) || '';
}

export function generateSampleCv(source, job, options = {}) {
  const draft = clone(source), sections = list(options.sections);
  if (sections.includes('summary')) draft.summary = SAMPLE_ENHANCEMENTS.summary;
  if (sections.includes('experience')) draft.experience = source.experience.map((e, i) => options.scope === 'quick' && i >= 2 ? clone(e) : { ...clone(e), bullets: clone(SAMPLE_ENHANCEMENTS.experience[i] || e.bullets) });
  if (sections.includes('projects')) draft.projects = source.projects.map((e, i) => ({ ...clone(e), bullets: [SAMPLE_ENHANCEMENTS.projects[i] || e.bullets[0], ...e.bullets.slice(1)].filter(Boolean) }));
  const eligible = list(job.keywords).filter(t => list(options.keywords).includes(t.label) && keywordEvidence(source, t, options.confirmations));
  if (sections.includes('skills')) draft.skills = unique([...source.skills, ...eligible.map(t => t.label)]);
  for (const term of eligible) {
    if (!sections.includes(term.section) || (term.section === 'experience' && options.scope === 'quick' && term.entry >= 2)) continue;
    const entry = draft[term.section]?.[term.entry];
    if (entry && !termsIn(entry.bullets.join(' '), [term]).length) {
      const text = keywordEvidence(source, term, options.confirmations);
      // Replace the matching evidence bullet rather than duplicating it in the CV.
      const words = text.toLowerCase().match(/[a-z]{4,}/g) || [];
      const ranked = entry.bullets.map((bullet, index) => ({ index, count: words.filter(w => bullet.toLowerCase().includes(w)).length })).sort((a, b) => b.count - a.count);
      if (ranked[0]?.count >= 2) entry.bullets[ranked[0].index] = `${term.label}: ${text}`;
    }
  }
  return draft;
}

export function draftKey(user, job, asset, revision) {
  return 'runr.cv-draft.v1:' + JSON.stringify([user || 'anonymous', job.id, job.version || '', job.title, job.years, job.keywords, job.industries, asset, revision]);
}
export function readDraft(key, storage) {
  try {
    const data = JSON.parse((storage || globalThis.localStorage).getItem(key));
    const valid = cv => cv && typeof cv.name === 'string' && typeof cv.summary === 'string' && Array.isArray(cv.order) && cv.order.every(k => Object.hasOwn(SECTION_LABELS, k)) && ['skills', 'languages'].every(k => Array.isArray(cv[k]) && cv[k].every(v => typeof v === 'string')) && ['experience', 'projects', 'education'].every(k => Array.isArray(cv[k]) && cv[k].every(e => e && typeof e.title === 'string' && Array.isArray(e.bullets) && e.bullets.every(b => typeof b === 'string')));
    if (!valid(data?.draft) || !Array.isArray(data.options?.sections) || !Array.isArray(data.options?.keywords)) return null;
    return { ...data, history: list(data.history).filter(valid).slice(-25) };
  } catch { return null; }
}
export function saveDraft(key, value, storage) {
  try { (storage || globalThis.localStorage).setItem(key, JSON.stringify(value)); return true; } catch { return false; }
}
const escape = value => clean(value).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
export function buildCvExport(cv, { font = 'serif', accent = '#164e63' } = {}) {
  const body = (cv.order || Object.keys(SECTION_LABELS)).map(key => {
    const value = cv[key];
    if (!value || Array.isArray(value) && !value.length) return '';
    let content = '';
    if (key === 'summary') content = `<p>${escape(value)}</p>`;
    else if (key === 'skills' || key === 'languages') content = `<p>${value.map(escape).join(' · ')}</p>`;
    else content = value.map(e => `<section class="entry"><header><strong>${escape(e.company || e.title)}</strong><span>${escape(e.period)}</span></header>${e.company ? `<p class="role">${escape(e.title)}</p>` : ''}<ul>${list(e.bullets).map(b => `<li>${escape(b)}</li>`).join('')}</ul></section>`).join('');
    return `<section><h2>${escape(SECTION_LABELS[key])}</h2>${content}</section>`;
  }).join('');
  const color = /^#[0-9a-f]{6}$/i.test(accent) ? accent : '#164e63';
  return `<!doctype html><html lang="en"><head><meta charset="utf-8"><title>${escape(cv.name)} — CV</title><style>@page{size:A4;margin:14mm}*{box-sizing:border-box}body{font-family:${font === 'sans' ? 'Arial,sans-serif' : 'Georgia,serif'};font-size:10pt;line-height:1.3;color:#17212b;max-width:180mm;margin:24px auto;padding:0 10px}h1{text-align:center;font-size:25pt;margin:0 0 4px}h2{color:${color};font-size:11pt;text-transform:uppercase;border-bottom:1px solid ${color};margin:14px 0 6px;break-after:avoid}p{margin:4px 0;orphans:3;widows:3}.contact,.headline{text-align:center}.entry{margin:9px 0}header{display:flex;justify-content:space-between;gap:12px;break-after:avoid}.role{font-style:italic;break-after:avoid}ul{padding-left:18px;margin:5px 0}li{margin:2px 0;break-inside:avoid}h1,h2{break-inside:avoid}@media print{body{padding:0;margin:0;max-width:none}}</style></head><body><h1>${escape(cv.name)}</h1><p class="headline">${escape(cv.headline)}</p><p class="contact">${[cv.location, cv.email, cv.phone, cv.linkedin_url, cv.website, cv.github_url].filter(Boolean).map(escape).join(' | ')}</p>${body}</body></html>`;
}
