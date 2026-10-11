import { test, expect } from 'playwright/test';
import { readFile } from 'node:fs/promises';

const job = { canonical_job_id: 'cv-job', title: 'Strategy Associate', company: 'Example', current_version_id: 'v1',
  description_intelligence: { state: 'available', prompt_version: 'runr_description_nemo_v3' },
  runr_summary: { overview: 'Develop business strategies.', required_qualifications: ['Strategy consulting and SQL skills.'] } };
test.beforeEach(async ({ page }) => {
  await page.route('**/v1/**', route => {
    const path = new URL(route.request().url()).pathname;
    return route.fulfill({ json: path.endsWith('/personalized-jobs/cv-job') ? job : path.endsWith('/documents') ? { documents: [] } : {} });
  });
});

test('selected-job sample generates, edits, reopens and exports the current CV', async ({ page }) => {
  await page.goto('/jobs/cv-job');
  await page.getByRole('button', { name: 'Customize CV', exact: true }).click();
  const drawer = page.getByRole('dialog', { name: 'Customize CV' });
  await drawer.getByRole('button', { name: 'Try working sample' }).click();
  for (const title of ['Job title', 'Years of experience', 'Industry experience', 'ATS keywords', 'Summary']) await expect(drawer.getByText(title, { exact: true }).first()).toBeVisible();
  await page.screenshot({ path: `test-results/cv-compare-${test.info().project.name}.png`, fullPage: true });
  await drawer.getByRole('button', { name: 'Customize this CV' }).click();
  await expect(drawer.getByRole('checkbox', { name: 'Investment banking', exact: true })).toBeDisabled();
  await drawer.getByRole('button', { name: 'Summary help' }).click();
  await expect(drawer.getByRole('tooltip')).toBeVisible();
  await drawer.getByRole('button', { name: 'Summary help' }).click();
  await page.screenshot({ path: `test-results/cv-options-${test.info().project.name}.png`, fullPage: true });
  await drawer.getByRole('button', { name: 'Generate sample CV' }).click();
  await expect(drawer.getByRole('textbox', { name: 'Full name', exact: true })).toBeVisible();
  await drawer.getByRole('textbox', { name: 'Full name', exact: true }).fill('Edited Candidate');
  await drawer.getByRole('textbox', { name: 'Headline', exact: true }).click();
  await expect(drawer.getByText('Saved on this device', { exact: true })).toBeVisible();
  await page.screenshot({ path: `test-results/cv-editor-${test.info().project.name}.png`, fullPage: true });
  const download = page.waitForEvent('download');
  await drawer.getByRole('button', { name: 'Download CV', exact: true }).click();
  const file = await download;
  expect(file.suggestedFilename()).toContain('Edited-Candidate');
  const exported = await readFile((await file.path())!, 'utf8');
  expect(exported).toContain('Edited Candidate');
  expect(exported).not.toContain('contenteditable');
  await drawer.getByRole('button', { name: 'Close customization' }).click();
  await page.getByRole('button', { name: 'Customize CV', exact: true }).click();
  await drawer.getByRole('button', { name: 'Try working sample' }).click();
  await expect(drawer.getByRole('textbox', { name: 'Full name', exact: true })).toHaveText('Edited Candidate');
  await drawer.getByRole('button', { name: 'Undo edit' }).click();
  await expect(drawer.getByRole('textbox', { name: 'Full name', exact: true })).toHaveText('Alex Morgan');
  await drawer.getByRole('textbox', { name: 'Full name', exact: true }).fill('Escape preserves this');
  await page.keyboard.press('Escape');
  await expect(drawer).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Customize CV', exact: true })).toBeFocused();
  await page.getByRole('button', { name: 'Customize CV', exact: true }).click();
  await drawer.getByRole('button', { name: 'Try working sample' }).click();
  await expect(drawer.getByRole('textbox', { name: 'Full name', exact: true })).toHaveText('Escape preserves this');
  await page.screenshot({ path: `test-results/cv-viewport-${test.info().project.name}.png` });
});

