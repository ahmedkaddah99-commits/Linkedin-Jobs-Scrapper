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

test('actual CV is assessed without invoking incomplete production rewriting', async ({ page }) => {
  await page.route('**/v1/documents?*', route => route.fulfill({ json: { documents: [{ asset_id: 'mine', filename: 'My CV.pdf', document_type: 'cv' }] } }));
  await page.route('**/v1/documents/assets/mine/editor', route => route.fulfill({ json: { editor: { revision: 2, profile: { name: 'Real Candidate', summary: 'SQL analyst', competencies: ['SQL'], recent_experience: [{ title: 'Analyst', company: 'Example', period: '2020 - 2022', bullets: ['Built reports using SQL'] }] } } } }));
  await page.goto('/jobs/cv-job');
  await page.getByRole('button', { name: 'Customize CV', exact: true }).click();
  const drawer = page.getByRole('dialog', { name: 'Customize CV' });
  await drawer.getByRole('combobox', { name: 'Baseline CV' }).selectOption('mine');
  await expect(drawer.getByText('Real Candidate', { exact: true })).toBeVisible();
  await drawer.getByRole('button', { name: 'Customize this CV' }).click();
  await expect(drawer.getByText(/Live AI generation is not connected yet/)).toBeVisible();
  await drawer.getByRole('button', { name: 'Open editable draft' }).click();
  await expect(drawer.getByRole('textbox', { name: 'Full name', exact: true })).toHaveText('Real Candidate');
  await page.keyboard.press('Escape');
  await expect(drawer).toHaveCount(0);
});
