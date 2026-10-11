import test from 'node:test';
import assert from 'node:assert/strict';
import { assessCv, normalizeCv, generateSampleCv, experienceYears, buildCvExport, draftKey, termsIn, requirementsForJob, readDraft, saveDraft } from './cvCustomization.js';
import { SAMPLE_CV, SAMPLE_JOB } from '../data/cvCustomizationSample.js';

test('overlapping roles count once and unknown dates do not invent years', () => {
  assert.equal(experienceYears([{ period: 'Jan 2020 - Dec 2021' }, { period: 'Jan 2021 - Dec 2022' }]), 3);
  assert.equal(experienceYears([{ period: '' }]), null);
});
test('ATS aliases and word boundaries count unique requirements rather than repetitions', () => {
  const terms = [{ label: 'SQL', aliases: [] }, { label: 'Enterprise software / SaaS', aliases: ['SaaS'] }];
  assert.deepEqual(termsIn('NoSQL SQL SQL SaaS', terms).map(t => t.label), terms.map(t => t.label));
  assert.equal(termsIn('NoSQL', terms).length, 0);
});
test('sample produces all sections without mutating original or adding unproven finance experience', () => {
  const original = JSON.stringify(SAMPLE_CV);
  const draft = generateSampleCv(SAMPLE_CV, SAMPLE_JOB, { sections: ['summary', 'skills', 'experience', 'projects'], keywords: ['Corporate strategy', 'Investment banking'], scope: 'full', confirmations: {} });
  assert.equal(JSON.stringify(SAMPLE_CV), original);
  assert.equal(draft.experience.length, SAMPLE_CV.experience.length);
  assert.equal(draft.projects.length, SAMPLE_CV.projects.length);
  assert.deepEqual(draft.education, SAMPLE_CV.education);
  assert.ok(!JSON.stringify(draft).toLowerCase().includes('investment banking'));
  assert.ok(assessCv(draft, SAMPLE_JOB).score > assessCv(SAMPLE_CV, SAMPLE_JOB).score);
});
test('unselected sections are preserved and quick edit changes only two experiences', () => {
  const onlySummary = generateSampleCv(SAMPLE_CV, SAMPLE_JOB, { sections: ['summary'], keywords: [], scope: 'full' });
  assert.deepEqual(onlySummary.experience, SAMPLE_CV.experience);
  assert.deepEqual(onlySummary.skills, SAMPLE_CV.skills);
  const quick = generateSampleCv(SAMPLE_CV, SAMPLE_JOB, { sections: ['experience'], keywords: [], scope: 'quick' });
  assert.equal(quick.experience.filter((entry, i) => JSON.stringify(entry) !== JSON.stringify(SAMPLE_CV.experience[i])).length, 2);
  assert.deepEqual(quick.summary, SAMPLE_CV.summary);
});
test('coverage changes with content and confirmations alone cannot increase score', () => {
  const before = assessCv(SAMPLE_CV, SAMPLE_JOB);
  const repeated = assessCv({ ...SAMPLE_CV, skills: [...SAMPLE_CV.skills, ...SAMPLE_CV.skills] }, SAMPLE_JOB);
  assert.equal(before.score, repeated.score);
  const changed = { ...SAMPLE_CV, skills: [...SAMPLE_CV.skills, 'Corporate strategy'] };
  assert.ok(assessCv(changed, SAMPLE_JOB).keywords.matched.length > before.keywords.matched.length);
  assert.equal(before.dimensions.length, 5);
});
test('unknown job requirements do not create perfect match', () => {
  const assessment = assessCv(normalizeCv({}), { title: '', keywords: [], industries: [] });
  assert.equal(assessment.score, null);
  assert.ok(assessment.dimensions.every(d => d.status === 'unknown'));
  assert.equal(requirementsForJob({ title: 'Engineer', runrSummary: { required_qualifications: ['Python and SQL required'] } }).keywords.length, 2);
});
test('normalizes actual CV editor payload without losing education and contact fields', () => {
  const cv = normalizeCv({ name: 'Candidate', competencies: ['SQL'], recent_experience: [{ title: 'Analyst', company: 'A', period: '2020 - 2022', bullets: ['Built reports'] }], education: [{ degree_title: 'BSc', institution: 'University' }], languages: ['English'], linkedin_url: 'https://example.com/profile' });
  assert.equal(cv.experience[0].title, 'Analyst');
  assert.equal(cv.education[0].title, 'BSc');
  assert.deepEqual(cv.skills, ['SQL']);
  assert.equal(cv.linkedin_url, 'https://example.com/profile');
});
test('export uses current edits, escapes HTML and draft identity includes user/job/source revision', () => {
  const html = buildCvExport({ ...SAMPLE_CV, name: '<script>alert(1)</script>', summary: 'Edited summary' });
  assert.ok(html.includes('Edited summary'));
  assert.ok(!html.includes('<script>alert(1)</script>'));
  assert.ok(html.includes('&lt;script&gt;'));
  assert.notEqual(draftKey('a', { id: '1' }, 'cv', 1), draftKey('b', { id: '1' }, 'cv', 1));
  assert.notEqual(draftKey('a', { id: '1' }, 'cv', 1), draftKey('a', { id: '1' }, 'cv', 2));
});

test('removed sections do not contribute invisible ATS keywords or experience', () => {
  const cv = { ...normalizeCv({}), skills: ['SQL'], experience: [{ title: 'SQL analyst', company: 'A', period: '2020 - 2022', bullets: [] }], order: ['summary'] };
  const result = assessCv(cv, { keywords: [{ label: 'SQL' }], years: 2 });
  assert.equal(result.keywords.matched.length, 0);
  assert.equal(result.years, null);
  assert.ok(!buildCvExport(cv).includes('SQL analyst'));
});
test('draft storage errors and malformed drafts are recoverable', () => {
  const unavailable = { getItem() { throw Error('denied'); }, setItem() { throw Error('full'); } };
  assert.equal(readDraft('k', unavailable), null);
  assert.equal(saveDraft('k', {}, unavailable), false);
  assert.equal(readDraft('k', { getItem: () => JSON.stringify({ draft: { experience: [] } }) }), null);
});
test('job identity changes when its requirements change and retains provided version', () => {
  const a = requirementsForJob({ id: '1', title: 'Analyst', runrSummary: { required_qualifications: ['SQL'] } });
  const b = requirementsForJob({ id: '1', title: 'Analyst', runrSummary: { required_qualifications: ['Python'] } });
  assert.notEqual(draftKey('u', a, 'cv', 1), draftKey('u', b, 'cv', 1));
});
test('custom sections from the existing editor preserve their lines', () => {
  const result = normalizeCv({ custom_sections: [{ heading: 'Awards', lines: ['Winner 2024'], content: 'Winner 2024' }] });
  assert.deepEqual(result.custom[0].bullets, ['Winner 2024']);
  assert.ok(buildCvExport(result).includes('Winner 2024'));
});