test('actual CV analyzes, generates through the API and edits in the side panel', async ({ page }) => {
  await page.route('**/v1/documents?*', route => route.fulfill({ json: { documents: [{ asset_id: 'mine', filename: 'My CV.pdf', document_type: 'cv' }] } }));
  await page.route('**/v1/documents/assets/mine/editor', route => route.fulfill({ json: { editor: { revision: 2, profile: { name: 'Real Candidate', summary: 'SQL analyst', competencies: ['SQL'], recent_experience: [{ title: 'Analyst', company: 'Example', period: '2020 - 2022', bullets: ['Built reports using SQL'] }] } } } }));
  await page.route('**/v1/cv-customization/analyze', route => route.fulfill({ json: { requirements: { title: 'Strategy Associate', years: 3, yearsBasis: 'inferred', industries: ['Consulting'], roleTerms: ['Strategy'], priorities: ['SQL'], keywords: [{ label: 'SQL', source: 'SQL skills' }, { label: 'Data analysis', source: 'Analyze data', evidence: 'Built reports using SQL' }] } } }));
  await page.route('**/v1/cv-customization/generate', route => route.fulfill({ json: { draft: { name: 'Real Candidate', headline: 'Analyst', summary: 'Generated analysis summary', skills: ['SQL', 'Data analysis'], experience: [{ title: 'Analyst', company: 'Example', period: '2020 - 2022', bullets: ['Delivered SQL reporting insights'] }], projects: [], education: [], languages: [], custom: [], order: ['summary', 'experience', 'skills'] } } }));
  await page.goto('/jobs/cv-job');
  await page.getByRole('button', { name: 'Customize CV', exact: true }).click();
  const drawer = page.getByRole('dialog', { name: 'Customize CV' });
  await drawer.getByRole('combobox', { name: 'Baseline CV' }).selectOption('mine');
  await expect(drawer.getByText('Real Candidate', { exact: true })).toBeVisible();
  await drawer.getByRole('button', { name: 'Customize this CV' }).click();
  await expect(drawer.getByText(/Live AI generation is not connected yet/)).toHaveCount(0);
  await drawer.getByRole('button', { name: 'Select supported' }).click();
  await expect(drawer.getByRole('checkbox', { name: 'Data analysis', exact: true })).toBeChecked();
  await drawer.getByRole('button', { name: 'Generate tailored CV' }).click();
  await expect(drawer.getByRole('textbox', { name: 'Full name', exact: true })).toHaveText('Real Candidate');
  await drawer.getByRole('button', { name: 'Edit', exact: true }).click();
  await drawer.locator('.cv-side-editor textarea').fill('Edited from the side panel');
  await expect(drawer.locator('.cv-paper').getByRole('textbox', { name: 'Professional summary', exact: true })).toHaveText('Edited from the side panel');
  await page.keyboard.press('Escape');
  await expect(drawer).toHaveCount(0);
});

test('connection cards expand real people and designed empty states without images', async ({ page }) => {
  await page.route('**/v1/personalized-jobs/cv-job', route => route.fulfill({ json: { ...job, network_connections: [{ name: 'Existing Contact', role: 'Engineer', linkedin_url: 'https://linkedin.com/in/example' }], shared_background_connections: [] } }));
  await page.goto('/jobs/cv-job');
  await expect(page.locator('.jobs-setup-rail')).toHaveCount(0);
  await page.getByRole('button', { name: /Your connections/ }).click();
  await expect(page.getByText('Existing Contact', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: /Shared background/ }).click();
  await expect(page.getByText(/No confirmed overlap yet/)).toBeVisible();
  await expect(page.locator('.job-connections img')).toHaveCount(0);
  await page.screenshot({ path: `test-results/job-connections-v2-${test.info().project.name}.png`, fullPage: true });
});
